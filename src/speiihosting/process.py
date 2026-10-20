from __future__ import annotations

import logging
import logging.handlers
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import psutil

from .config import Service, SpeiiError
from .security import app_values, safe_environment
from .storage import Store, read_json, write_json

LOG_BYTES = 5_000_000


def logger_for(path: Path) -> logging.Logger:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    logger = logging.Logger(str(path))
    handler = logging.handlers.RotatingFileHandler(
        path, maxBytes=LOG_BYTES, backupCount=1, encoding="utf-8"
    )
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)
    return logger


def close_logger(logger: logging.Logger) -> None:
    for handler in list(logger.handlers):
        handler.close()
        logger.removeHandler(handler)


def pump(pipe, logger: logging.Logger) -> None:
    try:
        while block := pipe.read1(8192):
            logger.info(block.decode("utf-8", errors="replace").rstrip("\n"))
    finally:
        pipe.close()


def detached_flags() -> dict:
    if os.name == "nt":
        return {"creationflags": subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP}
    return {"start_new_session": True}


def run_logged(command: list[str], cwd: Path, log: Path, env: dict | None = None) -> int:
    logger = logger_for(log)
    try:
        child = subprocess.Popen(
            command,
            cwd=cwd,
            env=env if env is not None else safe_environment(),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        thread = threading.Thread(target=pump, args=(child.stdout, logger), daemon=True)
        thread.start()
        try:
            code = child.wait(timeout=1800)
        except (KeyboardInterrupt, subprocess.TimeoutExpired):
            terminate_tree(child.pid)
            raise SpeiiError(
                "Build cancelled or timed out; the live release was preserved."
            ) from None
        thread.join(timeout=5)
        return code
    except OSError as error:
        raise SpeiiError(f"Cannot run {command[0]}: {error}") from error
    finally:
        close_logger(logger)


def identity(pid: int) -> dict:
    return {"pid": pid, "created": psutil.Process(pid).create_time()}


def matches(record: dict | None) -> bool:
    if not record:
        return False
    try:
        process = psutil.Process(record["pid"])
        return (
            abs(process.create_time() - record["created"]) < 0.01
            and process.status() != psutil.STATUS_ZOMBIE
        )
    except (psutil.Error, KeyError, TypeError):
        return False


def alive(store: Store, name: str) -> bool:
    return matches(read_json(store.home / "pids" / (name + ".json"), {}))


def terminate_tree(pid: int, created: float | None = None) -> None:
    try:
        parent = psutil.Process(pid)
        if created is not None and abs(parent.create_time() - created) >= 0.01:
            return
        children = parent.children(recursive=True)
        targets = [*reversed(children), parent]
        for process in targets:
            try:
                process.terminate()
            except psutil.Error:
                pass
        _, running = psutil.wait_procs(targets, timeout=5)
        for process in running:
            try:
                process.kill()
            except psutil.Error:
                pass
    except psutil.Error:
        pass


def ensure_daemon(store: Store) -> None:
    if alive(store, "speii-daemon"):
        return
    env = safe_environment()
    env["SPEIIHOSTING_HOME"] = str(store.home)
    subprocess.Popen(
        [sys.executable, "-m", "speiihosting.daemon"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=env,
        **detached_flags(),
    )
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if alive(store, "speii-daemon"):
            return
        time.sleep(0.1)
    raise SpeiiError("Supervisor did not start. Inspect speiihos logs speii-daemon.")


def stop_daemon(store: Store) -> None:
    record = read_json(store.home / "pids/speii-daemon.json", {})
    if not matches(record):
        return
    process = psutil.Process(record["pid"])
    # A file request also permits graceful Windows shutdown, where terminate()
    # forcefully ends a process rather than delivering SIGTERM.
    write_json(store.home / "pids/stop.json", {"requested": time.time()})
    deadline = time.monotonic() + 20
    while matches(record) and time.monotonic() < deadline:
        time.sleep(0.1)
    if matches(record):
        terminate_tree(process.pid, record["created"])


def environment(service: Service, live: Path) -> dict[str, str]:
    env = safe_environment(service.env_allow)
    # No shell evaluation and no token values printed or written to the registry.
    env.update(app_values(live / ".env"))
    prefixes = [str(live / "node_modules/.bin")]
    if service.environment_dir:
        prefixes.insert(0, str(service.environment_dir / ("Scripts" if os.name == "nt" else "bin")))
        env["VIRTUAL_ENV"] = str(service.environment_dir)
    env["PATH"] = os.pathsep.join([*prefixes, env.get("PATH", "")])
    env["HOST"] = env["HOSTNAME"] = env["NITRO_HOST"] = "127.0.0.1"
    if service.port:
        env["PORT"] = env["NITRO_PORT"] = str(service.port)
    env["PYTHONUNBUFFERED"] = "1"
    env["SPEII_DATA_DIR"] = str(live.parent / "data")
    return env


def command_for(service: Service) -> list[str]:
    python = (
        str(service.environment_dir / ("Scripts/python.exe" if os.name == "nt" else "bin/python"))
        if service.environment_dir
        else sys.executable
    )
    return [python if part == "{python}" else part for part in service.command]


class Worker:
    def __init__(
        self,
        store: Store,
        name: str,
        command: list[str],
        cwd: Path,
        generation: object,
        env: dict | None = None,
        service: Service | None = None,
    ):
        self.store, self.name, self.command, self.cwd = store, name, command, cwd
        self.generation, self.env = generation, env
        self.service = service
        self.terminating: threading.Thread | None = None
        self.limit_check_at = 0.0
        self.process: subprocess.Popen | None = None
        self.thread: threading.Thread | None = None
        self.record: dict = {}
        self.failures: list[float] = []
        self.retry_at = 0.0
        self.crashed = False
        self.error = ""
        self.started_at = 0.0
        self.metrics: psutil.Process | None = None
        self.metric_children: dict[int, psutil.Process] = {}
        self.metric_snapshot = {"memory": 0, "cpu": 0.0}
        self.metrics_at = 0.0
        self.logger = logger_for(store.home / "logs" / (name + ".log"))

    def tick(self) -> None:
        now = time.monotonic()
        if (
            self.process
            and self.service
            and self.service.isolation == "process"
            and now >= self.limit_check_at
        ):
            self.limit_check_at = now + 2
            try:
                parent = self.metrics or psutil.Process(self.process.pid)
                total = sum(p.memory_info().rss for p in [parent, *parent.children(recursive=True)])
                if total > self.service.resources.memory_mb * 1024 * 1024:
                    self.request_restart("Memory limit exceeded")
            except (psutil.Error, OSError):
                pass
        if self.process and self.process.poll() is not None:
            self.error = f"Exited with code {self.process.returncode}"
            if self.thread:
                self.thread.join(timeout=1)
            self.process = None
            self.failures = [t for t in self.failures if now - t < 60] + [now]
            self.retry_at = now + min(2 ** (len(self.failures) - 1), 10)
            self.crashed = len(self.failures) > 5
            self.logger.warning(
                self.error + ("; crash limit reached" if self.crashed else "; restarting")
            )
        if (
            self.process
            or self.crashed
            or now < self.retry_at
            or (self.terminating and self.terminating.is_alive())
        ):
            return
        try:
            self.process = subprocess.Popen(
                self.command,
                cwd=self.cwd,
                env=self.env,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                **detached_flags(),
            )
            self.record = identity(self.process.pid)
            self.record.update(
                generation=self.generation,
                isolation=self.service.isolation if self.service else "infrastructure",
            )
            self.started_at = time.monotonic()
            self.metrics = psutil.Process(self.process.pid)
            self.metrics.cpu_percent()
            self.metric_children = {}
            self.metrics_at = 0.0
            write_json(self.store.home / "pids" / (self.name + ".json"), self.record)
            self.thread = threading.Thread(
                target=pump, args=(self.process.stdout, self.logger), daemon=True
            )
            self.thread.start()
        except (OSError, psutil.Error) as error:
            self.error = f"Could not launch {self.command[0]}: {error}"
            self.logger.error(self.error)
            self.crashed = True
            self.process = None

    def stop(self) -> None:
        if self.terminating:
            self.terminating.join(timeout=20)
        if self.service and self.service.isolation == "podman":
            from .isolation import adapter

            adapter(self.service).stop(self.store, self.service)
        if self.process:
            terminate_tree(self.process.pid, self.record.get("created"))
            try:
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                pass
        if self.thread:
            self.thread.join(timeout=2)
        self.process = None
        (self.store.home / "pids" / (self.name + ".json")).unlink(missing_ok=True)
        close_logger(self.logger)

    def request_restart(self, reason: str) -> None:
        if not self.process or (self.terminating and self.terminating.is_alive()):
            return
        self.logger.warning(reason)
        pid, created = self.process.pid, self.record.get("created")

        def terminate():
            if self.service and self.service.isolation == "podman":
                from .isolation import adapter

                adapter(self.service).stop(self.store, self.service)
            terminate_tree(pid, created)

        self.terminating = threading.Thread(target=terminate, daemon=True)
        self.terminating.start()

    def status(self) -> dict:
        state = (
            "crashed"
            if self.crashed
            else "running"
            if self.process and self.process.poll() is None
            else "restarting"
        )
        result = {
            "status": state,
            "generation": self.generation,
            "error": self.error,
            "restarts": len(self.failures),
            "pid": None,
            "cpu": 0.0,
            "memory": 0,
            "uptime": time.monotonic() - self.started_at if state == "running" else 0,
        }
        if state == "running":
            try:
                process = self.metrics or psutil.Process(self.process.pid)
                now = time.monotonic()
                if not self.metrics_at or now - self.metrics_at >= 2:
                    current = {
                        p.pid: self.metric_children.get(p.pid, p)
                        for p in process.children(recursive=True)
                    }
                    self.metric_children = current
                    targets = [process, *current.values()]
                    self.metric_snapshot = {
                        "memory": sum(p.memory_info().rss for p in targets),
                        "cpu": sum(p.cpu_percent() for p in targets),
                    }
                    self.metrics_at = now
                result.update(pid=process.pid, **self.metric_snapshot)
            except psutil.Error:
                result["status"] = "restarting"
        return result


def wait_service(
    store: Store, service: Service, running: bool = True, timeout: float | None = None
) -> None:
    from .health import probe
    from .ports import listening

    deadline = time.monotonic() + (
        timeout or (service.health.startup_timeout if service.health else 30)
    )
    status = {}
    last_health = {"status": "not_checked"}
    while time.monotonic() < deadline:
        runtime = read_json(store.home / "runtime.json", {})
        status = runtime.get("services", {}).get(service.name, {})
        if not running and status.get("status", "stopped") == "stopped":
            return
        if running and status.get("generation") == service.generation:
            if status.get("restarts", 0):
                raise SpeiiError(
                    f"{service.name} exited during startup. Inspect speiihos logs {service.name}."
                )
            if status.get("status") == "crashed":
                raise SpeiiError(f"{service.name} crashed. Inspect speiihos logs {service.name}.")
            if status.get("status") == "running" and (
                not service.command or status.get("uptime", 0) >= 1
            ):
                if service.full_domain:
                    infra = runtime.get("infrastructure", {})
                    if any(
                        infra.get(k, {}).get("status") == "crashed"
                        or infra.get(k, {}).get("restarts", 0)
                        for k in ("nginx", "cloudflared")
                    ):
                        raise SpeiiError(
                            "Public routing failed to start. Inspect logs nginx and logs cloudflared."
                        )
                    if any(
                        infra.get(k, {}).get("status") != "running"
                        or infra.get(k, {}).get("uptime", 0) < 1
                        for k in ("nginx", "cloudflared")
                    ) or not listening(store.settings().nginx_port):
                        time.sleep(0.15)
                        continue
                if service.health:
                    # A successful HTTP request proves the listener is ready too.
                    # Avoid an extra empty TCP connection before every HTTP probe.
                    last_health = probe(service)
                    if last_health["status"] != "healthy":
                        time.sleep(0.15)
                        continue
                elif service.port and not listening(service.port):
                    time.sleep(0.15)
                    continue
                return
        time.sleep(0.15)
    details = f"Last process state: {status.get('status', 'not_reported')}."
    if running and service.health:
        details += f" HTTP health: {last_health['status']}"
        if "http_status" in last_health:
            details += f" (HTTP {last_health['http_status']})"
        details += "."
    raise SpeiiError(
        f"{service.name} did not become {'ready' if running else 'stopped'}. "
        f"{details} Inspect speiihos logs {service.name}."
    )
