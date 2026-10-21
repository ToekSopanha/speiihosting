import json
import sys
import time

from typer.testing import CliRunner

from speiihosting.cli import app
from speiihosting.config import Service
from speiihosting.inspection import describe
from speiihosting.isolation import ProcessRuntime
from speiihosting.manager import Manager
from speiihosting.process import environment


def test_managed_env_overrides_project_without_leaking_between_services(
    store, tmp_path, monkeypatch
):
    live = store.site("api") / "live"
    live.mkdir(parents=True)
    (live / ".env").write_text("JWT_SECRET=project-secret\nPROJECT_ONLY=kept\n")
    managed = store.env_file("api")
    managed.parent.mkdir(parents=True)
    managed.write_text(
        "JWT_SECRET=managed-secret\nPORT=9999\nHOST=0.0.0.0\n"
        "CLOUDFLARE_API_TOKEN=forbidden\nTUNNEL_TOKEN=forbidden\n"
        "SPEIIHOSTING_HOME=forbidden\nLITERAL=${JWT_SECRET}\n",
        encoding="utf-8-sig",
    )
    service = Service(name="api", type="backend", source=tmp_path, port=3001)
    # An explicit Store must win over an unrelated CLI environment.
    monkeypatch.setenv("SPEIIHOSTING_HOME", str(tmp_path / "different-home"))
    values = ProcessRuntime().launch(store, service).env
    assert values["JWT_SECRET"] == "managed-secret"
    assert values["PROJECT_ONLY"] == "kept"
    assert values["PORT"] == "3001" and values["HOST"] == "127.0.0.1"
    assert values["LITERAL"] == "${JWT_SECRET}"
    assert "forbidden" not in values.values()
    other = service.model_copy(update={"name": "other"})
    assert environment(other, live, store)["JWT_SECRET"] == "project-secret"
    store.save_services({service.name: service})
    report = describe(store, service, disk=False)
    assert report["env_file"] == str(managed)
    assert report["env_file_present"] is True
    assert "managed-secret" not in json.dumps(report)
    assert "managed-secret" not in (store.home / "services.json").read_text()


def test_host_preview_reports_managed_env_path_without_exposing_values(
    store, tmp_path, monkeypatch
):
    source = tmp_path / "backend"
    source.mkdir()
    (source / "main.py").write_text("print('preview')")
    managed = store.env_file("custom-api")
    managed.parent.mkdir(parents=True)
    managed.write_text("JWT_SECRET=private-managed-value\n")
    monkeypatch.chdir(source)
    result = CliRunner().invoke(
        app, ["host-back", "--port", "3001", "--name", "custom-api", "--dry-run", "--json"]
    )
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["env_file"] == str(managed)
    assert data["env_file_present"] is True
    assert "private-managed-value" not in result.output
    assert not store.site("custom-api").exists()


def test_managed_env_survives_build_deploy_rollback_restart_and_remove(store, tmp_path):
    source = tmp_path / "env-worker"
    source.mkdir()
    (source / "bot.py").write_text(
        "import os, time\n"
        "assert os.environ.get('JWT_SECRET'), 'JWT_SECRET missing'\n"
        "print('mode=' + os.environ['APP_MODE'], flush=True)\n"
        "while True: time.sleep(1)\n"
    )
    (source / "build.py").write_text(
        "import os\nfrom pathlib import Path\n"
        "assert os.environ.get('JWT_SECRET'), 'JWT_SECRET missing during build'\n"
        "Path('build-mode.txt').write_text(os.environ['APP_MODE'])\n"
    )
    managed = store.env_file(source.name)
    managed.parent.mkdir(parents=True)

    def write_env(mode):
        managed.write_text(f"JWT_SECRET=private-test-secret\nAPP_MODE={mode}\n")

    write_env("one")
    manager = Manager(store)
    service = manager.host("bot", source, build=f'"{sys.executable}" build.py', install=False)
    live = store.site(service.name) / "live"
    log = store.home / "logs" / f"{service.name}.log"

    def wait_for_mode(mode, count=1):
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if log.read_text().count("mode=" + mode) >= count:
                return
            time.sleep(0.05)
        raise AssertionError("Worker did not reload its managed environment")

    wait_for_mode("one")
    assert (live / "build-mode.txt").read_text() == "one"
    assert not (live / ".env").exists()
    write_env("two")
    manager.lifecycle(service.name, "restart")
    wait_for_mode("two")
    assert (live / "build-mode.txt").read_text() == "one"
    manager.deploy(service.name, install=False)
    wait_for_mode("two", count=2)
    assert (live / "build-mode.txt").read_text() == "two"
    manager.deploy(service.name, rollback=True, install=False)
    wait_for_mode("two", count=3)
    assert (live / "build-mode.txt").read_text() == "one"
    assert "private-test-secret" not in log.read_text()
    manager.remove(service.name)
    assert managed.is_file()
    assert "APP_MODE=two" in managed.read_text()
