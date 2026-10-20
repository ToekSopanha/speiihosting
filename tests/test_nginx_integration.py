"""Use a real Nginx if SPEII_TEST_NGINX or a system installation is available.

The tunnel connector and API calls are replaced; no Cloudflare credentials or
public DNS changes are required for this local routing test.
"""

import os
import shutil
import socket
import sys

import httpx
import pytest

from speiihosting.config import SpeiiError
from speiihosting.manager import Manager

NGINX = os.environ.get("SPEII_TEST_NGINX") or shutil.which("nginx")
pytestmark = pytest.mark.skipif(not NGINX or os.name == "nt", reason="requires POSIX Nginx")


def test_real_nginx_spa_proxy_stop_deploy_and_rollback(store, tmp_path, monkeypatch, free_port):
    (store.home / "bin/nginx").symlink_to(NGINX)
    connector = store.home / "bin/cloudflared"
    connector.write_text(f"#!{sys.executable}\nimport time\nwhile True: time.sleep(1)\n")
    connector.chmod(0o700)
    settings = store.settings()
    settings.nginx_port = free_port
    settings.default_domain = "example.com"
    settings.tunnel_id, settings.tunnel_token = "test-tunnel", "test-token"
    store.save_settings(settings)
    monkeypatch.setattr("speiihosting.cloudflare.sync_routes", lambda *args, **kw: None)
    monkeypatch.setattr("speiihosting.cloudflare.Cloudflare.bind", lambda *args, **kw: None)
    source = tmp_path / "web"
    source.mkdir()
    (source / "index.html").write_text("<h1>release one</h1>")
    (source / "assets").mkdir()
    (source / "assets/app.1234abcd.js").write_text("console.log('hashed');")
    (source / "assets/logo.svg").write_text("<svg></svg>")
    (source / ".env").write_text("SHOULD_NEVER_BE_SERVED=secret")
    backend = tmp_path / "api"
    backend.mkdir()
    (backend / "main.py").write_text(
        "from http.server import HTTPServer,BaseHTTPRequestHandler\nimport os\n"
        "class Handler(BaseHTTPRequestHandler):\n"
        " def do_GET(self):\n"
        "  self.send_response(200); self.end_headers(); self.wfile.write(self.path.encode())\n"
        "HTTPServer(('127.0.0.1',int(os.environ['PORT'])),Handler).serve_forever()\n"
    )
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        backend_port = sock.getsockname()[1]
    manager = Manager(store)
    manager.host("backend", backend, port=backend_port, install=False)
    front = manager.host("frontend", source, subdomain="web", install=False)
    assert front.backend is None
    manager.link(front.name, "api", "/api")
    other = manager.host("frontend", source, name="other", subdomain="other", install=False)
    with httpx.Client(
        base_url=f"http://127.0.0.1:{free_port}", headers={"Host": front.full_domain}
    ) as client:
        assert "release one" in client.get("/some/client/route").text
        assert client.get("/.env").status_code == 403
        assert client.get("/assets/missing.js").status_code == 404
        assert client.get("/").headers["cache-control"] == "no-cache"
        assert "immutable" in client.get("/assets/app.1234abcd.js").headers["cache-control"]
        assert "immutable" not in client.get("/assets/logo.svg").headers["cache-control"]
        assert client.get("/assets/logo.svg").headers["x-content-type-options"] == "nosniff"
        assert client.get("/api/ping").text == "/ping"
        (source / "index.html").write_text("<h1>release two</h1>")
        assert "release one" in client.get("/").text
        manager.deploy(front.name, install=False)
        assert "release two" in client.get("/").text
        manager.deploy(front.name, rollback=True, install=False)
        assert "release one" in client.get("/").text
        manager.lifecycle(front.name, "stop")
        assert client.get("/").status_code == 404
        assert (store.home / "nginx/speiihosting.d/web.conf.disabled").exists()
        manager.lifecycle(front.name, "start")
        assert "release one" in client.get("/").text
        # A build failure must preserve the serving files and previous release.
        service = store.resolve(front.name)
        service.build_command = '"' + sys.executable + '" -c "raise SystemExit(1)"'
        services = store.services()
        services[front.name] = service
        store.save_services(services)
        with pytest.raises(SpeiiError, match="command failed"):
            manager.deploy(front.name, install=False)
        assert "release one" in client.get("/").text
    manager.remove(front.name)
    manager.remove(other.name)
