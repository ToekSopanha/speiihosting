from __future__ import annotations

import mimetypes
import subprocess
from pathlib import Path

from .config import Service, SpeiiError
from .storage import Store, atomic_write


def quote(path: Path) -> str:
    value = path.as_posix()
    if any(c in value for c in ("\n", "\r", "\0", "$")):
        raise SpeiiError("Nginx paths cannot contain control characters or dollar signs.")
    return '"' + value.replace('"', '\\"') + '"'


def proxy(port: int, prefix: str = "/", strip: bool = False, streaming: bool = False) -> str:
    target = f"http://speii_{port}" + ("/" if strip else "")
    return f"""    location {prefix} {{
        proxy_pass {target};
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $speii_scheme;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection $speii_connection;
        proxy_read_timeout 300s;
        proxy_connect_timeout 5s;
        proxy_buffering {"off" if streaming else "on"};
    }}
"""


def render_site(service: Service, services: dict[str, Service], store: Store) -> str:
    settings = store.settings()
    live = store.site(service.name) / "live"
    headers = "        add_header X-Content-Type-Options nosniff always;\n        add_header Referrer-Policy same-origin always;\n"
    text = f"""server {{
    listen 127.0.0.1:{settings.nginx_port};
    server_name {service.full_domain};
    location ~ (^|/)\\. {{ deny all; }}
"""
    if service.backend:
        backend = services.get(service.backend)
        if backend is None or backend.type != "backend" or not backend.port:
            raise SpeiiError(f"Backend {service.backend!r} is missing or invalid.")
        prefix = service.api_prefix
        if backend.status == "running":
            text += f"    location = {prefix} {{ return 308 {prefix}/; }}\n"
            text += proxy(backend.port, prefix + "/", strip=True, streaming=backend.streaming)
        else:
            text += f"    location {prefix} {{ return 503; }}\n"
    if service.type == "frontend":
        text += f"""    root {quote(live)};
    index index.html;
    location / {{ try_files $uri $uri/ /index.html; add_header Cache-Control "no-cache";
{headers}    }}
    location ~* "[.-][a-f0-9]{{8,64}}\\.(js|css|png|jpg|jpeg|gif|svg|woff2?|ico)$" {{
        try_files $uri =404;
        add_header Cache-Control "public, max-age=31536000, immutable";
{headers}    }}
    location ~* ^/(assets|static)/.*\\.(js|css|png|jpg|jpeg|gif|svg|woff2?|ico)$ {{
        try_files $uri =404;
        add_header Cache-Control "public, max-age=3600";
{headers}    }}
"""
    elif service.port:
        if service.framework == "Next.js" and (live / ".next/static").is_dir():
            text += f"""    location /_next/static/ {{
        alias {quote(live / ".next/static")[:-1]}/";
        expires 1y;
        add_header Cache-Control "public, immutable";
{headers}
    }}
"""
        if service.framework == "Django" and (live / "staticfiles").is_dir():
            text += f'    location /static/ {{ alias {quote(live / "staticfiles")[:-1]}/"; expires 1d; }}\n'
        text += proxy(service.port, streaming=service.streaming)
    return text + "}\n"


