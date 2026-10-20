import json
import os
from pathlib import Path

import pytest
from typer.testing import CliRunner

from speiihosting.cli import app
from speiihosting.config import Service, Settings, SpeiiError, valid_domain
from speiihosting.ports import allocate
from speiihosting.projects import Release, copy_source, detect, project_name, static_directory
from speiihosting.storage import atomic_write


def test_secure_state_and_secret_redaction(store):
    settings = Settings(cloudflare_api_token="test-secret", tunnel_token="tunnel-secret")
    store.save_settings(settings)
    assert store.settings().cloudflare_api_token.get_secret_value() == "test-secret"
    result = CliRunner().invoke(app, ["config", "show"])
    assert result.exit_code == 0
    assert "test-secret" not in result.output
    assert "tunnel-secret" not in result.output
    if os.name != "nt":
        assert (store.home.stat().st_mode & 0o777) == 0o700
        assert ((store.home / "config.json").stat().st_mode & 0o777) == 0o600


def test_corrupt_state_is_not_overwritten(store):
    path = store.home / "services.json"
    atomic_write(path, "not json")
    result = CliRunner().invoke(app, ["list"])
    assert result.exit_code == 1
    assert path.read_text() == "not json"


@pytest.mark.parametrize("name", ["../escape", "/root", ".", "nginx", "a; return 200;"])
def test_reject_unsafe_names(store, name):
    with pytest.raises(ValueError):
        store.site(name)


@pytest.mark.parametrize(
    "domain", ["https://site.test", "site.test;", "bad_domain.test", "site.test/", "-bad.test"]
)
def test_reject_unsafe_domains(domain):
    with pytest.raises(ValueError):
        valid_domain(domain)


def test_service_name_priority(tmp_path):
    (tmp_path / "package.json").write_text('{"name":"@scope/my-api"}')
    assert project_name(tmp_path, "explicit") == "explicit"
    assert project_name(tmp_path, None) == "my-api"
    (tmp_path / "package.json").unlink()
    (tmp_path / "pyproject.toml").write_text('[project]\nname="python-api"\n')
    assert project_name(tmp_path, None) == "python-api"
    (tmp_path / "pyproject.toml").unlink()
    assert project_name(tmp_path, None) == tmp_path.name


def test_static_detection_requires_disambiguation(tmp_path):
    for name in ("dist", "build"):
        path = tmp_path / name
        path.mkdir()
        (path / "index.html").write_text(name)
    with pytest.raises(SpeiiError, match="--dir"):
        static_directory(tmp_path)
    assert static_directory(tmp_path, Path("dist")) == tmp_path / "dist"


def test_source_copy_excludes_dependencies_and_keeps_env(tmp_path):
    source, target = tmp_path / "source", tmp_path / "target"
    source.mkdir()
    (source / ".env").write_text("BOT_TOKEN=private")
    (source / "app.py").write_text("print('hello')")
    for name in (".git", "node_modules", ".venv", "__pycache__"):
        (source / name).mkdir()
        (source / name / "big").write_text("ignored")
    copy_source(source, target)
    assert (target / ".env").read_text() == "BOT_TOKEN=private"
    assert sorted(p.name for p in target.iterdir()) == [".env", "app.py"]


@pytest.mark.skipif(os.name == "nt", reason="symlinks need extra Windows privileges")
def test_source_copy_rejects_external_symlinks(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "leak").symlink_to(tmp_path / "secret")
    with pytest.raises(SpeiiError, match="symlink"):
        copy_source(source, tmp_path / "target")


def test_release_revert_restores_live_and_previous(tmp_path):
    release = Release(tmp_path / "site")
    for path, text in (
        (release.live, "current"),
        (release.previous, "older"),
        (release.candidate, "next"),
    ):
        path.mkdir()
        (path / "index.html").write_text(text)
    release.promote()
    assert (release.live / "index.html").read_text() == "next"
    release.revert()
    assert (release.live / "index.html").read_text() == "current"
    assert (release.previous / "index.html").read_text() == "older"


def test_single_backup_retains_runnable_dependencies(tmp_path):
    release = Release(tmp_path / "site")
    release.live.mkdir()
    (release.live / "node_modules").mkdir()
    (release.live / "node_modules/dependency").write_text("large")
    release.candidate.mkdir()
    release.promote()
    release.finish()
    assert release.previous.exists()
    assert (release.previous / "node_modules/dependency").read_text() == "large"
    assert not release.obsolete.exists()


def test_port_registry_and_identifier_lookup(store, tmp_path, free_port):
    service = Service(name="my-api", type="backend", source=tmp_path, port=free_port)
    store.save_services({service.name: service})
    assert store.resolve(str(free_port)).name == "my-api"
    assert json.loads((store.home / "registry.json").read_text()) == {str(free_port): "my-api"}
    with pytest.raises(SpeiiError):
        allocate(free_port, {free_port})
    assert allocate(free_port, {free_port}, auto=True) != free_port


def test_cli_help_version_validation_and_log_clear(store, tmp_path):
    runner = CliRunner()
    assert runner.invoke(app, ["--version"]).exit_code == 0
    for command in (
        "host-front",
        "host-dynamic",
        "host-app",
        "host-back",
        "host-bot",
        "deploy",
        "logs",
        "clean",
        "init",
    ):
        result = runner.invoke(app, [command, "--help"])
        assert result.exit_code == 0, result.output
    assert runner.invoke(app, ["host-back", "--port", "70000"]).exit_code == 2
    service = Service(name="api", type="backend", source=tmp_path, port=8000)
    store.save_services({"api": service})
    (store.home / "logs/api.log").write_text("one\ntwo\nthree\n")
    (store.home / "logs/api.log.1").write_text("old\n")
    result = runner.invoke(app, ["logs", "8000", "-n", "2"])
    assert result.exit_code == 0, result.output
    assert result.output == "two\nthree\n"
    assert runner.invoke(app, ["logs", "size"]).exit_code == 0
    assert runner.invoke(app, ["logs", "clear", "api"]).exit_code == 0
    assert (store.home / "logs/api.log").stat().st_size == 0
    assert not (store.home / "logs/api.log.1").exists()


@pytest.mark.parametrize(
    "kind,filename,code,framework,module",
    [
        ("bot", "bot.py", "print('bot')", "Python", "bot.py"),
        (
            "backend",
            "main.py",
            "from fastapi import FastAPI\napp = FastAPI()",
            "FastAPI",
            "uvicorn",
        ),
        (
            "backend",
            "app.py",
            "from flask import Flask\napp = Flask(__name__)",
            "Flask",
            "waitress" if os.name == "nt" else "gunicorn",
        ),
    ],
)
def test_runtime_detection(tmp_path, kind, filename, code, framework, module):
    (tmp_path / filename).write_text(code)
    service = Service(name="app", type=kind, source=tmp_path, port=8000)
    command, extras = detect(service, tmp_path)
    assert service.framework == framework
    assert module in command
