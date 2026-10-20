"""Runtime adapters: trusted native processes and optional rootless containers."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .config import Service, SpeiiError
from .security import app_values, safe_environment
from .storage import Store, atomic_write


@dataclass
class LaunchSpec:
    command: list[str]
    cwd: Path
    env: dict[str, str]


class RuntimeAdapter(Protocol):
    def validate(self, service: Service) -> None: ...
    def launch(self, store: Store, service: Service) -> LaunchSpec: ...
    def stop(self, store: Store, service: Service) -> None: ...


class ProcessRuntime:
    def validate(self, service: Service) -> None:
        if hasattr(os, "geteuid") and os.geteuid() == 0:
            raise SpeiiError("Run hosted applications under a non-root user account.")

    def launch(self, store: Store, service: Service) -> LaunchSpec:
        from .process import command_for, environment

        self.validate(service)
        live = store.site(service.name) / "live"
        (live.parent / "data").mkdir(exist_ok=True, mode=0o700)
        return LaunchSpec(command_for(service), live, environment(service, live))

    def stop(self, store: Store, service: Service) -> None:
        pass


class PodmanRuntime:
    def binary(self) -> str:
        value = shutil.which("podman")
        if not value:
            raise SpeiiError("Install rootless Podman to use --isolation podman.")
        return value

    def validate(self, service: Service) -> None:
        if platform.system() != "Linux":
            raise SpeiiError("The rootless Podman adapter currently requires Linux with cgroup v2.")
        if not service.image:
            raise SpeiiError(
                "Podman isolation requires an image pinned by --image registry/name@sha256:..."
            )
        result = subprocess.run(
            [self.binary(), "info", "--format=json"],
            capture_output=True,
            text=True,
            timeout=15,
            env=safe_environment(),
        )
        try:
            host = json.loads(result.stdout)["host"]
            if (
                result.returncode
                or not host["security"]["rootless"]
                or host.get("cgroupVersion") != "v2"
                or not {"cpu", "memory", "pids"}.issubset(set(host.get("cgroupControllers", [])))
            ):
                raise ValueError("rootless cgroup v2 required")
        except (ValueError, KeyError, TypeError):
            raise SpeiiError(
                "Podman must run rootless with cgroup v2 resource controllers."
            ) from None

    @staticmethod
    def owner(store: Store) -> str:
        return hashlib.sha256(str(store.home).encode()).hexdigest()

    def name(self, store: Store, service: Service) -> str:
        return f"speii-{self.owner(store)[:12]}-{service.name}-{service.generation}"

    def launch(self, store: Store, service: Service) -> LaunchSpec:
        self.validate(service)
        site = store.site(service.name)
        live, data = site / "live", site / "data"
        data.mkdir(exist_ok=True, mode=0o700)
        if any("," in str(p) for p in (live, data)):
            raise SpeiiError("Container bind-mount paths cannot contain commas.")
        command = [
            self.binary(),
            "run",
            "--rm",
            "--init",
            "--pull=missing",
            "--name",
            self.name(store, service),
            "--label",
            f"io.speiihosting.owner={self.owner(store)}",
            "--label",
            f"io.speiihosting.service={service.name}",
            "--read-only",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges",
            "--userns=keep-id",
            "--user",
            f"{os.getuid()}:{os.getgid()}",
            "--pids-limit",
            str(service.resources.pids),
            "--memory",
            f"{service.resources.memory_mb}m",
            "--cpus",
            str(service.resources.cpus),
            "--log-driver=none",
            "--workdir=/app",
            "--tmpfs=/tmp:rw,nosuid,nodev,size=64m",
            "--mount",
            f"type=bind,src={live},destination=/app,ro=true",
            "--mount",
            f"type=bind,src={data},destination=/data",
        ]
        if service.port:
            command += ["--publish", f"127.0.0.1:{service.port}:{service.port}"]
        app_env = {
            key: value
            for key, value in safe_environment(service.env_allow).items()
            if key in service.env_allow
        }
        app_env.update(app_values(live / ".env"))
        app_env.update(
            HOME="/tmp",
            HOST="0.0.0.0",
            HOSTNAME="0.0.0.0",
            NITRO_HOST="0.0.0.0",
            SPEII_DATA_DIR="/data",
            PYTHONUNBUFFERED="1",
        )
        if service.port:
            app_env["PORT"] = app_env["NITRO_PORT"] = str(service.port)
        if any("\n" in value or "\r" in value or "\0" in value for value in app_env.values()):
            raise SpeiiError(
                "Container environment values must be single-line; put multiline secrets in a private data file."
            )
        env_file = site / f".container-env-{service.generation}"
        atomic_write(
            env_file,
            "".join(f"{key}={value}\n" for key, value in sorted(app_env.items())),
            durable=False,
        )
        command.extend(["--env-file", str(env_file)])
        command.append(service.image)
        if service.command != ["{image}"]:
            command.extend(service.command)
        return LaunchSpec(command, store.home, safe_environment())

    def stop(self, store: Store, service: Service) -> None:
        binary = self.binary()
        name = self.name(store, service)
        result = subprocess.run(
            [binary, "inspect", name],
            capture_output=True,
            text=True,
            timeout=10,
            env=safe_environment(),
        )
        if result.returncode:
            (store.site(service.name) / f".container-env-{service.generation}").unlink(
                missing_ok=True
            )
            return
        try:
            labels = json.loads(result.stdout)[0]["Config"]["Labels"]
            if (
                labels.get("io.speiihosting.owner") != self.owner(store)
                or labels.get("io.speiihosting.service") != service.name
            ):
                raise SpeiiError("Refusing to stop a container not owned by this service.")
        except (ValueError, KeyError, TypeError, IndexError):
            raise SpeiiError("Cannot verify container ownership before stopping it.") from None
        subprocess.run(
            [binary, "stop", "--time=5", name],
            capture_output=True,
            timeout=15,
            env=safe_environment(),
            check=True,
        )
        (store.site(service.name) / f".container-env-{service.generation}").unlink(missing_ok=True)


def adapter(service: Service) -> RuntimeAdapter:
    return PodmanRuntime() if service.isolation == "podman" else ProcessRuntime()
