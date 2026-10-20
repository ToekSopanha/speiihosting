"""Durable promotion intents and deterministic recovery after interrupted renames."""

from __future__ import annotations

import shutil
from enum import Enum
from pathlib import Path

from .config import Service, SpeiiError
from .storage import Store, read_json, write_json


class Phase(str, Enum):
    PREPARED = "prepared"
    PROMOTING = "promoting"
    COMMITTED = "committed"


class Transaction:
    def __init__(self, store: Store, service: Service, old: dict[str, Service]):
        self.store, self.service = store, service
        self.site = store.site(service.name)
        self.path = self.site / "transaction.json"
        self.data = {
            "schema_version": 1,
            "name": service.name,
            "phase": Phase.PREPARED.value,
            "old_services": {k: s.model_dump(mode="json") for k, s in old.items()},
            "new_service": service.model_dump(mode="json"),
            "had_live": (self.site / "live").exists(),
            "had_previous": (self.site / "previous").exists(),
            "previous_metadata": read_json(self.site / "previous.json", None),
        }

    def begin(self) -> None:
        if self.path.exists():
            raise SpeiiError("An interrupted deployment needs recovery before retrying.")
        write_json(self.path, self.data)

    def phase(self, phase: Phase) -> None:
        self.data["phase"] = phase.value
        write_json(self.path, self.data)

    def finish(self) -> None:
        obsolete = self.site / ".obsolete"
        if obsolete.exists():
            shutil.rmtree(obsolete)
        self.path.unlink(missing_ok=True)


def pending(store: Store) -> list[Path]:
    return sorted((store.home / "sites").glob("*/transaction.json"))


def recover(store: Store) -> list[str]:
    """Caller holds state.lock. Invalid/failed recovery keeps its evidence intact."""
    from .isolation import adapter
    from .nginx import Nginx
    from .process import matches, terminate_tree

    recovered = []
    for path in pending(store):
        raw = read_json(path)
        if not isinstance(raw, dict) or raw.get("schema_version") != 1:
            raise SpeiiError(f"Invalid deployment journal: {path}; restore it before recovery.")
        try:
            phase = Phase(raw["phase"])
            service = Service.model_validate(raw["new_service"])
            old = {k: Service.model_validate(value) for k, value in raw["old_services"].items()}
            if any(type(raw.get(key)) is not bool for key in ("had_live", "had_previous")):
                raise ValueError("missing release presence markers")
            if raw.get("previous_metadata") is not None:
                Service.model_validate(raw["previous_metadata"])
            if (
                service.name != path.parent.name
                or raw["name"] != service.name
                or any(k != s.name for k, s in old.items())
            ):
                raise ValueError("journal identity mismatch")
        except (ValueError, KeyError, TypeError) as error:
            raise SpeiiError(
                f"Invalid deployment journal: {path}; no files were changed."
            ) from error
        site = store.site(service.name)
        live, previous = site / "live", site / "previous"
        candidate, obsolete = site / "candidate", site / ".obsolete"
        if phase == Phase.COMMITTED:
            if not live.is_dir():
                raise SpeiiError(
                    f"Committed release is missing in {site}; refusing destructive recovery."
                )
            if obsolete.exists():
                shutil.rmtree(obsolete)
            if candidate.exists():
                shutil.rmtree(candidate)
            path.unlink()
            recovered.append(service.name)
            continue
        record = read_json(store.home / "pids" / (service.name + ".json"), {})
        if service.isolation == "podman":
            adapter(service).stop(store, service)
        if matches(record):
            terminate_tree(record["pid"], record["created"])
        if phase == Phase.PROMOTING:
            if not candidate.exists():
                # The candidate was renamed to live. Move it aside so recovery
                # can safely resume if the next filesystem operation fails.
                if live.exists():
                    live.rename(candidate)
                elif raw["had_live"] and not previous.exists():
                    raise SpeiiError(f"Both live and rollback files are missing in {site}.")
            if raw["had_live"] and not live.exists():
                if not previous.exists():
                    raise SpeiiError(
                        f"Original release is missing in {site}; recovery journal retained."
                    )
                previous.rename(live)
            if obsolete.exists():
                if previous.exists():
                    raise SpeiiError(f"Ambiguous rollback directory in {site}; journal retained.")
                obsolete.rename(previous)
        current = store.services()
        if service.name in old:
            old[service.name].generation = (
                max(
                    service.generation,
                    current.get(service.name, service).generation,
                    old[service.name].generation,
                )
                + 1
            )
        store.save_services(old)
        if any(s.full_domain for s in [*old.values(), service]):
            Nginx(store).apply(old)
            if store.settings().tunnel_mode == "local":
                from .cloudflare import configure_local

                configure_local(store, old)
        metadata = raw.get("previous_metadata")
        if metadata is not None:
            write_json(site / "previous.json", metadata)
        else:
            (site / "previous.json").unlink(missing_ok=True)
        if candidate.exists():
            shutil.rmtree(candidate)
        path.unlink()
        recovered.append(service.name)
    return recovered


def tree_bytes(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(p.stat().st_size for p in path.rglob("*") if p.is_file() and not p.is_symlink())


def check_budget(store: Store, site: Path) -> None:
    limit = store.settings().release_budget_mb * 1024 * 1024
    if (
        sum(
            tree_bytes(site / name)
            for name in ("live", "previous", "candidate", ".obsolete", "environments")
        )
        > limit
    ):
        raise SpeiiError(
            "Release disk budget exceeded. Run clean or increase config release_budget_mb."
        )
    if shutil.disk_usage(site).free < 128 * 1024 * 1024:
        raise SpeiiError("Less than 128 MiB free disk space remains; deployment was not promoted.")
