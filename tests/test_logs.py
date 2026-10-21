import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest
from typer.testing import CliRunner

from speiihosting.cli import app, clear_logs
from speiihosting.config import Service
from speiihosting.manager import Manager
from speiihosting.process import alive


def follow_logs(monkeypatch, actions, *arguments):
    actions = iter(actions)

    def advance(_):
        action = next(actions, None)
        if action is None:
            raise KeyboardInterrupt
        action()

    monkeypatch.setattr("speiihosting.cli.time.sleep", advance)
    return CliRunner().invoke(app, ["logs", "api", "-f", *arguments])


@pytest.fixture
def api_log(store, tmp_path):
    service = Service(name="api", type="backend", source=tmp_path, port=3001)
    store.save_services({service.name: service})
    return store.home / "logs/api.log"


def append(path, data):
    with path.open("ab") as handle:
        handle.write(data)


def test_follow_shows_new_lines_and_ctrl_c_exits_cleanly(api_log, monkeypatch):
    api_log.write_bytes(b"old line\n")
    result = follow_logs(monkeypatch, [lambda: append(api_log, b"new line\n")])
    assert result.exit_code == 0, result.output
    assert result.stdout == "old line\nnew line\n"
    assert "Following logs for api" in result.stderr


def test_follow_waits_for_a_missing_log_and_zero_lines_skips_history(api_log, monkeypatch):
    result = follow_logs(monkeypatch, [lambda: api_log.write_bytes(b"first line\n")], "-n", "0")
    assert result.exit_code == 0, result.output
    assert result.stdout == "first line\n"
    result = follow_logs(monkeypatch, [lambda: append(api_log, b"second line\n")], "-n", "0")
    assert result.exit_code == 0, result.output
    assert result.stdout == "second line\n"


@pytest.mark.parametrize("new", [b"new\n", b"first new line after clear\nsecond new line\n"])
def test_follow_reads_from_start_after_clear_and_immediate_regrowth(api_log, monkeypatch, new):
    api_log.write_bytes(b"old log line\n")

    def clear_and_write():
        clear_logs([api_log])
        append(api_log, new)

    result = follow_logs(monkeypatch, [clear_and_write])
    assert result.exit_code == 0, result.output
    assert result.stdout == "old log line\n" + new.decode()


def test_follow_retries_if_the_log_disappears_during_rotation(api_log, monkeypatch):
    api_log.write_bytes(b"before rotation\n")
    original_open = Path.open
    fail_once = [False]

    def rotating_open(path, *args, **kwargs):
        if path == api_log and fail_once[0]:
            fail_once[0] = False
            raise FileNotFoundError("Log rotated between polling and opening")
        return original_open(path, *args, **kwargs)

    def rotate():
        api_log.rename(api_log.with_suffix(".log.1"))
        api_log.write_bytes(b"after rotation\n")
        fail_once[0] = True

    monkeypatch.setattr(Path, "open", rotating_open)
    result = follow_logs(monkeypatch, [rotate, lambda: None])
    assert result.exit_code == 0, result.output
    assert result.stdout == "before rotation\nafter rotation\n"


def test_follow_preserves_utf8_and_crlf_split_between_polls(api_log, monkeypatch):
    api_log.write_bytes(b"before\r\n")
    chunks = [b"\xe2", b"\x82", b"\xac\r", b"\nafter\n"]
    result = follow_logs(
        monkeypatch, [lambda chunk=chunk: append(api_log, chunk) for chunk in chunks]
    )
    assert result.exit_code == 0, result.output
    assert result.stdout == "before\n€\nafter\n"


def test_live_backend_output_reaches_follower_and_viewer_exit_keeps_service_running(
    store, tmp_path, free_port, http_app
):
    source = tmp_path / "live-api"
    http_app(source)
    service = Manager(store).host("backend", source, port=free_port, install=False)
    output, status = tmp_path / "viewer.out", tmp_path / "viewer.err"

    def wait_for(path, text):
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if text in path.read_text(encoding="utf-8", errors="replace"):
                return
            assert viewer.poll() is None, status.read_text(errors="replace")
            time.sleep(0.05)
        pytest.fail(f"Live log viewer did not emit {text!r}")

    with output.open("wb") as stdout, status.open("wb") as stderr:
        viewer = subprocess.Popen(
            [sys.executable, "-m", "speiihosting", "logs", service.name, "-f", "-n", "0"],
            stdin=subprocess.DEVNULL,
            stdout=stdout,
            stderr=stderr,
        )
        try:
            wait_for(status, "Following logs")
            response = httpx.get(f"http://127.0.0.1:{free_port}/live-probe", trust_env=False)
            assert response.status_code == 200
            wait_for(output, "GET /live-probe")
        finally:
            viewer.terminate()
            try:
                viewer.wait(timeout=10)
            except subprocess.TimeoutExpired:
                viewer.kill()
                viewer.wait(timeout=5)
    assert alive(store, service.name)
    assert (
        httpx.get(f"http://127.0.0.1:{free_port}/still-running", trust_env=False).status_code == 200
    )
