from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sys
import uuid
from pathlib import Path

from .config import Service, SpeiiError, valid_name

try:
    import tomllib
except ImportError:
    import tomli as tomllib


EXCLUDED = {
    "node_modules",
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    ".git",
    ".github",
    ".svn",
    "tmp",
    ".cache",
    ".turbo",
    ".nuxt",
    ".DS_Store",
}


def manifest(path: Path) -> dict:
    try:
        return json.loads((path / "package.json").read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (ValueError, OSError) as error:
        raise SpeiiError(f"Invalid package.json in {path}: {error}") from error


def project_name(source: Path, explicit: str | None, port: int | None = None) -> str:
    if explicit:
        return valid_name(explicit)
    name = manifest(source).get("name")
    if not name and (source / "pyproject.toml").exists():
        try:
            data = tomllib.loads((source / "pyproject.toml").read_text(encoding="utf-8"))
            name = data.get("project", {}).get("name") or data.get("tool", {}).get(
                "poetry", {}
            ).get("name")
        except (ValueError, OSError) as error:
            raise SpeiiError(f"Invalid pyproject.toml: {error}") from error
    name = name or source.name or f"backend-{port}"
    name = re.sub(r"[^a-zA-Z0-9_-]+", "-", name.split("/")[-1]).strip("-_")[:63]
    return valid_name(name or f"backend-{port or 'app'}")


def static_candidates(source: Path) -> list[Path]:
    return [
        p
        for p in (source / "dist", source / "build", source / "out", source / "public", source)
        if (p / "index.html").is_file()
    ]


def static_directory(source: Path, override: Path | None = None) -> Path:
    if override:
        path = (source / override).resolve()
        if not (path / "index.html").is_file():
            raise SpeiiError(f"No index.html in {path}.")
        return path
    choices = static_candidates(source)
    if len(choices) != 1:
        raise SpeiiError(
            "Use --dir to select a build folder. Found: "
            + (", ".join(str(p) for p in choices) or "none; build your project first")
        )
    return choices[0]


def shell_command(command: str) -> list[str]:
    return ["cmd.exe", "/d", "/s", "/c", command] if os.name == "nt" else ["/bin/sh", "-c", command]


def executable(name: str) -> str:
    value = shutil.which(name)
    if not value:
        raise SpeiiError(f"{name} is required for this project; install it and retry.")
    return value


def detect(service: Service, path: Path) -> tuple[list[str], list[str]]:
    """Return a command and extra Python runtime dependencies."""
    if service.custom_command:
        return shell_command(service.custom_command), []
    package = manifest(path)
    deps = {**package.get("dependencies", {}), **package.get("devDependencies", {})}
    port = str(service.port or 8000)
    if package:
        npm = executable("npm")
        if "next" in deps:
            service.framework = "Next.js"
            return [npm, "start", "--", "--hostname", "127.0.0.1", "--port", port], []
        if "nuxt" in deps:
            service.framework = "Nuxt"
            return [executable("node"), ".output/server/index.mjs"], []
        if "start" in package.get("scripts", {}):
            service.framework = "Node.js"
            return [npm, "start"], []
    for filename in ("bot.js", "index.js", "server.js"):
        if (path / filename).is_file():
            service.framework = "Node.js"
            return [executable("node"), filename], []
    if (path / "manage.py").exists():
        modules = list(path.glob("*/wsgi.py"))
        if not modules:
            raise SpeiiError("Cannot locate Django wsgi.py; supply --run.")
        service.framework = "Django"
        module = f"{modules[0].parent.name}.wsgi:application"
        if os.name == "nt":
            return ["{python}", "-m", "waitress", f"--listen=127.0.0.1:{port}", module], [
                "waitress"
            ]
        return ["{python}", "-m", "gunicorn", module, "--bind", f"127.0.0.1:{port}"], ["gunicorn"]
    if (path / "artisan").exists():
        service.framework = "Laravel"
        return [executable("php"), "artisan", "serve", "--host=127.0.0.1", f"--port={port}"], []
    for filename in (
        ("bot.py", "main.py", "app.py") if service.type == "bot" else ("main.py", "app.py")
    ):
        file = path / filename
        if not file.is_file():
            continue
        code = file.read_text(encoding="utf-8")
        service.framework = "Python"
        if service.type != "bot" and re.search(r"\bFastAPI\s*\(", code):
            service.framework = "FastAPI"
            return [
                "{python}",
                "-m",
                "uvicorn",
                f"{file.stem}:app",
                "--host",
                "127.0.0.1",
                "--port",
                port,
            ], ["uvicorn"]
        if service.type != "bot" and re.search(r"\bFlask\s*\(", code):
            service.framework = "Flask"
            module = f"{file.stem}:app"
            if os.name == "nt":
                return ["{python}", "-m", "waitress", f"--listen=127.0.0.1:{port}", module], [
                    "waitress"
                ]
            return ["{python}", "-m", "gunicorn", module, "--bind", f"127.0.0.1:{port}"], [
                "gunicorn"
            ]
        return ["{python}", "-u", filename], []
    raise SpeiiError("Could not detect a runnable project. Supply --run 'your command'.")


def ignore(directory: str, names: list[str]) -> set[str]:
    return {
        name
        for name in names
        if name in EXCLUDED
        or name.endswith((".pyc", ".log"))
        or (Path(directory).name == ".next" and name == "cache")
    }


def copy_source(source: Path, destination: Path) -> None:
    if destination == source or source in destination.parents:
        raise SpeiiError("The hosting data directory must be outside the source project.")

    # Do not follow links to secrets or a recursive parent outside the project.
    def safe_ignore(directory: str, names: list[str]) -> set[str]:
        ignored = ignore(directory, names)
        for name in set(names) - ignored:
            item = Path(directory) / name
            if item.is_symlink() and item.is_dir():
                raise SpeiiError(f"Directory symlinks are not supported in deployments: {item}")
            if item.is_symlink() and not item.resolve().is_relative_to(source):
                raise SpeiiError(f"Source symlink escapes the project: {item}")
        return ignored

    shutil.copytree(source, destination, ignore=safe_ignore)


def run_build(command: list[str], cwd: Path, log: Path, env: dict | None = None) -> None:
    from .process import run_logged

    if run_logged(command, cwd, log, env) != 0:
        raise SpeiiError(f"Build/dependency command failed. See {log} (speiihos logs).")


def prepare(service: Service, candidate: Path, site: Path, log: Path, install: bool = True) -> None:
    """Build a candidate fully before touching live code or the running process."""
    from .process import environment as process_environment
    from .storage import Store

    store = Store(site.parent.parent, create=False)
    build_env = process_environment(service, candidate, store)
    package = manifest(candidate)
    if package and install:
        if service.strict_dependencies and not (candidate / "package-lock.json").is_file():
            raise SpeiiError(
                "Strict Node installs require package-lock.json; create and review a lockfile first."
            )
        npm = executable("npm")
        run_build(
            [
                npm,
                "ci" if (candidate / "package-lock.json").exists() else "install",
                "--no-audit",
                "--no-fund",
            ],
            candidate,
            log,
            build_env,
        )
    if service.type == "frontend":
        return
    service.command, extras = detect(service, candidate)
    requirements = candidate / (
        "requirements.lock" if (candidate / "requirements.lock").exists() else "requirements.txt"
    )
    pyproject = candidate / "pyproject.toml"
    python_project = "{python}" in service.command or requirements.exists() or pyproject.exists()
    if python_project and install and service.strict_dependencies and not requirements.exists():
        raise SpeiiError(
            "Strict Python installs require a pinned requirements.lock or requirements.txt with SHA-256 hashes."
        )
    if python_project and install and (requirements.exists() or pyproject.exists() or extras):
        digest = hashlib.sha256(
            (requirements.read_bytes() if requirements.exists() else b"")
            + (pyproject.read_bytes() if pyproject.exists() else b"")
            + repr(extras).encode()
            + sys.version.encode()
        ).hexdigest()[:16]
        if pyproject.exists() and not requirements.exists():
            # pip installs this project's code too; an unchanged manifest does
            # not mean its installed modules are unchanged between releases.
            digest = uuid.uuid4().hex[:16]
        environment = site / "environments" / digest
        python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        marker = environment / ".ready"
        if not marker.exists():
            if environment.exists():
                shutil.rmtree(environment)
            run_build([sys.executable, "-m", "venv", str(environment)], candidate, log, build_env)
            command = [str(python), "-m", "pip", "install"]
            if requirements.exists():
                verification = (
                    ["--require-hashes", "--only-binary=:all:"]
                    if service.strict_dependencies
                    else []
                )
                run_build(
                    [*command, *verification, "-r", str(requirements)], candidate, log, build_env
                )
            elif pyproject.exists():
                run_build([*command, str(candidate)], candidate, log, build_env)
            if extras:
                if service.strict_dependencies:
                    run_build(
                        [
                            str(python),
                            "-c",
                            "import importlib.util; assert all(importlib.util.find_spec(m) for m in "
                            + repr(extras)
                            + "), 'Include the server runtime in your hashed lockfile'",
                        ],
                        candidate,
                        log,
                        build_env,
                    )
                else:
                    run_build([*command, *extras], candidate, log, build_env)
            marker.touch()
        service.environment_dir = environment
    else:
        service.environment_dir = None
    if service.build_command:
        run_build(
            shell_command(service.build_command),
            candidate,
            log,
            process_environment(service, candidate, store),
        )
    elif service.type == "dynamic" and "build" in package.get("scripts", {}):
        run_build(
            [executable("npm"), "run", "build"],
            candidate,
            log,
            process_environment(service, candidate, store),
        )


def trim_dependencies(path: Path) -> None:
    for current, directories, files in os.walk(path):
        for name in list(directories):
            if name in EXCLUDED or (Path(current).name == ".next" and name == "cache"):
                target = Path(current) / name
                if target.is_symlink():
                    target.unlink()
                else:
                    shutil.rmtree(target)
                directories.remove(name)


class Release:
    """A reversible directory promotion; retain exactly one previous release."""

    def __init__(self, site: Path):
        self.site = site
        site.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.candidate = site / "candidate"
        self.live = site / "live"
        self.previous = site / "previous"
        self.obsolete = site / ".obsolete"

    def promote(self) -> None:
        if self.obsolete.exists():
            raise SpeiiError(
                f"Interrupted deployment in {self.site}; inspect .obsolete before retrying."
            )
        if self.previous.exists():
            self.previous.rename(self.obsolete)
        try:
            if self.live.exists():
                self.live.rename(self.previous)
            self.candidate.rename(self.live)
        except OSError:
            if self.previous.exists() and not self.live.exists():
                self.previous.rename(self.live)
            if self.obsolete.exists():
                self.obsolete.rename(self.previous)
            raise

    def revert(self) -> None:
        if self.live.exists():
            shutil.rmtree(self.live)
        if self.previous.exists():
            self.previous.rename(self.live)
        if self.obsolete.exists():
            self.obsolete.rename(self.previous)

    def finish(self) -> None:
        if self.obsolete.exists():
            shutil.rmtree(self.obsolete)
        # Keep the previous release runnable without downloads or build hooks.
