import socket

import pytest

from speiihosting.config import Settings
from speiihosting.process import stop_daemon
from speiihosting.storage import Store


@pytest.fixture
def http_app():
    """Write a concurrent loopback app without depending on runner DNS settings."""

    def write(source, code=200, body="ready"):
        source.mkdir(exist_ok=True)
        payload = repr(body.encode()) if body is not None else "self.path.encode()"
        (source / "main.py").write_text(
            "from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler\n"
            "from socketserver import TCPServer\n"
            "from pathlib import Path\nimport os\n"
            "class LocalHTTPServer(ThreadingHTTPServer):\n"
            " def server_bind(self):\n"
            "  TCPServer.server_bind(self)\n"
            "  self.server_name = 'localhost'\n"
            "  self.server_port = self.server_address[1]\n"
            "class Handler(BaseHTTPRequestHandler):\n"
            " timeout = 2\n"
            " def do_GET(self):\n"
            "  code = 503 if (Path(os.environ['SPEII_DATA_DIR'])/'unhealthy').exists() "
            f"else {code}\n"
            f"  body = {payload}\n"
            "  self.send_response(code)\n"
            "  self.send_header('Content-Length', str(len(body)))\n"
            "  self.end_headers()\n"
            "  self.wfile.write(body)\n"
            "LocalHTTPServer(('127.0.0.1',int(os.environ['PORT'])),Handler).serve_forever()\n"
        )

    return write


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    value = item.funcargs.get("store")
    if report.failed and value is not None:
        # Preserve bounded runtime evidence in CI output before fixture teardown.
        # Configuration and credential files are deliberately excluded.
        paths = [value.home / "runtime.json", *sorted((value.home / "logs").glob("*.log"))]
        for path in paths:
            try:
                with path.open("rb") as handle:
                    handle.seek(max(0, path.stat().st_size - 8192))
                    tail = handle.read(8192).decode("utf-8", errors="replace")
            except OSError:
                continue
            report.sections.append((f"SpeiiHosting {path.name}", tail))


@pytest.fixture
def store(tmp_path, monkeypatch):
    home = tmp_path / "state"
    monkeypatch.setenv("SPEIIHOSTING_HOME", str(home))
    value = Store(home)
    value.save_settings(Settings(autostart=False))
    yield value
    stop_daemon(value)


@pytest.fixture
def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]
