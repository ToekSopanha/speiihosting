import json
import subprocess

import httpx
import pytest

from speiihosting.cloudflare import Cloudflare
from speiihosting.config import Service, Settings, SpeiiError
from speiihosting.nginx import Nginx, render_site


def api_client(handler):
    settings = Settings(
        cloudflare_account_id="account", cloudflare_api_token="secret", tunnel_id="tunnel"
    )
    client = httpx.Client(
        base_url="https://api.cloudflare.com/client/v4/", transport=httpx.MockTransport(handler)
    )
    return Cloudflare(settings, client)


def test_dns_creation_and_reused_record_ownership(tmp_path):
    calls = []
    records = []

    def handler(request):
        calls.append(request)
        if request.url.path.endswith("/zones"):
            result = [{"id": "zone", "name": "example.com", "account": {"id": "account"}}]
        elif request.method == "POST":
            data = json.loads(request.content)
            assert data["proxied"] is True
            assert data["content"] == "tunnel.cfargotunnel.com"
            result = {"id": "dns", **data}
            records.append(result)
        else:
            result = records
        return httpx.Response(200, json={"success": True, "result": result})

    client = api_client(handler)
    service = Service(name="site", type="frontend", source=tmp_path, full_domain="app.example.com")
    client.bind(service)
    assert service.dns_owned and service.dns_record_id == "dns"
    reused = service.model_copy(update={"dns_owned": False})
    client.bind(reused)
    assert not reused.dns_owned
    assert sum(r.method == "POST" for r in calls) == 1


def test_dns_conflict_does_not_overwrite(tmp_path):
    methods = []

    def handler(request):
        methods.append(request.method)
        result = (
            [{"id": "zone", "name": "example.com", "account": {"id": "account"}}]
            if request.url.path.endswith("/zones")
            else [{"type": "A", "content": "1.2.3.4"}]
        )
        return httpx.Response(200, json={"success": True, "result": result})

    client = api_client(handler)
    with pytest.raises(SpeiiError, match="left unchanged"):
        client.bind(
            Service(name="site", type="frontend", source=tmp_path, full_domain="app.example.com")
        )
    assert methods == ["GET", "GET"]


def test_ingress_preserves_other_hosts_and_never_exposes_backends(store, tmp_path):
    submitted = []

    def handler(request):
        if request.method == "PUT":
            submitted.append(json.loads(request.content))
            result = {}
        else:
            result = {
                "config": {
                    "ingress": [
                        {"hostname": "other.example.com", "service": "http://localhost:9999"},
                        {"hostname": "removed.example.com", "service": "http://localhost:80"},
                        {"service": "http_status:404"},
                    ]
                }
            }
        return httpx.Response(200, json={"success": True, "result": result})

    client = api_client(handler)
    front = Service(name="front", type="frontend", source=tmp_path, full_domain="app.example.com")
    back = Service(name="api", type="backend", source=tmp_path, port=8000)
    client.configure({"front": front, "api": back}, store, {"removed.example.com"})
    rules = submitted[0]["config"]["ingress"]
    assert [r.get("hostname") for r in rules] == ["other.example.com", "app.example.com", None]
    assert rules[-1] == {"service": "http_status:404"}
    assert "8000" not in json.dumps(submitted)


def test_nginx_validation_failure_restores_files(store, monkeypatch, tmp_path):
    nginx = Nginx(store)
    nginx.conf.write_text("old main")
    (nginx.sites / "existing.conf").write_text("old site")
    monkeypatch.setattr(nginx, "command", lambda *args: ["nginx", *args])
    monkeypatch.setattr(
        subprocess, "run", lambda *a, **kw: subprocess.CompletedProcess(a, 1, "", "bad syntax")
    )
    front = Service(name="site", type="frontend", source=tmp_path, full_domain="app.example.com")
    with pytest.raises(SpeiiError, match="bad syntax"):
        nginx.apply({"site": front})
    assert nginx.conf.read_text() == "old main"
    assert (nginx.sites / "existing.conf").read_text() == "old site"
    assert not (nginx.sites / "site.conf").exists()


@pytest.mark.parametrize("strip_prefix", [True, False])
def test_nginx_spa_backend_binding_and_websockets(store, tmp_path, strip_prefix):
    front = Service(
        name="web",
        type="frontend",
        source=tmp_path,
        full_domain="web.example.com",
        backend="api",
        api_strip_prefix=strip_prefix,
    )
    back = Service(name="api", type="backend", source=tmp_path, port=8000)
    rendered = render_site(front, {"web": front, "api": back}, store)
    assert f"127.0.0.1:{store.settings().nginx_port};" in rendered
    assert "try_files $uri $uri/ /index.html" in rendered
    assert "location /api/" in rendered
    target = "http://speii_8000/" if strip_prefix else "http://speii_8000"
    assert f"proxy_pass {target};" in rendered
    assert "Upgrade $http_upgrade" in rendered
    assert "deny all" in rendered
    back.status = "stopped"
    assert "return 503" in render_site(front, {"web": front, "api": back}, store)


def test_local_backend_lifecycle_does_not_update_cloudflare(store, tmp_path, monkeypatch):
    from speiihosting.manager import Manager

    front = Service(
        name="web", type="frontend", source=tmp_path, full_domain="web.example.com", backend="api"
    )
    backend = Service(name="api", type="backend", source=tmp_path, port=8000)
    old = {"web": front, "api": backend}
    changed = {"web": front, "api": backend.model_copy(update={"status": "stopped"})}
    calls = []
    monkeypatch.setattr(Nginx, "apply", lambda *args: calls.append("nginx"))
    monkeypatch.setattr(
        "speiihosting.cloudflare.sync_routes", lambda *args: calls.append("cloudflare")
    )
    Manager(store).routing(changed, old)
    assert calls == ["nginx"]
