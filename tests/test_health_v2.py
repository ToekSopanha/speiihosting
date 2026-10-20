import json
import time

import httpx
import pytest
from typer.testing import CliRunner

from speiihosting.cli import app
from speiihosting.config import HealthCheck, Service, SpeiiError
from speiihosting.health import probe
from speiihosting.manager import Manager
from speiihosting.process import alive
from speiihosting.storage import read_json


def app_source(source, code=200, body="ready"):
    source.mkdir(exist_ok=True)
    (source / "main.py").write_text(
        "from http.server import HTTPServer,BaseHTTPRequestHandler\nimport os\nfrom pathlib import Path\n"
        "class Handler(BaseHTTPRequestHandler):\n"
        " def do_GET(self):\n"
        "  code = 503 if (Path(os.environ['SPEII_DATA_DIR'])/'unhealthy').exists() else "
        + str(code)
        + "\n"
        "  self.send_response(code); self.end_headers(); self.wfile.write("
        + repr(body.encode())
        + ")\n"
        "HTTPServer(('127.0.0.1',int(os.environ['PORT'])),Handler).serve_forever()\n"
    )


def eventually(predicate, timeout=10):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.1)
    raise AssertionError("Timed out waiting for health transition")


def test_http_health_failure_restores_last_working_release(store, tmp_path, free_port, monkeypatch):
    source = tmp_path / "checked-api"
    app_source(source)
    monkeypatch.setenv("HTTP_PROXY", "http://invalid.proxy:1")
    monkeypatch.setenv("HTTPS_PROXY", "http://invalid.proxy:1")
    manager = Manager(store)
    service = manager.host(
        "backend",
        source,
        port=free_port,
        install=False,
        health=HealthCheck(path="/health", expected_body="ready", startup_timeout=2),
    )
    assert probe(service)["status"] == "healthy"
    app_source(source, code=503)
    with pytest.raises(SpeiiError, match="did not become ready"):
        manager.deploy(service.name, install=False)
    assert probe(store.resolve(service.name))["status"] == "healthy"
    assert "else 200" in (store.site(service.name) / "live/main.py").read_text()
    assert alive(store, service.name)


def test_ongoing_health_failure_restarts_one_service(store, tmp_path, free_port):
    source = tmp_path / "monitored-api"
    app_source(source)
    service = Manager(store).host(
        "backend",
        source,
        port=free_port,
        install=False,
        health=HealthCheck(
            path="/health", expected_body="ready", interval=1, failures=1, startup_timeout=3
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
    vendor = source / "vendor/local-dep"
    vendor.mkdir(parents=True)
    (source / "package.json").write_text(
        json.dumps(
            {
                "name": "node-worker",
                "scripts": {"start": "node bot.js"},
                "dependencies": {"local-dep": "file:./vendor/local-dep"},
            }
        )
    )
    (vendor / "package.json").write_text('{"name":"local-dep","version":"1.0.0","main":"index.js"}')
    (vendor / "index.js").write_text("module.exports = 'dependency-one';")
    (source / "bot.js").write_text(
        "console.log(require('local-dep')); setInterval(() => {}, 1000);"
    )
    (source / ".env").write_text(
        f"NPM_CONFIG_CACHE={tmp_path / 'npm-cache'}\nNPM_CONFIG_UPDATE_NOTIFIER=false\n"
    )
    manager = Manager(store)
    service = manager.host("bot", source)
    (vendor / "index.js").write_text("module.exports = 'dependency-two';")
    manager.deploy(service.name)
    site = store.site(service.name)
    assert (site / "previous/node_modules/local-dep/index.js").exists()

    def offline(*args, **kwargs):
        raise AssertionError("Rollback unexpectedly attempted an installation")

    monkeypatch.setattr("speiihosting.manager.prepare", offline)
    manager.deploy(service.name, rollback=True)
    assert (
        site / "live/node_modules/local-dep/index.js"
    ).read_text() == "module.exports = 'dependency-one';"
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
