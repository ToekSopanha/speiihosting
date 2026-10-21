import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from speiihosting.config import Service, SpeiiError
from speiihosting.isolation import PodmanRuntime
from speiihosting.process import environment, run_logged
from speiihosting.storage import atomic_write, write_json


def test_app_environment_excludes_host_credentials(tmp_path, monkeypatch):
    for name in (
        "CLOUDFLARE_API_TOKEN",
        "TUNNEL_TOKEN",
        "SPEIIHOSTING_HOME",
        "AWS_SECRET_ACCESS_KEY",
        "SSH_AUTH_SOCK",
        "PYTHONPATH",
        "NODE_OPTIONS",
    ):
        monkeypatch.setenv(name, "host-secret")
    monkeypatch.setenv("EXPLICIT_APP_SETTING", "allowed")
    (tmp_path / ".env").write_text("BOT_TOKEN=app-secret\nCLOUDFLARE_API_TOKEN=reserved\n")
    service = Service(
        name="worker", type="bot", source=tmp_path, env_allow=["EXPLICIT_APP_SETTING"]
    )
    result = environment(service, tmp_path)
    assert result["BOT_TOKEN"] == "app-secret"
    assert result["EXPLICIT_APP_SETTING"] == "allowed"
    assert "host-secret" not in result.values()
    assert "CLOUDFLARE_API_TOKEN" not in result
    assert result["SPEII_DATA_DIR"] == str(tmp_path.parent / "data")


def test_build_environment_has_no_host_secrets(tmp_path, monkeypatch):
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "host-secret")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "host-secret")
    code = "import os; assert 'CLOUDFLARE_API_TOKEN' not in os.environ; assert 'AWS_SECRET_ACCESS_KEY' not in os.environ"
    assert run_logged([sys.executable, "-c", code], tmp_path, tmp_path / "build.log") == 0


@pytest.mark.parametrize("name", ["CLOUDFLARE_API_TOKEN", "tunnel_token", "SPEIIHOSTING_HOME"])
def test_reserved_variables_cannot_be_allowlisted(tmp_path, name):
    with pytest.raises(ValueError):
        Service(name="worker", type="bot", source=tmp_path, env_allow=[name])


def test_legacy_credentials_migrate_out_of_general_config(store):
    atomic_write(
        store.home / "config.json",
        json.dumps(
            {"cloudflare_api_token": "old-secret", "tunnel_token": "old-tunnel", "nginx_port": 80}
        ),
    )
    assert store.settings().cloudflare_api_token.get_secret_value() == "old-secret"
    store.migrate()
    config = (store.home / "config.json").read_text()
    assert "old-secret" not in config and "old-tunnel" not in config
    assert json.loads(config)["schema_version"] == 2
    assert store.settings().nginx_port == 80
    assert store.settings().tunnel_token.get_secret_value() == "old-tunnel"
    if os.name != "nt":
        assert (store.home / "credentials.json").stat().st_mode & 0o777 == 0o600


def test_unknown_schema_is_rejected_without_changes(store):
    atomic_write(store.home / "config.json", '{"schema_version":99}')
    before = (store.home / "config.json").read_bytes()
    with pytest.raises(SpeiiError):
        store.migrate()
    assert (store.home / "config.json").read_bytes() == before


