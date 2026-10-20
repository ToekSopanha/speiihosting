from __future__ import annotations

import os
import platform
import signal
import subprocess
import time

from .config import SpeiiError
from .doctor import find_binary
from .health import HealthMonitor
from .isolation import adapter
from .nginx import Nginx
from .ports import listening
from .process import (
    LOG_BYTES,
    Worker,
    close_logger,
    identity,
    logger_for,
    matches,
    terminate_tree,
)
from .security import safe_environment
from .storage import Store, file_lock, read_json, write_json
from .transactions import pending, recover


def run(store: Store) -> None:
    with file_lock(store.home / "daemon.lock", timeout=0):
        # Reclaim only recorded process identities from a previous supervisor.
        for path in (store.home / "pids").glob("*.json"):
            record = read_json(path, {})
            if record.get("isolation") == "podman":
                service = store.services().get(path.stem)
                if service:
                    previous = service.model_copy(update={"generation": record["generation"]})
                    adapter(previous).stop(store, previous)
            if matches(record):
                terminate_tree(record["pid"], record["created"])
            path.unlink(missing_ok=True)
        logger = logger_for(store.home / "logs/speii-daemon.log")
        workers: dict[str, Worker] = {}
        monitor = HealthMonitor()
        last_write = 0.0
        last_transition = None
        failed = {}
        last_recovery_error = None
        quarantined: set[str] = set()
        quarantined_routing = None
        quarantine_public_block = False
        stopping = False

        def shutdown(*_):
            nonlocal stopping
            stopping = True

        signal.signal(signal.SIGTERM, shutdown)
        signal.signal(signal.SIGINT, shutdown)
        if hasattr(signal, "SIGHUP"):
            signal.signal(signal.SIGHUP, signal.SIG_IGN)
        (store.home / "pids/stop.json").unlink(missing_ok=True)
        write_json(store.home / "pids/speii-daemon.json", identity(os.getpid()))
        logger.info("Supervisor started")
        try:
            while not stopping:
                if (store.home / "pids/stop.json").exists():
                    break
                try:
                    try:
                        if pending(store):
                            with file_lock(store.home / "state.lock", timeout=0):
                                names = recover(store)
                                if names:
                                    logger.info(
                                        "Recovered interrupted deployment: %s", ", ".join(names)
                                    )
                        last_recovery_error = None
                        quarantined = set()
                    except (SpeiiError, OSError, ValueError) as error:
                        if "Another Speii process holds" not in str(error):
                            quarantined = {p.parent.name for p in pending(store)}
                            if str(error) != last_recovery_error:
                                logger.error("Recovery required: %s", error)
                                last_recovery_error = str(error)
                    settings = store.settings()
                    services = store.services()
                    affected_public = any(
                        s.full_domain and (s.name in quarantined or s.backend in quarantined)
                        for s in services.values()
                    )
                    if affected_public:
                        signature = repr(
                            [
                                (name, s.generation, s.status, s.backend)
                                for name, s in services.items()
                            ]
                        ) + repr(sorted(quarantined))
                        if signature != quarantined_routing:
                            try:
                                with file_lock(store.home / "state.lock", timeout=0):
                                    safe = {
                                        name: s.model_copy(deep=True)
                                        for name, s in services.items()
                                    }
                                    for name in quarantined:
                                        if name in safe:
                                            safe[name].status = "stopped"
                                    Nginx(store).apply(safe)
                                    quarantined_routing = signature
                                    quarantine_public_block = False
                            except (SpeiiError, OSError, ValueError, subprocess.SubprocessError):
                                quarantine_public_block = True
                    else:
                        quarantine_public_block = False
                        quarantined_routing = None
                    wanted: dict[str, tuple] = {}
                    public = any(s.full_domain and s.status == "running" for s in services.values())
                    infrastructure_error = None
                    try:
                        if public:
                            nginx = Nginx(store)
                            wanted["nginx"] = (
                                nginx.command("-g", "daemon off;"),
                                nginx.root,
                                settings.nginx_port,
                                safe_environment(),
                                None,
                            )
                            cloudflared = find_binary("cloudflared", store)
                            if not cloudflared:
                                raise SpeiiError("cloudflared is missing; run doctor --install.")
                            if settings.tunnel_mode == "remote":
                                env = safe_environment()
                                env["TUNNEL_TOKEN"] = (
                                    settings.tunnel_token.get_secret_value()
                                    if settings.tunnel_token
                                    else ""
                                )
                                command = [
                                    cloudflared,
                                    "tunnel",
                                    "--no-autoupdate",
                                    "--pidfile",
                                    str(store.home / "pids/tunnel-connected.pid"),
                                    "run",
                                ]
                                revision = (
                                    settings.tunnel_id,
                                    settings.tunnel_token.get_secret_value()
                                    if settings.tunnel_token
                                    else "",
                                )
                                # A hash is safe to persist as the runtime generation.
                                import hashlib

                                revision = hashlib.sha256(repr(revision).encode()).hexdigest()
                            else:
                                env = safe_environment()
                                command = [
                                    cloudflared,
                                    "tunnel",
                                    "--config",
                                    str(store.home / "tunnel.yml"),
                                    "--no-autoupdate",
                                    "--pidfile",
                                    str(store.home / "pids/tunnel-connected.pid"),
                                    "run",
                                ]
                                revision = (store.home / "tunnel.yml").stat().st_mtime_ns
                            wanted["cloudflared"] = (command, store.home, revision, env, None)
                    except (SpeiiError, OSError, ValueError, subprocess.SubprocessError) as error:
                        infrastructure_error = str(error)
                        if failed.get("infrastructure") != infrastructure_error:
                            logger.error("Public routing unavailable: %s", infrastructure_error)
                            failed["infrastructure"] = infrastructure_error
                    if quarantine_public_block:
                        wanted.pop("nginx", None)
                        infrastructure_error = "Public routing paused because recovery could not safely quarantine a site."
                    if settings.sleep_prevent and platform.system() == "Darwin":
                        wanted["sleep"] = (
                            ["/usr/bin/caffeinate", "-is"],
                            store.home,
                            1,
                            safe_environment(),
                            None,
                        )
                    for service in services.values():
                        if service.name in quarantined:
                            continue
                        if service.status == "running" and service.command and not service.external:
                            current = workers.get(service.name)
                            try:
                                if current and current.generation == service.generation:
                                    wanted[service.name] = (
                                        current.command,
                                        current.cwd,
                                        service.generation,
                                        current.env,
                                        service,
                                    )
                                else:
                                    spec = adapter(service).launch(store, service)
                                    wanted[service.name] = (
                                        spec.command,
                                        spec.cwd,
                                        service.generation,
                                        spec.env,
                                        service,
                                    )
                                failed.pop(service.name, None)
                            except (SpeiiError, OSError, ValueError) as error:
                                message = str(error)
                                if failed.get(service.name) != message:
                                    logger.error("%s: %s", service.name, message)
                                failed[service.name] = message
                    for name in list(workers):
                        if name not in wanted or workers[name].generation != wanted[name][2]:
                            workers.pop(name).stop()
                    for name, (command, cwd, generation, env, service) in wanted.items():
                        if name not in workers:
                            if name == "cloudflared":
                                (store.home / "pids/tunnel-connected.pid").unlink(missing_ok=True)
                            workers[name] = Worker(
                                store, name, command, cwd, generation, env, service
                            )
                        workers[name].tick()
                    states = {}
                    health_states = monitor.poll(
                        {k: v for k, v in services.items() if k not in quarantined}, workers
                    )
                    for service in services.values():
                        if service.name in quarantined:
                            state = {
                                "status": "recovery_required",
                                "generation": service.generation,
                                "error": last_recovery_error,
                            }
                        elif service.status != "running":
                            state = {"status": "stopped", "generation": service.generation}
                        elif service.name in workers:
                            state = workers[service.name].status()
                        elif service.name in failed:
                            state = {
                                "status": "crashed",
                                "generation": service.generation,
                                "error": failed[service.name],
                            }
                        else:
                            state = {
                                "status": "running"
                                if not service.external or listening(service.port)
                                else "offline",
                                "generation": service.generation,
                                "pid": None,
                            }
                        state["health"] = health_states.get(
                            service.name,
                            {"status": "starting" if service.health else "not_configured"},
                        )
                        state["isolation"] = service.isolation
                        states[service.name] = state
                    payload = {
                        "updated": time.time(),
                        "infrastructure_error": infrastructure_error,
                        "services": states,
                        "infrastructure": {
                            k: w.status() for k, w in workers.items() if k not in services
                        },
                    }
                    transition = repr(
                        [
                            (
                                name,
                                state.get("status"),
                                state.get("generation"),
                                state.get("pid"),
                                state.get("health", {}).get("status"),
                                state.get("uptime", 0) >= 1,
                            )
                            for name, state in {**states, **payload["infrastructure"]}.items()
                        ]
                    )
                    now = time.monotonic()
                    if (
                        transition != last_transition
                        or now - last_write >= settings.metrics_interval
                    ):
                        write_json(store.home / "runtime.json", payload, durable=False)
                        last_write, last_transition = now, transition
                    # Nginx writes its own logs: rotate and signal it to reopen.
                    rotated = False
                    for filename in ("nginx_access.log", "nginx_error.log"):
                        path = store.home / "logs" / filename
                        if path.exists() and path.stat().st_size >= LOG_BYTES:
                            if os.name == "nt":
                                # Windows cannot rename an open Nginx file.
                                import shutil

                                shutil.copyfile(path, path.with_suffix(".log.1"))
                                with path.open("w"):
                                    pass
                            else:
                                path.replace(path.with_suffix(".log.1"))
                                path.touch(mode=0o600)
                                rotated = True
                    if rotated and "nginx" in workers:
                        Nginx(store).signal("reopen")
                except Exception as error:
                    logger.error("Supervisor cycle failed: %s", error)
                time.sleep(0.25)
        finally:
            monitor.close()
            for worker in workers.values():
                worker.stop()
            write_json(
                store.home / "runtime.json", {"services": {}, "infrastructure": {}}, durable=False
            )
            (store.home / "pids/tunnel-connected.pid").unlink(missing_ok=True)
            (store.home / "pids/speii-daemon.json").unlink(missing_ok=True)
            logger.info("Supervisor stopped")
            close_logger(logger)


if __name__ == "__main__":
    store = Store()
    try:
        run(store)
    except SpeiiError:
        from .process import alive

        raise SystemExit(0 if alive(store, "speii-daemon") else 1)
