from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import zipfile
from importlib.resources import files

import httpx

from .config import SpeiiError
from .storage import Store, atomic_write


def pinned_binaries() -> dict:
    return json.loads(files("speiihosting").joinpath("binaries.json").read_text(encoding="utf-8"))


def verified_download(client: httpx.Client, asset: dict) -> bytes:
    digest = asset.get("sha256", "")
    if not re.fullmatch(r"[a-f0-9]{64}", digest):
        raise SpeiiError("No reviewed SHA-256 checksum is available; use an OS package manager.")
    if not asset.get("url", "").startswith(
        (
            "https://github.com/cloudflare/cloudflared/releases/download/",
            "https://nginx.org/download/",
        )
    ):
        raise SpeiiError("Installer manifest contains an unsupported download source.")
    payload = bytearray()
    with client.stream("GET", asset["url"]) as response:
        response.raise_for_status()
        for block in response.iter_bytes(chunk_size=65536):
            payload.extend(block)
            if len(payload) > 128 * 1024 * 1024:
                raise SpeiiError("Binary download exceeds the 128 MiB limit.")
    if hashlib.sha256(payload).hexdigest() != digest:
        raise SpeiiError("Binary download checksum did not match; nothing was installed.")
    return bytes(payload)


def find_binary(name: str, store: Store) -> str | None:
    suffix = ".exe" if os.name == "nt" else ""
    paths = [store.home / "bin" / (name + suffix)]
    if name == "nginx":
        paths.append(store.home / "bin/nginx/nginx.exe")
    for path in paths:
        if path.is_file():
            return str(path)
    return shutil.which(name)


def audit(store: Store) -> list[tuple[str, bool, str]]:
    settings = store.settings()
    from .process import alive
    from .startup import installed

    return [
        ("Python", sys.version_info >= (3, 10), sys.executable),
        ("pip", importlib.util.find_spec("pip") is not None, "Python dependency installer"),
        *[
            (name, bool(find_binary(name, store)), find_binary(name, store) or "not installed")
            for name in ("nginx", "cloudflared")
        ],
        ("Cloudflare", bool(settings.tunnel_id), settings.default_domain or "run speiihos init"),
        ("Supervisor", alive(store, "speii-daemon"), "speiihos service start"),
        ("Autostart", installed(), "enabled" if installed() else "not registered"),
    ]


def package_commands(name: str, system: str | None = None) -> list[list[str]]:
    system = system or platform.system()
    if system == "Darwin" and shutil.which("brew"):
        return [["brew", "install", name]]
    if system == "Windows" and shutil.which("winget"):
        if name == "cloudflared":
            return [
                [
                    "winget",
                    "install",
                    "--id",
                    "Cloudflare.cloudflared",
                    "--exact",
                    "--accept-source-agreements",
                    "--accept-package-agreements",
                ]
            ]
    if system == "Linux" and name == "nginx":
        prefix = [] if os.geteuid() == 0 else ["sudo"]
        if shutil.which("apt-get"):
            return [[*prefix, "apt-get", "update"], [*prefix, "apt-get", "install", "-y", "nginx"]]
        if shutil.which("dnf"):
            return [[*prefix, "dnf", "install", "-y", "nginx"]]
    return []


def download_cloudflared(store: Store) -> None:
    systems = {"Darwin": "darwin", "Linux": "linux", "Windows": "windows"}
    architectures = {"x86_64": "amd64", "amd64": "amd64", "aarch64": "arm64", "arm64": "arm64"}
    system = systems.get(platform.system())
    architecture = architectures.get(platform.machine().lower())
    if not system or not architecture:
        raise SpeiiError(
            "Unsupported cloudflared architecture; install its official binary manually."
        )
    extension = ".exe" if system == "windows" else ".tgz" if system == "darwin" else ""
    name = f"cloudflared-{system}-{architecture}{extension}"
    asset = pinned_binaries()["cloudflared"]["assets"].get(name)
    if not asset:
        raise SpeiiError(
            f"No reviewed binary is available for {name}; install it through your OS package manager."
        )
    with httpx.Client(follow_redirects=True, timeout=120) as client:
        data = verified_download(client, asset)
        if extension == ".tgz":
            import tarfile

            with tarfile.open(fileobj=io.BytesIO(data)) as archive:
                member = next(
                    (
                        m
                        for m in archive.getmembers()
                        if m.isfile() and m.name.rsplit("/", 1)[-1] == "cloudflared"
                    ),
                    None,
                )
                if member is None:
                    raise SpeiiError("Official archive does not contain cloudflared.")
                if member.size > 128 * 1024 * 1024:
                    raise SpeiiError("Unpacked cloudflared exceeds the binary size limit.")
                data = archive.extractfile(member).read()
        target = store.home / "bin" / ("cloudflared.exe" if system == "windows" else "cloudflared")
        atomic_write(target, data)
        target.chmod(0o700)


def download_windows_nginx(store: Store) -> None:
    with httpx.Client(follow_redirects=True, timeout=120) as client:
        data = verified_download(client, pinned_binaries()["nginx_windows"])
        root = store.home / "bin/nginx"
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            if sum(member.file_size for member in archive.infolist()) > 128 * 1024 * 1024:
                raise SpeiiError("Unpacked Nginx exceeds the archive size limit.")
            for member in archive.infolist():
                parts = member.filename.split("/")[1:]
                if not parts or not parts[-1]:
                    continue
                if any(p in {"..", "."} or ":" in p or "\\" in p for p in parts):
                    raise SpeiiError("Unsafe path in Nginx archive.")
                atomic_write(root.joinpath(*parts), archive.read(member))


def install_missing(store: Store) -> None:
    for name in ("nginx", "cloudflared"):
        if find_binary(name, store):
            continue
        commands = package_commands(name)
        if commands:
            for command in commands:
                if subprocess.run(command).returncode:
                    raise SpeiiError(f"Could not install {name}; install it manually and retry.")
        elif name == "cloudflared":
            download_cloudflared(store)
        elif platform.system() == "Windows":
            download_windows_nginx(store)
        else:
            raise SpeiiError(f"No supported package manager; install {name} manually.")
        if not find_binary(name, store):
            raise SpeiiError(f"{name} installed but not on PATH; reopen your terminal and retry.")