def test_metrics_write_skips_fsync_but_critical_state_is_durable(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(os, "fsync", lambda fd: calls.append(fd))
    write_json(tmp_path / "runtime.json", {}, durable=False)
    assert not calls
    write_json(tmp_path / "config.json", {})
    assert len(calls) >= 1


def test_state_reads_are_cached_and_invalidated(store, monkeypatch):
    import speiihosting.storage as storage

    calls = []
    original = storage.read_json

    def read(path, default=None):
        calls.append(path.name)
        return original(path, default)

    monkeypatch.setattr(storage, "read_json", read)
    store.settings()
    initial = len(calls)
    for _ in range(5):
        store.settings()
    assert len(calls) == initial
    settings = store.settings()
    settings.metrics_interval = 5
    store.save_settings(settings)
    assert store.settings().metrics_interval == 5
    assert len(calls) > initial


def rootless(monkeypatch):
    monkeypatch.setattr(os, "getuid", lambda: 1000, raising=False)
    monkeypatch.setattr(os, "getgid", lambda: 1000, raising=False)
    monkeypatch.setattr("speiihosting.isolation.platform.system", lambda: "Linux")
    monkeypatch.setattr("speiihosting.isolation.shutil.which", lambda _: "/usr/bin/podman")
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *a, **kw: subprocess.CompletedProcess(
            a,
            0,
            json.dumps(
                {
                    "host": {
                        "security": {"rootless": True},
                        "cgroupVersion": "v2",
                        "cgroupControllers": ["cpu", "memory", "pids"],
                    }
                }
            ),
            "",
        ),
    )


def test_rootless_adapter_hardens_container_and_keeps_secrets_out_of_argv(
    store, tmp_path, monkeypatch
):
    rootless(monkeypatch)
    service = Service(
        name="sandbox",
        type="backend",
        source=tmp_path,
        port=8000,
        isolation="podman",
        image="registry.example/app@sha256:" + "a" * 64,
        command=["{image}"],
    )
    live = store.site(service.name) / "live"
    live.mkdir(parents=True)
    (live / ".env").write_text(
        "APP_SECRET=inside-container\nCONTAINER_HOST=app-value\nPATH=/app/fake-path\n"
    )
    managed = store.env_file(service.name)
    managed.parent.mkdir(parents=True)
    managed.write_text("APP_SECRET=managed-container\nCLOUDFLARE_API_TOKEN=forbidden\n")
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "never-in-container")
    spec = PodmanRuntime().launch(store, service)
    assert "--read-only" in spec.command
    assert "--cap-drop=ALL" in spec.command
    assert "--security-opt=no-new-privileges" in spec.command
    assert "127.0.0.1:8000:8000" in spec.command
    assert (
        "--memory" in spec.command and "--cpus" in spec.command and "--pids-limit" in spec.command
    )
    assert "inside-container" not in repr(spec.command)
    assert "managed-container" not in repr(spec.command)
    assert "APP_SECRET" not in spec.env and "CONTAINER_HOST" not in spec.env
    assert spec.env.get("PATH") != "/app/fake-path"
    env_file = Path(spec.command[spec.command.index("--env-file") + 1])
    assert "APP_SECRET=managed-container" in env_file.read_text()
    assert "never-in-container" not in env_file.read_text()
    assert "forbidden" not in env_file.read_text()
    if os.name != "nt":
        assert env_file.stat().st_mode & 0o777 == 0o600


def test_rootful_container_runtime_is_rejected(tmp_path, monkeypatch):
    rootless(monkeypatch)
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *a, **kw: subprocess.CompletedProcess(
            a, 0, '{"host":{"security":{"rootless":false},"cgroupVersion":"v2"}}', ""
        ),
    )
    service = Service(
        name="app",
        type="bot",
        source=tmp_path,
        isolation="podman",
        image="registry.example/app@sha256:" + "a" * 64,
    )
    with pytest.raises(SpeiiError, match="rootless"):
        PodmanRuntime().validate(service)


def test_container_stop_verifies_ownership(store, tmp_path, monkeypatch):
    rootless(monkeypatch)
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(
            command, 0, '[{"Config":{"Labels":{"io.speiihosting.owner":"someone-else"}}}]', ""
        )

    monkeypatch.setattr(subprocess, "run", run)
    service = Service(name="app", type="bot", source=tmp_path, isolation="podman")
    with pytest.raises(SpeiiError, match="not owned"):
        PodmanRuntime().stop(store, service)
    assert all("stop" not in command for command in calls)
