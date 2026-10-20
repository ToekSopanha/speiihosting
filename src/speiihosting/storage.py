from __future__ import annotations

import json
import os
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path

from pydantic import ValidationError

from .config import Service, Settings, SpeiiError, valid_name


def atomic_write(path: Path, data: str | bytes, *, durable: bool = True) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data.encode() if isinstance(data, str) else data)
            handle.flush()
            if durable:
                os.fsync(handle.fileno())
        os.replace(name, path)
        if durable and os.name != "nt":
            descriptor = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def write_json(path: Path, value: object, *, durable: bool = True) -> None:
    atomic_write(path, json.dumps(value, indent=2) + "\n", durable=durable)


def read_json(path: Path, default: object = None):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default
    except (ValueError, OSError) as error:
        raise SpeiiError(
            f"Cannot read {path}: {error}. Restore a valid file before continuing."
        ) from error


@contextmanager
def file_lock(path: Path, timeout: float = 30):
    """An OS lock, released even when a CLI or supervisor crashes."""
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with path.open("a+b") as handle:
        if handle.tell() == 0:
            handle.write(b"\0")
            handle.flush()
        deadline = time.monotonic() + timeout
        while True:
            try:
                if os.name == "nt":
                    import msvcrt

                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise SpeiiError(
                        f"Another Speii process holds {path.name}; try again."
                    ) from None
                time.sleep(0.05)
        try:
            yield
        finally:
            if os.name == "nt":
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


class Store:
    def __init__(self, home: Path | None = None, *, create: bool = True):
        self._cache: dict[str, tuple[tuple, object]] = {}
        self.home = (
            (home or Path(os.environ.get("SPEIIHOSTING_HOME", "~/.speiihosting")))
            .expanduser()
            .resolve()
        )
        if create:
            self.home.mkdir(parents=True, exist_ok=True, mode=0o700)
            if os.name != "nt":
                self.home.chmod(0o700)
            for directory in ("bin", "pids", "logs", "sites", "nginx", "nginx/speiihosting.d"):
                (self.home / directory).mkdir(parents=True, exist_ok=True, mode=0o700)

    def lock(self):
        return file_lock(self.home / "state.lock")

    def cached_json(self, name: str, default):
        import copy

        path = self.home / name
        try:
            stat = path.stat()
            stamp = (stat.st_mtime_ns, stat.st_size, stat.st_ino)
        except FileNotFoundError:
            return copy.deepcopy(default)
        cached = self._cache.get(name)
        if not cached or cached[0] != stamp:
            cached = (stamp, read_json(path, default))
            self._cache[name] = cached
        return copy.deepcopy(cached[1])

    def settings(self) -> Settings:
        try:
            from .security import credentials

            raw = self.cached_json("config.json", {})
            if not isinstance(raw, dict) or raw.get("schema_version", 1) not in {1, 2}:
                raise ValueError("unsupported schema version")
            raw["schema_version"] = 2
            provider = raw.get("credential_store", "file")
            if provider == "file":
                values = self.cached_json("credentials.json", {})
                if not isinstance(values, dict):
                    raise ValueError("invalid credentials")
            else:
                stamp = self._cache.get("config.json", ((),))[0]
                key = "keyring:" + repr(stamp)
                if key not in self._cache:
                    self._cache[key] = ((), credentials(self.home, provider).read())
                values = self._cache[key][1]
            for key in ("cloudflare_api_token", "tunnel_token"):
                if key in values:
                    raw[key] = values[key]
            return Settings.model_validate(raw)
        except (ValidationError, ValueError, TypeError) as error:
            # Pydantic's full error text can include tokens; never print its inputs.
            raise SpeiiError("Invalid config.json. Check its field names and values.") from error

    def save_settings(self, settings: Settings) -> None:
        from .security import credentials

        credentials(self.home, settings.credential_store).write(
            {
                key: secret.get_secret_value()
                for key in ("cloudflare_api_token", "tunnel_token")
                if (secret := getattr(settings, key)) is not None
            }
        )
        write_json(self.home / "config.json", settings.disk_data())

    def services(self) -> dict[str, Service]:
        try:
            raw = self.cached_json("services.json", {})
            if not isinstance(raw, dict):
                raise ValueError("expected an object")
            for value in raw.values():
                if not isinstance(value, dict) or value.get("schema_version", 1) not in {1, 2}:
                    raise ValueError("unsupported schema version")
                value["schema_version"] = 2
            services = {key: Service.model_validate(value) for key, value in raw.items()}
            if any(key != service.name for key, service in services.items()):
                raise ValueError("service keys must match names")
            return services
        except (ValidationError, ValueError, TypeError) as error:
            raise SpeiiError(
                "Invalid services.json; check the service names and values."
            ) from error

    def save_services(self, services: dict[str, Service]) -> None:
        ports = [s.port for s in services.values() if s.port is not None]
        domains = [s.full_domain for s in services.values() if s.full_domain]
        if len(set(ports)) != len(ports) or len(set(domains)) != len(domains):
            raise SpeiiError("Service ports and public hostnames must be unique.")
        write_json(
            self.home / "services.json", {k: v.model_dump(mode="json") for k, v in services.items()}
        )
        write_json(
            self.home / "registry.json",
            {str(s.port): s.name for s in services.values() if s.port is not None},
        )

    def migrate(self) -> None:
        """Version 1 is upgraded in memory on read; persist only under the CLI lock."""
        with self.lock():
            self.save_settings(self.settings())
            self.save_services(self.services())

    def site(self, name: str) -> Path:
        return self.home / "sites" / valid_name(name)

    def resolve(self, identifier: str | None, cwd: Path | None = None) -> Service:
        services = self.services()
        if identifier in services:
            return services[identifier]
        if identifier and identifier.isdigit():
            matches = [s for s in services.values() if s.port == int(identifier)]
        elif identifier:
            matches = []
        else:
            current = (cwd or Path.cwd()).resolve()
            matches = [
                s for s in services.values() if s.source == current or s.source in current.parents
            ]
        if len(matches) != 1:
            raise SpeiiError("Specify a unique service name or port (see speiihos list).")
        return matches[0]
