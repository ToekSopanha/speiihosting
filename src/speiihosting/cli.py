from __future__ import annotations

import functools
import json
import os
import platform
import shutil
import socket
import subprocess
import time
from contextvars import ContextVar
from pathlib import Path
from typing import Annotated

import httpx
import typer
from pydantic import ValidationError
from rich.console import Console
from rich.table import Table

from . import __version__, cloudflare, doctor, power, startup
from .config import HealthCheck, Resources, Service, SpeiiError
from .inspection import describe
from .log_reader import LogReader
from .manager import Manager
from .nginx import Nginx
from .process import alive, ensure_daemon, stop_daemon
from .storage import Store, read_json

app = typer.Typer(
    no_args_is_help=True,
    help="Host websites, local APIs and bots on your computer.",
    pretty_exceptions_enable=False,
)
config_app = typer.Typer(invoke_without_command=True, help="View and change global settings.")
service_app = typer.Typer(help="Manage the supervisor and all hosted services.")
app.add_typer(config_app, name="config")
app.add_typer(service_app, name="service")
project_app = typer.Typer(help="Create and validate speiihosting.toml project manifests.")
app.add_typer(project_app, name="project")
console = Console(highlight=False)
_OPTIONS: ContextVar[dict] = ContextVar("speii_cli_options", default={})


def global_option(name: str) -> bool:
    return bool(_OPTIONS.get().get(name))


def emit(value: dict | list, json_output: bool = False) -> None:
    if json_output or global_option("json"):
        typer.echo(json.dumps(value, default=str))
    else:
        console.print_json(json.dumps(value, default=str))