class Nginx:
    def __init__(self, store: Store):
        self.store = store
        self.root = store.home / "nginx"
        self.conf = self.root / "nginx.conf"
        self.sites = self.root / "speiihosting.d"

    def command(self, *arguments: str) -> list[str]:
        from .doctor import find_binary

        binary = find_binary("nginx", self.store)
        if not binary:
            raise SpeiiError("Nginx is missing. Run speiihos doctor --install.")
        return [binary, "-p", self.root.as_posix() + "/", "-c", str(self.conf), *arguments]

    def main_config(self, services: dict[str, Service] | None = None) -> str:
        # nginx resolves relative paths (including its startup error log) against
        # the prefix root set by -p.  Create every directory nginx may write into
        # so it can open its startup log even before parsing the config file.
        # This is the root cause of the Windows "CreateFile … logs/error.log …
        # The system cannot find the path specified" error.
        for directory in (
            "logs",  # nginx startup error log lives here under the prefix
            "client_temp",
            "proxy_temp",
            "fastcgi_temp",
            "uwsgi_temp",
            "scgi_temp",
        ):
            (self.root / directory).mkdir(exist_ok=True)
        types: dict[str, list[str]] = {}
        for extension, content_type in {
            **mimetypes.types_map,
            ".js": "application/javascript",
            ".mjs": "application/javascript",
            ".wasm": "application/wasm",
        }.items():
            if extension[1:].isalnum():
                types.setdefault(content_type, []).append(extension[1:])
        mime = "\n".join(
            f"        {key} {' '.join(values)};" for key, values in sorted(types.items())
        )
        upstreams = "\n".join(
            f"    upstream speii_{port} {{ server 127.0.0.1:{port}; keepalive 16; }}"
            for port in sorted({s.port for s in (services or {}).values() if s.port})
        )
        return f"""worker_processes 1;
pid {quote(self.store.home / "pids/nginx.pid")};
# error_log here uses an absolute path so it works on all platforms, but nginx
# also writes a startup log relative to the -p prefix before reading this file.
# The logs/ directory under the prefix is created by main_config() above.
error_log {quote(self.store.home / "logs/nginx_error.log")} warn;
events {{ worker_connections 1024; }}
http {{
    types {{
{mime}
    }}
    default_type application/octet-stream;
    server_tokens off;
    sendfile on;
    client_max_body_size 10m;
    client_body_timeout 15s;
    client_header_timeout 15s;
    keepalive_timeout 30s;
    # Increase bucket size to accommodate long subdomain names (e.g. portfolio.example.com).
    # The default of 32 bytes is too small and causes nginx to refuse to start.
    server_names_hash_bucket_size 128;
    add_header X-Content-Type-Options nosniff always;
    add_header Referrer-Policy same-origin always;
    access_log {quote(self.store.home / "logs/nginx_access.log")} combined;
    client_body_temp_path {quote(self.root / "client_temp")};
    proxy_temp_path {quote(self.root / "proxy_temp")};
    fastcgi_temp_path {quote(self.root / "fastcgi_temp")};
    uwsgi_temp_path {quote(self.root / "uwsgi_temp")};
    scgi_temp_path {quote(self.root / "scgi_temp")};
    gzip on;
    gzip_types text/css application/javascript application/json image/svg+xml;
    map $http_upgrade $speii_connection {{ default upgrade; '' ''; }}
    map $http_x_forwarded_proto $speii_scheme {{ default $scheme; https https; }}
    server {{ listen 127.0.0.1:{self.store.settings().nginx_port} default_server; server_name _; return 404; }}
{upstreams}
    include {quote(self.sites / "*.conf")};
}}
"""

    def signal(self, action: str) -> None:
        result = subprocess.run(
            self.command("-s", action), capture_output=True, text=True, timeout=15
        )
        if result.returncode:
            raise SpeiiError(f"Nginx {action} failed: {result.stderr.strip()}")

    def apply(self, services: dict[str, Service]) -> None:
        """Restore the entire managed configuration if validation or reload fails."""
        old = {p: p.read_bytes() for p in [self.conf, *self.sites.iterdir()] if p.is_file()}
        try:
            atomic_write(self.conf, self.main_config(services))
            for path in self.sites.iterdir():
                if path.suffix in {".conf", ".disabled"}:
                    path.unlink()
            for service in services.values():
                if service.full_domain:
                    suffix = ".conf" if service.status == "running" else ".conf.disabled"
                    atomic_write(
                        self.sites / (service.name + suffix),
                        render_site(service, services, self.store),
                    )
            result = subprocess.run(self.command("-t"), capture_output=True, text=True, timeout=15)
            if result.returncode:
                raise SpeiiError(f"Nginx rejected the configuration: {result.stderr.strip()}")
            from .process import alive

            if alive(self.store, "nginx"):
                self.signal("reload")
        except Exception:
            for path in [self.conf, *self.sites.iterdir()]:
                if path.is_file():
                    path.unlink()
            for path, data in old.items():
                atomic_write(path, data)
            raise
