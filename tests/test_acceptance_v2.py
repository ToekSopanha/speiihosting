import sys
import time
from types import SimpleNamespace

import psutil
import pytest

from speiihosting.config import Service, SpeiiError
from speiihosting.inspection import describe
from speiihosting.manager import Manager
from speiihosting.process import alive, ensure_daemon
from speiihosting.security import KeyringCredentials
from speiihosting.storage import read_json, write_json


def eventually(predicate, timeout=10):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.1)
    raise AssertionError("Timed out waiting for expected state")


def test_new_backend_never_auto_links_existing_frontends(store, tmp_path, monkeypatch):
    fronts = {
        name: Service(
            name=name, type="frontend", source=tmp_path, full_domain=f"{name}.example.com"
        )
        for name in ("web", "admin")
    }
    store.save_services(fronts)
    source = tmp_path / "api"
    source.mkdir()
    (source / "main.py").write_text("print('private backend')")
    monkeypatch.setattr("speiihosting.ports.available", lambda _: True)
    monkeypatch.setattr("speiihosting.manager.ensure_daemon", lambda _: None)
    monkeypatch.setattr("speiihosting.manager.wait_service", lambda *a, **kw: None)
    monkeypatch.setattr("speiihosting.nginx.Nginx.apply", lambda *a, **kw: None)
    service = Manager(store).host("backend", source, port=8000, install=False)
    assert not service.full_domain
    assert all(store.resolve(name).backend is None for name in fronts)
    assert store.settings().tunnel_id is None


def test_unlink_removes_only_the_explicit_api_mapping(store, tmp_path, monkeypatch):
    front = Service(
        name="web", type="frontend", source=tmp_path, full_domain="web.example.com", backend="api"
    )
    back = Service(name="api", type="backend", source=tmp_path, port=8000)
    store.save_services({"web": front, "api": back})
    assert describe(store, back)["routes"][0]["url"] == "https://web.example.com/api"
    monkeypatch.setattr("speiihosting.nginx.Nginx.apply", lambda *a, **kw: None)
    Manager(store).unlink("web")
    assert store.resolve("web").backend is None
    assert store.resolve("web").full_domain == "web.example.com"
    assert store.resolve("api").status == "running"
    assert describe(store, back)["routes"] == []


def test_idle_supervisor_does_not_rewrite_metrics_every_tick(store):
    settings = store.settings()
    settings.metrics_interval = 5
    store.save_settings(settings)
    ensure_daemon(store)
    runtime = store.home / "runtime.json"
    eventually(runtime.exists)
    first = read_json(runtime)["updated"]
    time.sleep(1)
    assert read_json(runtime)["updated"] == first


@pytest.mark.parametrize("fault", ["infrastructure", "invalid_journal"])
def test_unrelated_worker_is_restarted_despite_another_service_failure(
    store, tmp_path, monkeypatch, fault
):
    # Prevent a system cloudflared installation from using any personal config.
    monkeypatch.setenv("PATH", str(tmp_path / "empty-bin"))
    source = tmp_path / "healthy"
    source.mkdir()
    (source / "bot.py").write_text("import time\nwhile True: time.sleep(1)\n")
    service = Manager(store).host("bot", source, install=False)
    original = read_json(store.home / "pids/healthy.json")
    if fault == "infrastructure":
        services = store.services()
        services["broken-web"] = Service(
            name="broken-web",
            type="frontend",
            source=tmp_path,
            full_domain="unconfigured.example.com",
        )
        store.save_services(services)
    else:
        directory = store.site("broken-worker")
        directory.mkdir()
        write_json(directory / "transaction.json", {"schema_version": 99})
    psutil.Process(original["pid"]).terminate()

    def restarted():
        current = read_json(store.home / "pids/healthy.json", {})
        return current.get("pid") != original["pid"] and alive(store, service.name)

    eventually(restarted)
    if fault == "invalid_journal":
        assert (store.site("broken-worker") / "transaction.json").exists()


def test_plaintext_keyring_is_rejected_even_when_available(tmp_path, monkeypatch):
    backend = type("PlaintextKeyring", (), {"__module__": "keyrings.alt.file", "priority": 1})()
    fake = SimpleNamespace(get_keyring=lambda: backend, set_keyring=lambda _: None)
    monkeypatch.setitem(sys.modules, "keyring", fake)
    with pytest.raises(SpeiiError, match="secure OS keyring"):
        KeyringCredentials(tmp_path)
