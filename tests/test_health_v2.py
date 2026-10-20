import io
import json
import tarfile
import time

import httpx
import pytest
from typer.testing import CliRunner

from speiihosting.cli import app
from speiihosting.config import HealthCheck, Service, SpeiiError
from speiihosting.health import probe
from speiihosting.manager import Manager
from speiihosting.process import alive, wait_service
from speiihosting.storage import read_json, write_json


def eventually(predicate, timeout=25):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.1)
    raise AssertionError("Timed out waiting for health transition")


def test_http_health_failure_restores_last_working_release(
    store, tmp_path, free_port, monkeypatch, http_app
):
    source = tmp_path / "checked-api"
    http_app(source)
    monkeypatch.setenv("HTTP_PROXY", "http://invalid.proxy:1")
    monkeypatch.setenv("HTTPS_PROXY", "http://invalid.proxy:1")
    manager = Manager(store)
    service = manager.host(
        "backend",
        source,
        port=free_port,
        install=False,
        health=HealthCheck(path="/health", expected_body="ready", startup_timeout=10),
    )
    assert probe(service)["status"] == "healthy"
    http_app(source, code=503)
    with pytest.raises(SpeiiError, match="did not become ready"):
        manager.deploy(service.name, install=False)
    assert probe(store.resolve(service.name))["status"] == "healthy"
    assert "else 200" in (store.site(service.name) / "live/main.py").read_text()
    assert alive(store, service.name)


def test_ongoing_health_failure_restarts_one_service(store, tmp_path, free_port, http_app):
    source = tmp_path / "monitored-api"
    http_app(source)
    service = Manager(store).host(
        "backend",
        source,
        port=free_port,
        install=False,
        health=HealthCheck(
            path="/health", expected_body="ready", interval=1, failures=1, startup_timeout=10
        ),
    )
    marker = store.site(service.name) / "data/unhealthy"
    marker.write_text("trigger health failure")
    eventually(
        lambda: (
            read_json(store.home / "runtime.json", {})
            .get("services", {})
            .get(service.name, {})
            .get("restarts", 0)
            >= 1
        )
    )
    marker.unlink()
    eventually(lambda: probe(service)["status"] == "healthy")


@pytest.mark.parametrize("healthy", [True, False])
def test_http_readiness_requires_a_healthy_request_without_a_separate_tcp_probe(
    store, tmp_path, monkeypatch, healthy
):
    service = Service(
        name="http-readiness",
        type="backend",
        source=tmp_path,
        port=8000,
        command=["python", "main.py"],
        health=HealthCheck(),
    )
    write_json(
        store.home / "runtime.json",
        {
            "services": {
                service.name: {
                    "generation": service.generation,
                    "status": "running",
                    "uptime": 2,
                }
            }
        },
    )

    def unexpected_tcp_probe(port):
        pytest.fail("HTTP readiness must not open an additional empty TCP connection")

    monkeypatch.setattr("speiihosting.ports.listening", unexpected_tcp_probe)
    monkeypatch.setattr(
        "speiihosting.health.probe",
        lambda _: {
            "status": "healthy" if healthy else "unhealthy",
            "http_status": 200 if healthy else 503,
        },
    )
    if healthy:
        wait_service(store, service, timeout=0.1)
    else:
        with pytest.raises(SpeiiError, match=r"HTTP health: unhealthy \(HTTP 503\)"):
            wait_service(store, service, timeout=0.1)


