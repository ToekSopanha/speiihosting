from __future__ import annotations

import json
import subprocess
import time

import httpx

from .config import Service, Settings, SpeiiError
from .storage import Store, atomic_write


class Cloudflare:
    def __init__(self, settings: Settings, client: httpx.Client | None = None):
        self.settings = settings
        self.client = client or httpx.Client(
            base_url="https://api.cloudflare.com/client/v4/",
            headers={
                "Authorization": "Bearer "
                + (
                    settings.cloudflare_api_token.get_secret_value()
                    if settings.cloudflare_api_token
                    else ""
                )
            },
            timeout=30,
            transport=httpx.HTTPTransport(retries=2),
        )

    def close(self) -> None:
        self.client.close()

    def request(self, method: str, path: str, **kwargs):
        try:
            for attempt in range(3):
                response = self.client.request(method, path.lstrip("/"), **kwargs)
                if (
                    method in {"GET", "PUT"}
                    and response.status_code in {429, 502, 503}
                    and attempt < 2
                ):
                    time.sleep(attempt + 1)
                    continue
                break
            data = response.json()
            if response.is_error or not data.get("success", False):
                messages = "; ".join(e.get("message", "API error") for e in data.get("errors", []))
                raise SpeiiError(
                    f"Cloudflare {response.status_code}: {messages or 'request failed'}"
                )
            return data
        except (httpx.HTTPError, ValueError) as error:
            # No request headers, bodies, or tokens in diagnostics.
            raise SpeiiError(
                "Cloudflare could not be reached or returned an invalid response."
            ) from error

    def zones(self) -> list[dict]:
        items = []
        page = 1
        while True:
            data = self.request("GET", "zones", params={"page": page, "per_page": 50})
            items.extend(data["result"])
            if page >= data.get("result_info", {}).get("total_pages", 1):
                return items
            page += 1

    def zone_for(self, hostname: str) -> dict:
        matches = [
            z for z in self.zones() if hostname == z["name"] or hostname.endswith("." + z["name"])
        ]
        if not matches:
            raise SpeiiError(
                f"No accessible Cloudflare zone for {hostname}. Token needs Zone Read and DNS Edit."
            )
        zone = max(matches, key=lambda z: len(z["name"]))
        if zone["account"]["id"] != self.settings.cloudflare_account_id:
            raise SpeiiError("The domain and tunnel must belong to the same Cloudflare account.")
        return zone

    @property
    def tunnel_path(self) -> str:
        if not self.settings.cloudflare_account_id or not self.settings.tunnel_id:
            raise SpeiiError("Run speiihos init to configure a Cloudflare tunnel.")
        return (
            f"accounts/{self.settings.cloudflare_account_id}/cfd_tunnel/{self.settings.tunnel_id}"
        )

    def create_tunnel(self) -> None:
        result = self.request(
            "POST",
            f"accounts/{self.settings.cloudflare_account_id}/cfd_tunnel",
            json={"name": self.settings.tunnel_name, "config_src": "cloudflare"},
        )["result"]
        self.settings.tunnel_id = result["id"]
        self.settings.tunnel_token = self.request("GET", self.tunnel_path + "/token")["result"]

    def bind(self, service: Service) -> None:
        zone = self.zone_for(service.full_domain)
        service.zone_id = zone["id"]
        target = f"{self.settings.tunnel_id}.cfargotunnel.com"
        endpoint = f"zones/{zone['id']}/dns_records"
        records = self.request("GET", endpoint, params={"name": service.full_domain})["result"]
        if records:
            if (
                len(records) != 1
                or records[0]["type"] != "CNAME"
                or records[0]["content"] != target
                or not records[0].get("proxied")
            ):
                raise SpeiiError(
                    f"DNS already exists for {service.full_domain}; it was left unchanged."
                )
            service.dns_record_id = records[0]["id"]
            return
        record = self.request(
            "POST",
            endpoint,
            json={
                "type": "CNAME",
                "name": service.full_domain,
                "content": target,
                "proxied": True,
                "ttl": 1,
            },
        )["result"]
        service.dns_record_id = record["id"]
        service.dns_owned = True

    def unbind(self, service: Service) -> None:
        if not service.dns_record_id or not service.zone_id or not service.dns_owned:
            return
        endpoint = f"zones/{service.zone_id}/dns_records/{service.dns_record_id}"
        record = self.request("GET", endpoint)["result"]
        if (
            record["type"] != "CNAME"
            or record["content"] != f"{self.settings.tunnel_id}.cfargotunnel.com"
        ):
            raise SpeiiError("DNS record changed outside Speii; refusing to delete it.")
        self.request("DELETE", endpoint)

    def configure(
        self, services: dict[str, Service], store: Store, old_domains: set[str] | None = None
    ) -> None:
        current = self.request("GET", self.tunnel_path + "/configurations")["result"]
        config = current.get("config") or {}
        owned = (old_domains or set()) | {s.full_domain for s in services.values() if s.full_domain}
        rules = [
            r for r in config.get("ingress", []) if r.get("hostname") and r["hostname"] not in owned
        ]
        rules.extend(
            {
                "hostname": s.full_domain,
                "service": f"http://127.0.0.1:{self.settings.nginx_port}",
                "originRequest": {"httpHostHeader": s.full_domain},
            }
            for s in services.values()
            if s.full_domain and s.status == "running"
        )
        rules.append({"service": "http_status:404"})
        config["ingress"] = rules
        self.request("PUT", self.tunnel_path + "/configurations", json={"config": config})
        atomic_write(store.home / "tunnel.yml", json.dumps(config, indent=2))

    def purge(self, service: Service) -> None:
        if not service.zone_id or not service.full_domain:
            raise SpeiiError("This service has no Cloudflare zone to purge.")
        # URL purges do not invalidate arbitrary SPA assets. Whole-zone purges require
        # explicit --all-zone, rather than evicting other sites unexpectedly.
        self.request(
            "POST",
            f"zones/{service.zone_id}/purge_cache",
            json={
                "files": [
                    f"https://{service.full_domain}/",
                    f"https://{service.full_domain}/index.html",
                ]
            },
        )


def local_command(store: Store, *args: str) -> subprocess.CompletedProcess:
    from .doctor import find_binary

    binary = find_binary("cloudflared", store)
    if not binary:
        raise SpeiiError("cloudflared is missing. Run speiihos doctor --install.")
    result = subprocess.run([binary, *args], text=True, capture_output=True)
    if result.returncode:
        raise SpeiiError(f"cloudflared failed: {result.stderr.strip()}")
    return result


def configure_local(store: Store, services: dict[str, Service]) -> None:
    settings = store.settings()
    rules = [
        {
            "hostname": s.full_domain,
            "service": f"http://127.0.0.1:{settings.nginx_port}",
            "originRequest": {"httpHostHeader": s.full_domain},
        }
        for s in services.values()
        if s.full_domain and s.status == "running"
    ]
    rules.append({"service": "http_status:404"})
    path = store.home / "tunnel.yml"
    data = json.dumps(
        {
            "tunnel": settings.tunnel_id,
            "credentials-file": str(settings.tunnel_credentials),
            "ingress": rules,
        },
        indent=2,
    )
    if not path.exists() or path.read_text(encoding="utf-8") != data:
        atomic_write(path, data)


def sync_routes(
    store: Store, services: dict[str, Service], old_domains: set[str] | None = None
) -> None:
    settings = store.settings()
    if settings.tunnel_mode == "local":
        configure_local(store, services)
    else:
        client = Cloudflare(settings)
        try:
            client.configure(services, store, old_domains)
        finally:
            client.close()
