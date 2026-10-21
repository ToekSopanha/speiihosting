from __future__ import annotations

from .config import Service
from .process import alive
from .storage import Store, read_json
from .transactions import tree_bytes


def describe(store: Store, service: Service, *, disk: bool = True) -> dict:
    runtime = read_json(store.home / "runtime.json", {}) if alive(store, "speii-daemon") else {}
    state = runtime.get("services", {}).get(service.name, {})
    infrastructure = runtime.get("infrastructure", {})
    connected = False
    path = store.home / "pids/tunnel-connected.pid"
    if path.exists():
        try:
            connected = int(path.read_text().strip()) == infrastructure.get("cloudflared", {}).get(
                "pid"
            )
        except (OSError, ValueError):
            pass
    site = store.site(service.name)
    routes = (
        [
            {
                "path": service.api_prefix,
                "strip_prefix": service.api_strip_prefix,
                "backend": service.backend,
                "public": bool(service.full_domain),
            }
        ]
        if service.backend
        else []
    )
    if service.type == "backend":
        routes.extend(
            {
                "frontend": front.name,
                "path": front.api_prefix,
                "strip_prefix": front.api_strip_prefix,
                "public": bool(front.full_domain),
                "url": f"https://{front.full_domain}{front.api_prefix}"
                if front.full_domain
                else None,
            }
            for front in store.services().values()
            if front.backend == service.name
        )
    return {
        "name": service.name,
        "type": service.type,
        "source": str(service.source),
        "env_file": str(store.env_file(service.name)),
        "env_file_present": store.env_file(service.name).is_file(),
        "port": service.port,
        "url": f"https://{service.full_domain}" if service.full_domain else None,
        "desired_status": service.status,
        "status": state.get("status", "inactive" if service.status == "running" else "stopped"),
        "health": state.get(
            "health", {"status": "not_configured" if not service.health else "unknown"}
        ),
        "pid": state.get("pid"),
        "restarts": state.get("restarts", 0),
        "cpu_percent": state.get("cpu", 0),
        "memory_bytes": state.get("memory", 0),
        "isolation": service.isolation,
        "resource_limits": service.resources.model_dump(),
        "metrics_scope": "Podman client process tree; use podman stats for container payload usage"
        if service.isolation == "podman"
        else "native process tree",
        "isolation_boundary": "rootless container"
        if service.isolation == "podman"
        else "trusted code under the current OS user",
        "resource_enforcement": {
            "memory": "cgroup"
            if service.isolation == "podman"
            else "best-effort process-tree RSS monitor",
            "cpus": "cgroup" if service.isolation == "podman" else "not enforced",
            "pids": "cgroup" if service.isolation == "podman" else "not enforced",
        },
        "public_verified_at": service.public_verified_at.isoformat()
        if service.public_verified_at
        else None,
        "data_directory": str(site / "data"),
        "routes": routes,
        "stages": {
            "process_started": state.get("status") == "running",
            "application_health": state.get("health", {}).get("status", "unknown"),
            "connector_process_started": infrastructure.get("cloudflared", {}).get("status")
            == "running"
            if service.full_domain
            else None,
            "tunnel_connected": connected if service.full_domain else None,
            "public_url_verified": service.public_verified if service.full_domain else None,
        },
        "disk_bytes": {
            name: tree_bytes(site / name) for name in ("live", "previous", "data", "environments")
        }
        if disk
        else None,
        "recovery_pending": (site / "transaction.json").exists(),
        "error": state.get("error") or None,
    }
