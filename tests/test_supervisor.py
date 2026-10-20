import sys
import time
from types import SimpleNamespace

import httpx
import pytest

from speiihosting.config import SpeiiError
from speiihosting.manager import Manager
from speiihosting.process import Worker, alive, close_logger, logger_for, stop_daemon


def eventually(predicate, timeout=10):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.1)
    raise AssertionError("Timed out waiting for condition")


def test_bot_isolation_deploy_rollback_and_lifecycle(store, tmp_path):
    source = tmp_path / "my-bot"
    source.mkdir()
    (source / ".env").write_text("BOT_TEST_TOKEN=env-loaded\n")

    def write_bot(version):
        (source / "bot.py").write_text(
            "import os,time\nprint('"
            + version
            + "', os.environ.get('BOT_TEST_TOKEN'), flush=True)\n"
            "while True: time.sleep(0.1)\n"
        )

    write_bot("v1")
    manager = Manager(store)
    service = manager.host("bot", source, install=False)
    log = store.home / "logs/my-bot.log"
    eventually(lambda: log.exists() and "v1 env-loaded" in log.read_text())
    assert alive(store, "speii-daemon")
    write_bot("v2")
    assert "v1" in (store.site(service.name) / "live/bot.py").read_text()
    manager.deploy(service.name, install=False)
    eventually(lambda: "v2 env-loaded" in log.read_text())
    assert "v1" in (store.site(service.name) / "previous/bot.py").read_text()
    manager.deploy(service.name, install=False, rollback=True)
    assert "v1" in (store.site(service.name) / "live/bot.py").read_text()
    manager.lifecycle(service.name, "stop")
    assert not alive(store, service.name)
    manager.lifecycle(service.name, "start")
    assert alive(store, service.name)
    manager.remove(service.name)
    assert store.services() == {}
    assert not store.site(service.name).exists()


def test_backend_has_no_cloudflare_dependency_and_restores_after_daemon_restart(
    store, tmp_path, free_port, http_app
):
    source = tmp_path / "backend"
    http_app(source, body="local API")
    manager = Manager(store)
    service = manager.host("backend", source, port=free_port, install=False)
    assert not service.full_domain
    assert not store.settings().tunnel_id
    assert httpx.get(f"http://127.0.0.1:{free_port}", trust_env=False).text == "local API"
    assert store.resolve(str(free_port)).name == service.name
    stop_daemon(store)
    assert not alive(store, service.name)
    manager.lifecycle(str(free_port), "start")
    assert httpx.get(f"http://127.0.0.1:{free_port}", trust_env=False).text == "local API"


def test_failed_deploy_recovers_old_live_release(store, tmp_path):
    source = tmp_path / "resilient"
    source.mkdir()
    file = source / "bot.py"
    file.write_text("import time\nwhile True: time.sleep(1)\n")
    manager = Manager(store)
    service = manager.host("bot", source, install=False)
    file.write_text("raise RuntimeError('broken deployment')\n")
    with pytest.raises(SpeiiError):
        manager.deploy(service.name, install=False)
    assert "while True" in (store.site(service.name) / "live/bot.py").read_text()
    assert alive(store, service.name)


def test_crash_backoff_does_not_stop_other_workers(store, tmp_path, monkeypatch):
    clock = [0.0]
    monkeypatch.setattr(
        "speiihosting.process.time",
        SimpleNamespace(monotonic=lambda: clock[0], sleep=time.sleep, time=time.time),
    )
    broken = Worker(store, "broken", [sys.executable, "-c", "raise SystemExit(1)"], tmp_path, 1)
    healthy = Worker(
        store, "healthy", [sys.executable, "-c", "import time; time.sleep(60)"], tmp_path, 1
    )
    try:
        healthy.tick()
        for _ in range(7):
            broken.tick()
            if broken.process:
                broken.process.wait(timeout=5)
            clock[0] += 0.1
            broken.tick()
            clock[0] = broken.retry_at + 0.1
        assert broken.crashed
        assert healthy.status()["status"] == "running"
    finally:
        broken.stop()
        healthy.stop()


def test_log_rotation_is_bounded(tmp_path, monkeypatch):
    monkeypatch.setattr("speiihosting.process.LOG_BYTES", 10_000)
    path = tmp_path / "bounded.log"
    logger = logger_for(path)
    try:
        for _ in range(50):
            logger.info("x" * 1000)
    finally:
        close_logger(logger)
    logs = list(tmp_path.glob("bounded.log*"))
    assert len(logs) == 2
    assert all(p.stat().st_size <= 10_000 for p in logs)