def test_offline_rollback_keeps_dependencies_and_persistent_data(store, tmp_path, monkeypatch):
    source = tmp_path / "offline-worker"
    source.mkdir()
    (source / "bot.py").write_text("import time\nwhile True: time.sleep(1)\n")
    manager = Manager(store)
    service = manager.host("bot", source, install=False)
    site = store.site(service.name)
    dependency = site / "live/node_modules/kept"
    dependency.mkdir(parents=True)
    (dependency / "version").write_text("original dependency")
    (site / "data/uploads.txt").write_text("user data")
    (source / "bot.py").write_text("import time\n# release two\nwhile True: time.sleep(1)\n")
    manager.deploy(service.name, install=False)
    assert (site / "previous/node_modules/kept/version").exists()

    def forbid_install(*args, **kwargs):
        raise AssertionError("Rollback must never install or rebuild dependencies")

    monkeypatch.setattr("speiihosting.manager.prepare", forbid_install)
    monkeypatch.setattr("speiihosting.projects.run_build", forbid_install)
    manager.deploy(service.name, rollback=True)
    assert (site / "live/node_modules/kept/version").read_text() == "original dependency"
    assert (site / "data/uploads.txt").read_text() == "user data"
    manager.remove(service.name)
    assert (site / "data/uploads.txt").read_text() == "user data"
    assert not (site / "live").exists()
    with pytest.raises(SpeiiError, match="reuse-data"):
        manager.host("bot", source, install=False)
    # Restoration with saved data must be explicit.
    monkeypatch.undo()
    restored = manager.host("bot", source, install=False, reuse_data=True)
    assert (site / "data/uploads.txt").read_text() == "user data"
    manager.remove(restored.name, purge_data=True)
    assert not site.exists()


def test_node_rollback_preserves_a_real_installed_local_dependency(store, tmp_path, monkeypatch):
    import shutil

    if not shutil.which("npm"):
        pytest.skip("requires Node/npm")
    source = tmp_path / "node-worker"
    vendor = source / "vendor"
    vendor.mkdir(parents=True)

    def write_dependency(version, value):
        archive = vendor / f"local-dep-{version}.tgz"
        files = {
            "package.json": json.dumps(
                {"name": "local-dep", "version": version, "main": "index.js"}
            ),
            "index.js": f"module.exports = '{value}';",
        }
        # Install a real offline package, without directory links to candidate/.
        with tarfile.open(archive, "w:gz") as package:
            for name, contents in files.items():
                data = contents.encode()
                entry = tarfile.TarInfo(f"package/{name}")
                entry.size, entry.mode = len(data), 0o644
                package.addfile(entry, io.BytesIO(data))
        (source / "package.json").write_text(
            json.dumps(
                {
                    "name": "node-worker",
                    "scripts": {"start": "node bot.js"},
                    "dependencies": {"local-dep": f"file:./vendor/{archive.name}"},
                }
            )
        )

    write_dependency("1.0.0", "dependency-one")
    (source / "bot.js").write_text(
        "console.log(require('local-dep')); setInterval(() => {}, 1000);"
    )
    (source / ".env").write_text(
        f"NPM_CONFIG_CACHE={tmp_path / 'npm-cache'}\nNPM_CONFIG_UPDATE_NOTIFIER=false\n"
    )
    manager = Manager(store)
    service = manager.host("bot", source)
    site = store.site(service.name)
    dependency = site / "live/node_modules/local-dep"
    assert dependency.resolve() == dependency
    write_dependency("2.0.0", "dependency-two")
    manager.deploy(service.name)
    assert (site / "previous/node_modules/local-dep/index.js").exists()
    assert (
        site / "live/node_modules/local-dep/index.js"
    ).read_text() == "module.exports = 'dependency-two';"
    previous_dependency = site / "previous/node_modules/local-dep"
    assert previous_dependency.resolve() == previous_dependency

    def offline(*args, **kwargs):
        raise AssertionError("Rollback unexpectedly attempted an installation")

    monkeypatch.setattr("speiihosting.manager.prepare", offline)
    manager.deploy(service.name, rollback=True)
    assert (
        site / "live/node_modules/local-dep/index.js"
    ).read_text() == "module.exports = 'dependency-one';"
    assert dependency.resolve() == dependency
    assert alive(store, service.name)


def test_public_verification_requires_an_explicit_successful_request(store, tmp_path, monkeypatch):
    service = Service(
        name="public-web", type="frontend", source=tmp_path, full_domain="web.example.com"
    )
    store.save_services({service.name: service})
    assert not store.resolve(service.name).public_verified
    real_client = httpx.Client
    seen = []

    def client(**kwargs):
        assert kwargs.get("trust_env") is False
        return real_client(
            transport=httpx.MockTransport(
                lambda request: seen.append(str(request.url)) or httpx.Response(200, text="ready")
            ),
            **kwargs,
        )

    monkeypatch.setattr("speiihosting.cli.httpx.Client", client)
    result = CliRunner().invoke(app, ["verify", service.name, "--json"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["public_url_verified"]
    assert seen == ["https://web.example.com/"]
    assert store.resolve(service.name).public_verified