def guarded(function):
    @functools.wraps(function)
    def wrapper(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except (SpeiiError, OSError, httpx.HTTPError, subprocess.SubprocessError) as error:
            if kwargs.get("json_output") or global_option("json"):
                emit({"error": str(error)}, True)
            else:
                console.print(f"Error: {error}", style="red", markup=False)
            raise typer.Exit(1) from None
        except (ValidationError, ValueError):
            message = "Invalid input. Check names, domains, ports and setting values."
            if kwargs.get("json_output") or global_option("json"):
                emit({"error": message}, True)
            else:
                console.print(message, style="red")
            raise typer.Exit(2) from None

    return wrapper


def report(service: Service, json_output: bool = False) -> None:
    warnings = []
    try:
        register_startup(Store())
    except (SpeiiError, OSError) as error:
        warnings.append(f"Service is active; autostart registration failed: {error}")
    if json_output or global_option("json"):
        emit({**describe(Store(), service), "warnings": warnings}, True)
        return
    console.print(f"{service.name}: active ({service.framework})", style="green", markup=False)
    if service.full_domain:
        console.print(f"Public URL (not verified): https://{service.full_domain}", markup=False)
    elif service.port:
        console.print(f"Local service: http://127.0.0.1:{service.port}", markup=False)
    else:
        console.print("Outbound worker; no domain or port required.")
    console.print(f"Source: {service.source}", markup=False)
    for warning in warnings:
        console.print(warning, style="yellow", markup=False)
    if service.backend:
        console.print(
            f"Exposed API route: {service.api_prefix} → {service.backend}; application authorization is required.",
            markup=False,
        )
    elif service.type == "backend":
        for route in describe(Store(), service, disk=False)["routes"]:
            if route.get("public"):
                console.print(
                    f"Exposed API route: {route['url']}; application authorization is required.",
                    markup=False,
                )


def register_startup(store: Store) -> None:
    if store.settings().autostart and not startup.installed():
        startup.configure(store, True)


@app.callback(invoke_without_command=True)
def root(
    ctx: typer.Context,
    version: Annotated[bool, typer.Option("--version", is_eager=True)] = False,
    json_output: bool = typer.Option(False, "--json"),
    non_interactive: bool = False,
):
    ctx.ensure_object(dict)
    ctx.obj.update({"json": json_output, "non_interactive": non_interactive})
    _OPTIONS.set(ctx.obj)
    if version:
        console.print(__version__)
        raise typer.Exit()


@app.command("doctor")
@guarded
def doctor_command(
    install: bool = typer.Option(False, "--install", help="Install missing Nginx/cloudflared."),
):
    """Audit dependencies, account configuration and startup registration."""
    store = Store()
    if install:
        doctor.install_missing(store)
    table = Table("Component", "Status", "Details")
    for name, ok, detail in doctor.audit(store):
        table.add_row(name, "OK" if ok else "MISSING / INACTIVE", detail)
    console.print(table)


@app.command("init")
@guarded
def initialize(
    domain: str | None = None,
    browser: bool = False,
    install: bool = typer.Option(True, "--install/--no-install"),
    autostart: bool = typer.Option(True, "--autostart/--no-autostart"),
    nginx_port: int = typer.Option(8080, min=1, max=65535),
):
    """Install dependencies and configure a Cloudflare API token or browser login."""
    store = Store()
    with store.lock():
        settings = store.settings()
        if install:
            doctor.install_missing(store)
        for name in ("nginx", "cloudflared"):
            if not doctor.find_binary(name, store):
                raise SpeiiError(f"{name} missing; run doctor --install.")
        settings.nginx_port, settings.autostart = nginx_port, autostart
        token = os.environ.get("CLOUDFLARE_API_TOKEN")
        if not token and settings.cloudflare_api_token:
            token = settings.cloudflare_api_token.get_secret_value()
        if global_option("non_interactive") and (browser or not token):
            raise SpeiiError(
                "Noninteractive setup requires CLOUDFLARE_API_TOKEN and --domain when several zones exist."
            )
        if not browser and not token:
            token = typer.prompt(
                "Cloudflare API token (blank for browser login)",
                default="",
                hide_input=True,
                show_default=False,
            )
        if token and not browser:
            settings.cloudflare_api_token = token
            client = cloudflare.Cloudflare(settings)
            try:
                zones = client.zones()
                if not zones:
                    raise SpeiiError(
                        "No zones available; add your domain to Cloudflare and grant Zone Read/DNS Edit."
                    )
                if domain:
                    matches = [z for z in zones if z["name"] == domain.lower().rstrip(".")]
                    if len(matches) != 1:
                        raise SpeiiError("That domain is not accessible to this token.")
                    zone = matches[0]
                else:
                    if global_option("non_interactive") and len(zones) != 1:
                        raise SpeiiError(
                            "Noninteractive setup with several zones requires --domain."
                        )
                    for index, zone in enumerate(zones, 1):
                        console.print(f"{index}. {zone['name']}", markup=False)
                    choice = (
                        1
                        if global_option("non_interactive")
                        else typer.prompt("Domain number", default=1, type=int)
                    )
                    if not 1 <= choice <= len(zones):
                        raise SpeiiError("Invalid domain selection.")
                    zone = zones[choice - 1]
                if settings.tunnel_id and settings.cloudflare_account_id != zone["account"]["id"]:
                    raise SpeiiError(
                        "Existing tunnel belongs to another account. Use a separate SPEIIHOSTING_HOME."
                    )
                settings.default_domain = zone["name"]
                settings.cloudflare_account_id = zone["account"]["id"]
                settings.tunnel_name = f"speiihosting-{socket.gethostname()}"[:63]
                if not settings.tunnel_id or settings.tunnel_mode != "remote":
                    client.create_tunnel()
                else:
                    settings.tunnel_token = client.request("GET", client.tunnel_path + "/token")[
                        "result"
                    ]
                settings.tunnel_mode = "remote"
                store.save_settings(settings)
                client.configure(store.services(), store)
            finally:
                client.close()
        else:
            binary = doctor.find_binary("cloudflared", store)
            if subprocess.run([binary, "tunnel", "login"]).returncode:
                raise SpeiiError("Cloudflare browser login failed.")
            settings.default_domain = domain or typer.prompt("Root domain on Cloudflare")
            settings.tunnel_mode = "local"
            if not settings.tunnel_id or not settings.tunnel_credentials:
                settings.tunnel_name = f"speiihosting-{socket.gethostname()}"[:63]
                credentials = store.home / "tunnel-credentials.json"
                cloudflare.local_command(
                    store,
                    "tunnel",
                    "--credentials-file",
                    str(credentials),
                    "create",
                    settings.tunnel_name,
                )
                data = read_json(credentials)
                settings.tunnel_id = data["TunnelID"]
                settings.tunnel_credentials = credentials
                settings.cloudflare_account_id = data["AccountTag"]
            store.save_settings(settings)
            cloudflare.configure_local(store, store.services())
        Nginx(store).apply(store.services())
        if autostart:
            register_startup(store)
        ensure_daemon(store)
    console.print("Ready to host. Sleep prevention is off until explicitly enabled.", style="green")


app.command("setup", hidden=True)(initialize)


def execute_host(kind: str, arguments: dict):
    from .project_config import options, preview

    values = arguments.copy()
    config_path = values.pop("config", None)
    dry_run = values.pop("dry_run", False)
    json_output = values.pop("json_output", False)
    health_path = values.pop("health_path", None)
    health_status = values.pop("health_status", None)
    health_body = values.pop("health_body", None)
    startup_timeout = values.pop("startup_timeout", None)
    memory_mb = values.pop("memory_mb", None)
    cpus = values.pop("cpus", None)
    pids = values.pop("pids", None)
    if values.get("env_allow") == []:
        values["env_allow"] = None
    source = Path.cwd().resolve()
    values = options(source, kind, values, config_path)
    if any(
        value is not None for value in (health_path, health_status, health_body, startup_timeout)
    ):
        health = values.get("health") or HealthCheck()
        update = {
            key: value
            for key, value in {
                "path": health_path,
                "expected_status": health_status,
                "expected_body": health_body,
                "startup_timeout": startup_timeout,
            }.items()
            if value is not None
        }
        values["health"] = HealthCheck.model_validate({**health.model_dump(), **update})
    if any(value is not None for value in (memory_mb, cpus, pids)):
        resource = values.get("resources") or Resources()
        update = {
            key: value
            for key, value in {"memory_mb": memory_mb, "cpus": cpus, "pids": pids}.items()
            if value is not None
        }
        values["resources"] = Resources.model_validate({**resource.model_dump(), **update})
    store = Store(create=not dry_run)
    if dry_run:
        emit(preview(store, source, kind, values), json_output)
        return
    report(Manager(store).host(kind, source, **values), json_output)


@app.command("host-front")
@guarded
def host_front(
    subdomain: str | None = None,
    directory: Path | None = typer.Option(None, "--dir"),
    domain: str | None = None,
    name: str | None = None,
    backend: str | None = None,
    build: str | None = None,
    config: Path | None = None,
    dry_run: bool = False,
    json_output: bool = typer.Option(False, "--json"),
    strict_dependencies: bool | None = typer.Option(
        None, "--strict-dependencies/--no-strict-dependencies"
    ),
    reuse_data: bool | None = typer.Option(None, "--reuse-data/--no-reuse-data"),
):
    """Publish static files; API exposure requires an explicit backend link."""
    execute_host("frontend", locals())


@app.command("host-dynamic")
@guarded
def host_dynamic(
    subdomain: str | None = None,
    port: int | None = typer.Option(None, min=1, max=65535),
    domain: str | None = None,
    name: str | None = None,
    run: str | None = None,
    build: str | None = None,
    backend: str | None = None,
    auto_port: bool | None = typer.Option(None, "--auto-port/--no-auto-port"),
    install: bool | None = typer.Option(None, "--install/--no-install"),
    config: Path | None = None,
    dry_run: bool = False,
    json_output: bool = typer.Option(False, "--json"),
    health_path: str | None = None,
    health_status: int | None = typer.Option(None, min=100, max=599),
    health_body: str | None = None,
    startup_timeout: float | None = typer.Option(None, min=2, max=600),
    env_allow: list[str] | None = typer.Option(None, "--env-allow"),
    isolation: str | None = None,
    image: str | None = None,
    memory_mb: int | None = typer.Option(None, min=32),
    cpus: float | None = typer.Option(None, min=0.1),
    pids: int | None = typer.Option(None, min=16),
    streaming: bool | None = typer.Option(None, "--streaming/--no-streaming"),
    strict_dependencies: bool | None = typer.Option(
        None, "--strict-dependencies/--no-strict-dependencies"
    ),
    reuse_data: bool | None = typer.Option(None, "--reuse-data/--no-reuse-data"),
):
    """Build and supervise a dynamic app with health checks and explicit routing."""
    execute_host("dynamic", locals())


app.command("host-app")(host_dynamic)


@app.command("host-back")
@guarded
def host_back(
    port: int | None = typer.Option(None, min=1, max=65535),
    name: str | None = None,
    run: str | None = None,
    frontend: str | None = None,
    auto_port: bool | None = typer.Option(None, "--auto-port/--no-auto-port"),
    existing: bool | None = typer.Option(None, "--existing/--managed"),
    install: bool | None = typer.Option(None, "--install/--no-install"),
    config: Path | None = None,
    dry_run: bool = False,
    json_output: bool = typer.Option(False, "--json"),
    health_path: str | None = None,
    health_status: int | None = typer.Option(None, min=100, max=599),
    health_body: str | None = None,
    startup_timeout: float | None = typer.Option(None, min=2, max=600),
    env_allow: list[str] | None = typer.Option(None, "--env-allow"),
    isolation: str | None = None,
    image: str | None = None,
    memory_mb: int | None = typer.Option(None, min=32),
    cpus: float | None = typer.Option(None, min=0.1),
    pids: int | None = typer.Option(None, min=16),
    strict_dependencies: bool | None = typer.Option(
        None, "--strict-dependencies/--no-strict-dependencies"
    ),
    reuse_data: bool | None = typer.Option(None, "--reuse-data/--no-reuse-data"),
):
    """Host a private local API; --frontend explicitly exposes its /api route."""
    execute_host("backend", locals())


@app.command("host-bot")
@guarded
def host_bot(
    name: str | None = None,
    run: str | None = None,
    webhook: bool | None = typer.Option(None, "--webhook/--polling"),
    port: int | None = typer.Option(None, min=1, max=65535),
    subdomain: str | None = None,
    domain: str | None = None,
    install: bool | None = typer.Option(None, "--install/--no-install"),
    config: Path | None = None,
    dry_run: bool = False,
    json_output: bool = typer.Option(False, "--json"),
    health_path: str | None = None,
    health_status: int | None = typer.Option(None, min=100, max=599),
    health_body: str | None = None,
    startup_timeout: float | None = typer.Option(None, min=2, max=600),
    env_allow: list[str] | None = typer.Option(None, "--env-allow"),
    isolation: str | None = None,
    image: str | None = None,
    memory_mb: int | None = typer.Option(None, min=32),
    cpus: float | None = typer.Option(None, min=0.1),
    pids: int | None = typer.Option(None, min=16),
    strict_dependencies: bool | None = typer.Option(
        None, "--strict-dependencies/--no-strict-dependencies"
    ),
    reuse_data: bool | None = typer.Option(None, "--reuse-data/--no-reuse-data"),
):
    """Host an outbound bot or explicitly expose a webhook endpoint."""
    execute_host("bot", locals())


@app.command()
@guarded
def deploy(
    name: str | None = None,
    install: bool = typer.Option(True, "--install/--no-install"),
    dry_run: bool = False,
    json_output: bool = typer.Option(False, "--json"),
):
    """Deploy from the registered source directory, keeping one rollback release."""
    store = Store(create=not dry_run)
    if dry_run:
        from .project_config import preview

        service = store.resolve(name)
        service = Manager(store).release_configuration(service)
        values = {
            "name": service.name,
            "port": service.port,
            "run": service.custom_command,
            "build": service.build_command,
            "backend": service.backend,
            "directory": Path(service.static_dir) if service.static_dir else None,
            "subdomain": "@" if service.full_domain else None,
            "domain": service.full_domain,
            "health": service.health,
            "env_allow": service.env_allow,
            "isolation": service.isolation,
            "image": service.image,
            "resources": service.resources,
            "install": install,
            "strict_dependencies": service.strict_dependencies,
        }
        emit(
            {
                **preview(store, service.source, service.type, values),
                "action": "deploy",
                "rollback": "one complete runnable release",
            },
            json_output,
        )
        return
    service = Manager(store).deploy(name, install=install)
    warnings = []
    if service.type == "frontend" and service.zone_id:
        client = cloudflare.Cloudflare(store.settings())
        try:
            client.purge(service)
        except (SpeiiError, httpx.HTTPError):
            warnings.append("Deployment succeeded; cache purge failed. Retry speiihos purge.")
        finally:
            client.close()
    if json_output or global_option("json"):
        emit({**describe(store, service), "action": "deploy", "warnings": warnings}, True)
    else:
        console.print(f"Deployed {service.name}.", style="green", markup=False)
        for warning in warnings:
            console.print(warning, style="yellow")


@app.command()
@guarded
def rollback(
    name: str,
    install: bool = typer.Option(True, "--install/--no-install"),
    dry_run: bool = False,
    json_output: bool = typer.Option(False, "--json"),
):
    """Restore the previous release and retain the replaced version."""
    store = Store(create=not dry_run)
    if dry_run:
        service = store.resolve(name)
        emit(
            {
                "dry_run": True,
                "action": "rollback",
                "name": service.name,
                "previous_available": (store.site(service.name) / "previous").is_dir(),
                "install_dependencies": False,
            },
            json_output,
        )
        return
    service = Manager(store).deploy(name, install=install, rollback=True)
    if json_output or global_option("json"):
        emit({**describe(store, service), "action": "rollback"}, True)
    else:
        console.print(f"Rolled back {service.name}.", style="green", markup=False)


def change_state(name: str, action: str) -> None:
    service = Manager(Store()).lifecycle(name, action)
    console.print(f"{service.name}: {service.status}", markup=False)


@app.command()
@guarded
def start(name: str):
    """Start a registered service (name or port)."""
    change_state(name, "start")


@app.command()
@guarded
def stop(name: str):
    """Stop a registered service (name or port)."""
    change_state(name, "stop")


@app.command()
@guarded
def restart(name: str):
    """Restart a registered service (name or port)."""
    change_state(name, "restart")


@app.command("list")
@guarded
def list_services(json_output: bool = typer.Option(False, "--json"), disk: bool = False):
    """Show services, current process status and resource usage."""
    store = Store()
    descriptions = [describe(store, service, disk=disk) for service in store.services().values()]
    if json_output or global_option("json"):
        emit(descriptions, True)
        return
    runtime = read_json(store.home / "runtime.json", {}) if alive(store, "speii-daemon") else {}
    table = Table("Name", "Type", "Target", "Status", "Health", "Restarts", "CPU", "RAM")
    for service in store.services().values():
        state = runtime.get("services", {}).get(service.name, {})
        target = (
            f"127.0.0.1:{service.port}"
            if service.port
            else str(store.site(service.name) / "live")
            if service.type == "frontend"
            else "outbound"
        )
        table.add_row(
            service.name,
            service.type,
            target,
            state.get("status", "inactive" if service.status == "running" else "stopped"),
            state.get("health", {}).get("status", "unknown"),
            str(state.get("restarts", 0)),
            f"{state.get('cpu', 0):.1f}%",
            f"{state.get('memory', 0) / 1_000_000:.1f} MB",
        )
    console.print(table)


@app.command("inspect")
@guarded
def inspect_service(name: str, json_output: bool = typer.Option(False, "--json")):
    """Inspect routes, health, isolation, process metrics and exact disk consumption."""
    store = Store()
    emit(describe(store, store.resolve(name)), json_output)


@app.command()
@guarded
def recover(json_output: bool = typer.Option(False, "--json")):
    """Restore interrupted deployments from their durable journals."""
    from .transactions import recover as recover_transactions

    store = Store()
    with store.lock():
        names = recover_transactions(store)
    if any(s.status == "running" for s in store.services().values()):
        ensure_daemon(store)
    emit({"recovered": names}, json_output)


@app.command()
@guarded
def migrate(json_output: bool = typer.Option(False, "--json")):
    """Persist the current schema and move legacy tokens out of config.json."""
    Store().migrate()
    emit({"schema_version": 2, "migrated": True}, json_output)


@app.command()
@guarded
def verify(name: str, json_output: bool = typer.Option(False, "--json")):
    """Explicitly check the public HTTPS URL using the application's health criteria."""
    store = Store()
    service = store.resolve(name)
    if not service.full_domain:
        raise SpeiiError("Only a public service has an HTTPS URL to verify.")
    from datetime import datetime, timezone

    from .health import probe_url

    health = service.health or HealthCheck(timeout=10)
    result = probe_url(f"https://{service.full_domain}{health.path}", health)
    ok = result["status"] == "healthy"
    with store.lock():
        current = store.resolve(name)
        if current.generation != service.generation:
            raise SpeiiError(
                "Service changed during verification; retry against the current release."
            )
        current.public_verified = ok
        current.public_verified_at = datetime.now(timezone.utc)
        services = store.services()
        services[current.name] = current
        store.save_services(services)
    emit(
        {"name": service.name, "public_url_verified": ok, "http_status": result.get("http_status")},
        json_output,
    )
    if not ok:
        raise typer.Exit(1)


@project_app.command("init")
@guarded
def project_init(
    type_: str | None = typer.Option(None, "--type"), force: bool = False, dry_run: bool = False
):
    """Generate a project manifest without publishing or installing anything."""
    from .project_config import generate
    from .storage import atomic_write

    path = Path.cwd() / "speiihosting.toml"
    content = generate(Path.cwd(), type_)
    if dry_run:
        typer.echo(content, nl=False)
    elif path.exists() and not force:
        raise SpeiiError("speiihosting.toml already exists; use --force to replace it.")
    else:
        atomic_write(path, content)
        console.print(f"Created {path}", markup=False)


@project_app.command("validate")
@guarded
def project_validate(json_output: bool = typer.Option(False, "--json")):
    """Validate the current project manifest without creating hosting state."""
    from .project_config import ProjectConfig, load, tomllib

    path = Path.cwd() / "speiihosting.toml"
    config = ProjectConfig.model_validate(tomllib.loads(path.read_text(encoding="utf-8")))
    config = load(Path.cwd(), config.type)
    emit({"valid": True, "config": config.model_dump(mode="json", by_alias=True)}, json_output)


@app.command()
@guarded
def link(
    frontend: str,
    backend: str,
    prefix: str = "/api",
    strip_prefix: bool = typer.Option(
        True,
        "--strip-prefix/--preserve-prefix",
        help="Strip the public prefix, or preserve it for backend routes such as /api/projects.",
    ),
):
    """Route a frontend path to a backend; use --preserve-prefix if it expects that prefix."""
    Manager(Store()).link(frontend, backend, prefix, strip_prefix=strip_prefix)
    behavior = "prefix stripped" if strip_prefix else "prefix preserved"
    console.print(f"Linked {frontend}{prefix} → {backend} ({behavior})", markup=False)


@app.command()
@guarded
def unlink(frontend: str):
    """Remove a frontend's API mapping, keeping the backend private and running."""
    Manager(Store()).unlink(frontend)
    console.print(f"Removed API mapping from {frontend}.", markup=False)


@app.command()
@guarded
def remove(name: str, purge_data: bool = False):
    """Remove a service, its releases and owned remote DNS record."""
    Manager(Store()).remove(name, purge_data=purge_data)
    console.print(f"Removed {name}.", markup=False)


def log_paths(store: Store, name: str, build: bool = False) -> list[Path]:
    if build:
        service = store.resolve(name)
        return [store.home / "logs" / (service.name + ".build.log")]
    if name == "nginx":
        return [store.home / "logs" / f"nginx_{part}.log" for part in ("access", "error")]
    if name not in {"speii-daemon", "cloudflared", "power"}:
        name = store.resolve(name).name
    return [store.home / "logs" / (name + ".log")]


def clear_logs(paths: list[Path]) -> None:
    for path in paths:
        # Truncate in place: existing open file descriptors remain usable.
        with path.open("w", encoding="utf-8"):
            pass
        path.with_suffix(".log.1").unlink(missing_ok=True)


@app.command(context_settings={"allow_extra_args": False})
@guarded
def logs(
    name: str,
    target: str | None = typer.Argument(None),
    lines: int = typer.Option(100, "-n", "--lines", min=0),
    follow: bool = typer.Option(False, "-f", "--follow"),
    clear: bool = False,
    all_: bool = typer.Option(False, "--all"),
    build: bool = False,
):
    """Read logs, stream with -f, inspect 'size', or 'clear <name> / --all'."""
    store = Store()
    if name == "size":
        table = Table("Log file", "Bytes", "Lines")
        total = 0
        for path in sorted((store.home / "logs").glob("*.log*")):
            size = path.stat().st_size
            with path.open("rb") as handle:
                count = sum(chunk.count(b"\n") for chunk in iter(lambda: handle.read(65536), b""))
            table.add_row(path.name, str(size), str(count))
            total += size
        console.print(table)
        console.print(f"Total: {total:,} bytes")
        return
    if name == "clear":
        if not target and not all_:
            raise SpeiiError("Specify logs clear <name> or logs clear --all.")
        paths = (
            list((store.home / "logs").glob("*.log")) if all_ else log_paths(store, target, build)
        )
        clear_logs(paths)
        console.print("Logs cleared.")
        return
    if target or all_:
        raise SpeiiError("Unexpected arguments; use logs clear --all to clear every log.")
    paths = log_paths(store, name, build)
    if clear:
        clear_logs(paths)
        return
    readers = [LogReader(path) for path in paths]
    for reader in readers:
        text = reader.read_tail(lines)
        if text:
            if len(paths) > 1:
                console.print(reader.path.name, style="bold", markup=False)
            console.print(text, end="", markup=False, soft_wrap=True)
    if follow:
        Console(stderr=True).print(
            f"Following logs for {name}. Press Ctrl+C to stop; the service keeps running.",
            markup=False,
        )
        try:
            while True:
                for reader in readers:
                    text = reader.read_new()
                    if text:
                        console.print(text, end="", markup=False, soft_wrap=True)
                time.sleep(0.2)
        except KeyboardInterrupt:
            pass


@app.command()
@guarded
def clean(
    name: str | None = None,
    all_: bool = typer.Option(False, "--all"),
    logs_: bool = typer.Option(False, "--logs"),
):
    """Reclaim previous release backups or clear logs."""
    store = Store()
    with Manager(store).lock():
        if logs_:
            clear_logs(list((store.home / "logs").glob("*.log")))
            return
        if not all_ and not name:
            raise SpeiiError("Specify a service name, --all or --logs.")
        services = store.services().values() if all_ else [store.resolve(name)]
        manager = Manager(store)
        for service in services:
            site = store.site(service.name)
            previous = site / "previous"
            if previous.exists():
                shutil.rmtree(previous)
            (site / "previous.json").unlink(missing_ok=True)
            manager.cleanup_environments(service)
    console.print("Backups cleaned.")


@app.command()
@guarded
def purge(name: str):
    """Purge a site's root and index.html from Cloudflare's cache."""
    store = Store()
    if store.settings().tunnel_mode == "local":
        raise SpeiiError("Cache purging requires API-token setup (run init).")
    client = cloudflare.Cloudflare(store.settings())
    try:
        client.purge(store.resolve(name))
    finally:
        client.close()
    console.print("Purged root and index.html. Hashed assets keep their immutable cache.")


@config_app.callback()
@guarded
def config_menu(ctx: typer.Context):
    if ctx.invoked_subcommand is None:
        show_config()
        if not global_option("non_interactive") and typer.confirm(
            "Change a setting?", default=False
        ):
            key = typer.prompt("Setting (domain, nginx_port, autostart, sleep_prevent)")
            set_config(key, typer.prompt("New value"))


@config_app.command("show")
@guarded
def show_config():
    emit(Store().settings().model_dump(mode="json"))


@config_app.command("set")
@guarded
def set_config(key: str, value: str):
    store = Store()
    with store.lock():
        settings = store.settings()
        if key == "domain":
            settings.default_domain = value
        elif key in {"autostart", "sleep_prevent"}:
            if value.lower() not in {"on", "off", "true", "false"}:
                raise SpeiiError("Use on or off for boolean settings.")
            enabled = value.lower() in {"on", "true"}
            if key == "autostart":
                was_running = alive(store, "speii-daemon")
                startup.configure(store, enabled)
                if not enabled and was_running and platform.system() == "Darwin":
                    # bootout can stop a launchd-owned supervisor; disabling
                    # future startup should leave current services available.
                    stop_daemon(store)
                    ensure_daemon(store)
            else:
                power.configure(store, enabled)
            setattr(settings, key, enabled)
        elif key == "nginx_port":
            settings.nginx_port = int(value)
            if any(s.full_domain for s in store.services().values()):
                raise SpeiiError(
                    "Stop/remove public sites before changing nginx_port, then run init --nginx-port."
                )
        elif key == "metrics_interval":
            settings.metrics_interval = float(value)
        elif key == "release_budget_mb":
            settings.release_budget_mb = int(value)
        elif key == "credential_store":
            old_provider = settings.credential_store
            settings.credential_store = value
            # Save to the new backend and publish its selection before removing
            # the old credential copy. A failed write leaves the old store usable.
            store.save_settings(settings)
            if old_provider == "file" and value == "keyring":
                (store.home / "credentials.json").unlink(missing_ok=True)
        else:
            raise SpeiiError(
                "Supported settings: domain, nginx_port, autostart, sleep_prevent, metrics_interval, release_budget_mb, credential_store."
            )
        store.save_settings(settings)
        if key == "sleep_prevent" and settings.sleep_prevent:
            ensure_daemon(store)
    console.print(f"Updated {key}.", markup=False)


@app.command("sleep-prevent")
@guarded
def sleep_prevent(enabled: bool = typer.Option(True, "--on/--off")):
    """Enable or disable this tool's OS sleep prevention setting."""
    set_config("sleep_prevent", "on" if enabled else "off")


@service_app.command("start")
@guarded
def service_start():
    ensure_daemon(Store())
    console.print("Supervisor started; previously active services are being restored.")


@service_app.command("stop")
@guarded
def service_stop():
    stop_daemon(Store())
    console.print("Supervisor and managed processes stopped.")


def main():
    app()
