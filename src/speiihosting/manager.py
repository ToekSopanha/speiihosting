from __future__ import annotations

import re
import shutil
from contextlib import contextmanager
from pathlib import Path

from . import cloudflare
from .config import HealthCheck, Resources, Service, SpeiiError, valid_domain
from .isolation import adapter
from .nginx import Nginx
from .ports import allocate, listening
from .process import alive, ensure_daemon, environment, wait_service
from .projects import (
    Release,
    copy_source,
    executable,
    manifest,
    prepare,
    project_name,
    run_build,
    shell_command,
    static_directory,
)
from .storage import Store, read_json, write_json
from .transactions import Phase, Transaction, check_budget, recover


class Manager:
    def __init__(self, store: Store):
        self.store = store

    @contextmanager
    def lock(self):
        with self.store.lock():
            recover(self.store)
            yield

    def public_domain(self, subdomain: str, domain: str | None) -> str:
        settings = self.store.settings()
        root = valid_domain(domain or settings.default_domain)
        if not root or not settings.tunnel_id:
            raise SpeiiError("Run speiihos init before publishing a public site.")
        if subdomain in {"@", ""}:
            return root
        if not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", subdomain):
            raise SpeiiError(
                "Use one lowercase DNS label for --subdomain, or @ for the root domain."
            )
        return f"{subdomain}.{root}"

    def stage(
        self, service: Service, release: Release, build_front: bool = False, install: bool = True
    ) -> None:
        if release.candidate.exists():
            shutil.rmtree(release.candidate)
        log = self.store.home / "logs" / (service.name + ".build.log")
        if service.type == "frontend":
            if build_front and (
                service.build_command or "build" in manifest(service.source).get("scripts", {})
            ):
                workspace = release.site / "build-candidate"
                if workspace.exists():
                    shutil.rmtree(workspace)
                try:
                    copy_source(service.source, workspace)
                    prepare(service, workspace, release.site, log, install)
                    command = (
                        shell_command(service.build_command)
                        if service.build_command
                        else [executable("npm"), "run", "build"]
                    )
                    run_build(command, workspace, log, environment(service, workspace))
                    relative = Path(service.static_dir).relative_to(service.source)
                    output = static_directory(workspace, relative)
                    copy_source(output, release.candidate)
                finally:
                    if workspace.exists():
                        shutil.rmtree(workspace)
            else:
                output = static_directory(service.source, Path(service.static_dir))
                copy_source(output, release.candidate)
        else:
            copy_source(service.source, release.candidate)
            if service.isolation == "podman":
                service.command = (
                    shell_command(service.custom_command) if service.custom_command else ["{image}"]
                )
                service.framework = "container"
            else:
                prepare(service, release.candidate, release.site, log, install)
        check_budget(self.store, release.site)

    def routing(
        self, services: dict[str, Service], old: dict[str, Service], remote: bool = True
    ) -> None:
        if not any(s.full_domain for s in [*services.values(), *old.values()]):
            return
        Nginx(self.store).apply(services)
        if self.store.settings().tunnel_mode == "local":
            cloudflare.configure_local(self.store, services)
            return

        def routes(entries):
            return {
                s.full_domain for s in entries.values() if s.full_domain and s.status == "running"
            }

        if remote and routes(services) != routes(old):
            cloudflare.sync_routes(
                self.store, services, {s.full_domain for s in old.values() if s.full_domain}
            )

    def pause(self, service: Service, services: dict[str, Service]) -> None:
        paused = service.model_copy(deep=True)
        paused.status = "stopped"
        paused.generation += 1
        services[paused.name] = paused
        self.store.save_services(services)
        if alive(self.store, "speii-daemon"):
            wait_service(self.store, paused, running=False)

    def host(
        self,
        kind: str,
        source: Path,
        name: str | None = None,
        port: int | None = None,
        subdomain: str | None = None,
        domain: str | None = None,
        directory: Path | None = None,
        run: str | None = None,
        build: str | None = None,
        existing: bool = False,
        auto_port: bool = False,
        backend: str | None = None,
        frontend: str | None = None,
        install: bool = True,
        health: HealthCheck | None = None,
        env_allow: list[str] | None = None,
        isolation: str = "process",
        image: str | None = None,
        resources: Resources | None = None,
        streaming: bool = False,
        strict_dependencies: bool = False,
        reuse_data: bool = False,
    ) -> Service:
        source = source.expanduser().resolve()
        if not source.is_dir():
            raise SpeiiError(f"Source directory does not exist: {source}")
        with self.lock():
            old = self.store.services()
            service = Service(
                name=project_name(source, name or (subdomain if subdomain != "@" else None), port),
                type=kind,
                source=source,
                port=port,
                custom_command=run,
                build_command=build,
                external=existing,
                autostart=self.store.settings().autostart,
                health=health or (HealthCheck(expected_status=None) if port else None),
                env_allow=env_allow or [],
                isolation=isolation,
                image=image,
                resources=resources or Resources(),
                streaming=streaming,
                strict_dependencies=strict_dependencies,
            )
            if not existing and kind != "frontend":
                adapter(service).validate(service)
            if service.name in old:
                raise SpeiiError(f"{service.name} already exists; use deploy or choose --name.")
            site = self.store.site(service.name)
            if site.exists() and (
                not reuse_data or any(path.name != "data" for path in site.iterdir())
            ):
                raise SpeiiError(
                    f"Saved data exists for {service.name}; inspect it and use --reuse-data to attach it."
                )
            if subdomain is not None:
                for binary in ("nginx", "cloudflared"):
                    from .doctor import find_binary

                    if not find_binary(binary, self.store):
                        raise SpeiiError(f"{binary} is missing. Run doctor --install.")
                service.full_domain = self.public_domain(subdomain, domain)
                if any(s.full_domain == service.full_domain for s in old.values()):
                    raise SpeiiError("That hostname already belongs to another service.")
            if kind == "frontend":
                service.static_dir = str(static_directory(source, directory))
            if port:
                reserved = {s.port for s in old.values() if s.port} | {
                    self.store.settings().nginx_port
                }
                if existing:
                    if port in reserved or not listening(port):
                        raise SpeiiError(
                            "An existing service must listen on an unregistered local port."
                        )
                else:
                    service.port = allocate(port, reserved, auto_port)
            services = {k: v.model_copy(deep=True) for k, v in old.items()}
            if backend:
                target = self.store.resolve(backend)
                if target.type != "backend":
                    raise SpeiiError("--backend must identify a backend service.")
                service.backend = target.name
            services[service.name] = service
            if kind == "backend" and frontend:
                fronts = [self.store.resolve(frontend)]
                for front in fronts:
                    if front.type not in {"frontend", "dynamic"}:
                        raise SpeiiError("--frontend must identify a frontend or dynamic site.")
                    services[front.name].backend = service.name
            release = Release(self.store.site(service.name))
            (release.site / "data").mkdir(exist_ok=True, mode=0o700)
            promoted = False
            transaction = Transaction(self.store, service, old)
            try:
                if not existing:
                    self.stage(service, release, install=install)
                    transaction.begin()
                    transaction.phase(Phase.PROMOTING)
                    release.promote()
                    promoted = True
                self.routing(services, old, remote=False)
                self.store.save_services(services)
                ensure_daemon(self.store)
                wait_service(self.store, service)
                if service.full_domain:
                    settings = self.store.settings()
                    if settings.tunnel_mode == "local":
                        cloudflare.local_command(
                            self.store,
                            "tunnel",
                            "route",
                            "dns",
                            settings.tunnel_id,
                            service.full_domain,
                        )
                    else:
                        client = cloudflare.Cloudflare(settings)
                        try:
                            client.bind(service)
                        finally:
                            client.close()
                    self.store.save_services(services)
                    cloudflare.sync_routes(self.store, services)
                if not existing:
                    transaction.phase(Phase.COMMITTED)
            except Exception:
                self.pause(service, services)
                if transaction.path.exists():
                    recover(self.store)
                else:
                    self.store.save_services(old)
                    if promoted:
                        release.revert()
                    self.routing(old, services, remote=False)
                if service.dns_owned:
                    client = cloudflare.Cloudflare(self.store.settings())
                    try:
                        client.unbind(service)
                    finally:
                        client.close()
                if release.site.exists() and not any((release.site / "data").iterdir()):
                    shutil.rmtree(release.site)
                raise
            if not existing:
                transaction.finish()
            return service

    def deploy(
        self, identifier: str | None, install: bool = True, rollback: bool = False
    ) -> Service:
        with self.lock():
            old = self.store.services()
            original = self.store.resolve(identifier)
            if original.external:
                raise SpeiiError(
                    "External services are managed by their owner and cannot be deployed."
                )
            service = (
                original.model_copy(deep=True) if rollback else self.release_configuration(original)
            )
            service.public_verified = False
            release = Release(self.store.site(service.name))
            try:
                if rollback:
                    if not release.previous.exists():
                        raise SpeiiError("There is no previous release to roll back to.")
                    metadata = read_json(release.site / "previous.json", None)
                    if metadata:
                        previous = Service.model_validate(metadata)
                        for field in (
                            "command",
                            "health",
                            "isolation",
                            "image",
                            "resources",
                            "env_allow",
                            "streaming",
                            "strict_dependencies",
                            "custom_command",
                            "build_command",
                            "framework",
                            "environment_dir",
                        ):
                            setattr(service, field, getattr(previous, field))
                    if release.candidate.exists():
                        shutil.rmtree(release.candidate)
                    shutil.copytree(release.previous, release.candidate, symlinks=True)
                    check_budget(self.store, release.site)
                else:
                    self.stage(service, release, build_front=True, install=install)
            except Exception:
                if release.candidate.exists():
                    shutil.rmtree(release.candidate)
                self.cleanup_environments(original)
                raise
            services = {k: v.model_copy(deep=True) for k, v in old.items()}
            service.generation = original.generation + 2
            transaction = Transaction(self.store, service, old)
            transaction.begin()
            try:
                transaction.phase(Phase.PROMOTING)
                if original.status == "running" and original.command:
                    self.pause(original, services)
                release.promote()
                service.generation = services[service.name].generation + 1
                services[service.name] = service
                self.routing(services, old, remote=False)
                self.store.save_services(services)
                if service.status == "running":
                    ensure_daemon(self.store)
                    wait_service(self.store, service)
            except Exception:
                self.pause(service, services)
                recover(self.store)
                original = self.store.resolve(original.name)
                if original.status == "running":
                    ensure_daemon(self.store)
                    wait_service(self.store, original)
                self.cleanup_environments(original)
                raise
            # Promotion is committed. A backup cleanup failure must never undo a
            # healthy release after its old dependencies have already been trimmed.
            write_json(release.site / "previous.json", original.model_dump(mode="json"))
            transaction.phase(Phase.COMMITTED)
            transaction.finish()
            self.cleanup_environments(service)
            return service

    def release_configuration(self, original: Service) -> Service:
        from .project_config import load

        service = original.model_copy(deep=True)
        if not (service.source / "speiihosting.toml").exists():
            return service
        config = load(service.source, service.type)
        for name in (
            "health",
            "env_allow",
            "isolation",
            "image",
            "resources",
            "streaming",
            "strict_dependencies",
        ):
            if name in config.model_fields_set:
                setattr(service, name, getattr(config, name))
        if "run" in config.model_fields_set:
            service.custom_command = config.run
        if "build" in config.model_fields_set:
            service.build_command = config.build
        return service

    def cleanup_environments(self, service: Service) -> None:
        previous = read_json(self.store.site(service.name) / "previous.json", {})
        keep = {str(service.environment_dir), str(previous.get("environment_dir"))}
        root = self.store.site(service.name) / "environments"
        if root.exists():
            for path in root.iterdir():
                if str(path) not in keep:
                    shutil.rmtree(path)

    def lifecycle(self, identifier: str, action: str) -> Service:
        with self.lock():
            old = self.store.services()
            service = self.store.resolve(identifier)
            service.status = "stopped" if action == "stop" else "running"
            service.public_verified = False
            service.generation += 1
            services = {**old, service.name: service}
            try:
                self.routing(services, old)
                self.store.save_services(services)
                if service.status == "running":
                    ensure_daemon(self.store)
                if alive(self.store, "speii-daemon"):
                    wait_service(self.store, service, running=service.status == "running")
            except Exception:
                self.store.save_services(old)
                self.routing(old, services)
                raise
            return service

    def link(self, frontend: str, backend: str, prefix: str) -> None:
        with self.lock():
            services = self.store.services()
            front = self.store.resolve(frontend)
            back = self.store.resolve(backend)
            if front.type not in {"frontend", "dynamic"} or back.type != "backend":
                raise SpeiiError("Link requires a frontend/dynamic site and a backend.")
            front.backend, front.api_prefix = back.name, prefix
            services[front.name] = front
            self.routing(services, self.store.services(), remote=False)
            self.store.save_services(services)

    def remove(self, identifier: str, purge_data: bool = False) -> None:
        with self.lock():
            old = self.store.services()
            service = self.store.resolve(identifier)
            links = [s.name for s in old.values() if s.backend == service.name]
            if links:
                raise SpeiiError(
                    "Backend is linked to "
                    + ", ".join(links)
                    + "; remove or relink these sites first."
                )
            services = dict(old)
            self.pause(service, services)
            services.pop(service.name)
            try:
                self.routing(services, old)
                if service.full_domain and self.store.settings().tunnel_mode == "remote":
                    client = cloudflare.Cloudflare(self.store.settings())
                    try:
                        client.unbind(service)
                    finally:
                        client.close()
                self.store.save_services(services)
            except Exception:
                self.store.save_services(old)
                self.routing(old, services)
                raise
            site = self.store.site(service.name)
            if site.exists():
                data = site / "data"
                if purge_data or not data.exists() or not any(data.iterdir()):
                    shutil.rmtree(site)
                else:
                    for path in site.iterdir():
                        if path != data:
                            if path.is_dir() and not path.is_symlink():
                                shutil.rmtree(path)
                            else:
                                path.unlink()
            for path in (self.store.home / "logs").glob(service.name + ".log*"):
                path.unlink()
            for path in (self.store.home / "logs").glob(service.name + ".build.log*"):
                path.unlink()

    def unlink(self, identifier: str) -> None:
        with self.lock():
            services = self.store.services()
            service = self.store.resolve(identifier)
            if service.type not in {"frontend", "dynamic"}:
                raise SpeiiError("Only a frontend or dynamic app has a linked API route.")
            service.backend = None
            services[service.name] = service
            self.routing(services, self.store.services(), remote=False)
            self.store.save_services(services)
