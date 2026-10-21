"""A validated project manifest; CLI values override only explicitly supplied fields."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .config import HealthCheck, Resources, Service, SpeiiError
from .projects import detect, manifest, project_name, static_candidates

try:
    import tomllib
except ImportError:
    import tomli as tomllib


class ProjectConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[1] = 1
    type: Literal["frontend", "dynamic", "backend", "bot"]
    name: str | None = None
    subdomain: str | None = None
    domain: str | None = None
    port: int | None = Field(default=None, ge=1, le=65535)
    directory: Path | None = Field(default=None, alias="dir")
    run: str | None = None
    build: str | None = None
    backend: str | None = None
    frontend: str | None = None
    existing: bool = False
    reuse_data: bool = False
    auto_port: bool = False
    install: bool = True
    webhook: bool = False
    env_allow: list[str] = Field(default_factory=list)
    health: HealthCheck | None = None
    isolation: Literal["process", "podman"] = "process"
    image: str | None = None
    resources: Resources = Field(default_factory=Resources)
    streaming: bool = False
    strict_dependencies: bool = False


def load(source: Path, kind: str, path: Path | None = None) -> ProjectConfig:
    target = (source / path).resolve() if path else source / "speiihosting.toml"
    if not target.exists() and path is None:
        return ProjectConfig(type=kind)
    try:
        value = ProjectConfig.model_validate(tomllib.loads(target.read_text(encoding="utf-8")))
    except (ValueError, ValidationError, OSError) as error:
        raise SpeiiError(
            f"Invalid project configuration: {target}. Check field names and value types."
        ) from error
    if value.type != kind:
        raise SpeiiError(f"Project type is {value.type}; use the matching host command.")
    # Reuse service validation for all security-sensitive manifest values.
    Service(
        name=value.name or project_name(source, None),
        type=value.type,
        source=source,
        env_allow=value.env_allow,
        image=value.image,
    )
    return value


def options(source: Path, kind: str, overrides: dict, path: Path | None = None) -> dict:
    config = load(source, kind, path)
    result = {
        name: getattr(config, name)
        for name in type(config).model_fields
        if name not in {"schema_version", "type"}
    }
    result.update({key: value for key, value in overrides.items() if value is not None})
    if kind == "dynamic" and not result["port"]:
        result["port"] = 3000
    if kind == "backend" and not result["port"]:
        raise SpeiiError("A backend requires --port or port in speiihosting.toml.")
    if kind in {"frontend", "dynamic"} and not result["subdomain"]:
        raise SpeiiError("Public hosting requires --subdomain or subdomain in speiihosting.toml.")
    webhook = result.pop("webhook")
    if kind == "bot":
        if webhook and (not result["port"] or not result["subdomain"]):
            raise SpeiiError("Webhook mode requires --port and --subdomain.")
        if not webhook and any(result[key] is not None for key in ("port", "subdomain", "domain")):
            raise SpeiiError("Use --webhook to expose a bot port and subdomain.")
    if kind in {"backend", "bot"} and result["backend"]:
        raise SpeiiError("Only frontend/dynamic services can link to a backend.")
    if kind != "backend" and result["frontend"]:
        raise SpeiiError("Only backend services accept frontend links.")
    if kind == "frontend" and result["isolation"] != "process":
        raise SpeiiError(
            "Static files are served by Nginx; container isolation applies to app processes."
        )
    if result["existing"] and kind != "backend":
        raise SpeiiError("Only backend services support --existing.")
    if result["image"] and result["isolation"] != "podman":
        raise SpeiiError("--image requires --isolation podman.")
    if result["health"] and not result["port"]:
        raise SpeiiError("HTTP health checks require a service port.")
    return result


def generate(source: Path, kind: str | None = None) -> str:
    if kind is None:
        deps = manifest(source).get("dependencies", {})
        kind = (
            "bot"
            if (source / "bot.py").exists()
            else "dynamic"
            if "next" in deps or "nuxt" in deps
            else "frontend"
            if static_candidates(source)
            else "backend"
        )
    config = ProjectConfig(type=kind, name=project_name(source, None))
    lines = [
        "schema_version = 1",
        f"type = {json.dumps(kind)}",
        f"name = {json.dumps(config.name)}",
    ]
    if kind in {"frontend", "dynamic"}:
        import re

        lines.append(f"subdomain = {json.dumps(re.sub('[^a-z0-9-]', '-', config.name.lower()))}")
    if kind == "frontend":
        choices = static_candidates(source)
        if len(choices) == 1:
            lines.append(f"dir = {json.dumps(str(choices[0].relative_to(source)))}")
    elif kind != "bot":
        lines.append("port = " + ("3000" if kind == "dynamic" else "8000"))
    lines += [
        "",
        "# Inherit only these additional shell variables. App .env is loaded separately.",
        "env_allow = []",
        "# API exposure requires an explicit backend/frontend link.",
        "strict_dependencies = false",
    ]
    if kind in {"backend", "dynamic"}:
        lines += [
            "",
            "[health]",
            'path = "/"',
            "expected_status = 200",
            "timeout = 2",
            "interval = 5",
            "failures = 3",
            "startup_timeout = 30",
        ]
    return "\n".join(lines) + "\n"


def preview(store, source: Path, kind: str, values: dict) -> dict:
    name = project_name(
        source,
        values.get("name") or (values.get("subdomain") if values.get("subdomain") != "@" else None),
        values.get("port"),
    )
    service = Service(
        name=name,
        type=kind,
        source=source,
        port=values.get("port"),
        custom_command=values.get("run"),
        env_allow=values.get("env_allow", []),
        isolation=values.get("isolation", "process"),
        image=values.get("image"),
        health=values.get("health"),
        resources=values.get("resources", Resources()),
    )
    if kind == "frontend":
        from .projects import static_directory

        command = []
        output = str(static_directory(source, values.get("directory")))
    elif service.isolation == "podman":
        command = [
            "podman",
            "run",
            "<restricted flags>",
            service.image,
            values.get("run") or "<image command>",
        ]
        output = None
    elif values.get("existing"):
        command, output = [], None
    else:
        command, _ = detect(service, source)
        output = None
    subdomain = values.get("subdomain")
    domain = values.get("domain") or store.settings().default_domain or "<configured-domain>"
    url = (
        (f"https://{domain}" if subdomain == "@" else f"https://{subdomain}.{domain}")
        if subdomain is not None
        else None
    )
    routes = []
    if values.get("backend"):
        target = store.resolve(values["backend"])
        if target.type != "backend":
            raise SpeiiError("--backend must identify a backend service.")
        routes.append(
            {"path": "/api", "backend": target.name, "exposure": "public through frontend"}
        )
    if values.get("frontend"):
        target = store.resolve(values["frontend"])
        routes.append(
            {
                "frontend": target.name,
                "path": "/api",
                "backend": name,
                "exposure": "public through frontend",
            }
        )
    return {
        "dry_run": True,
        "name": name,
        "type": kind,
        "source": str(source),
        "env_file": str(store.env_file(name)),
        "env_file_present": store.env_file(name).is_file(),
        "static_output": output,
        "url": url,
        "requested_port": service.port,
        "command": command,
        "build": values.get("build")
        or (
            "npm run build"
            if kind == "dynamic" and "build" in manifest(source).get("scripts", {})
            else None
        ),
        "install_dependencies": values.get("install", True)
        and service.isolation == "process"
        and not values.get("existing"),
        "strict_dependencies": values.get("strict_dependencies", False),
        "routes": routes,
        "isolation": service.isolation,
        "resources": service.resources.model_dump(),
        "health": service.health.model_dump() if service.health else None,
        "env_allow": service.env_allow,
        "checks_on_apply": [
            "port availability",
            "dependency verification",
            "disk budget",
            "runtime isolation",
            "HTTP readiness",
        ],
    }
