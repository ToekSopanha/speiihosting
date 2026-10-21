from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator


class SpeiiError(Exception):
    """An actionable error that can be displayed without a traceback."""


def valid_name(value: str) -> str:
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,62}", value):
        raise ValueError("Names must be 1–63 letters, numbers, underscores or hyphens.")
    if value.lower() in {"nginx", "cloudflared", "speii-daemon", "size", "clear", "sleep"}:
        raise ValueError(f"{value!r} is reserved.")
    return value


def valid_domain(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.rstrip(".").lower().encode("idna").decode("ascii")
    labels = value.split(".")
    if (
        len(labels) < 2
        or len(value) > 253
        or any(not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label) for label in labels)
    ):
        raise ValueError("Enter a domain such as example.com, without a scheme or path.")
    return value


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    schema_version: Literal[2] = 2
    cloudflare_account_id: str | None = None
    cloudflare_api_token: SecretStr | None = None
    tunnel_id: str | None = None
    tunnel_token: SecretStr | None = None
    tunnel_name: str = "speiihosting-home-server"
    tunnel_mode: Literal["remote", "local"] = "remote"
    tunnel_credentials: Path | None = None
    default_domain: str | None = None
    sleep_prevent: bool = False
    autostart: bool = True
    nginx_port: int = Field(default=8080, ge=1, le=65535)
    metrics_interval: float = Field(default=2, ge=1, le=60)
    release_budget_mb: int = Field(default=4096, ge=32)
    credential_store: Literal["file", "keyring"] = "file"

    _domain = field_validator("default_domain")(valid_domain)

    def disk_data(self) -> dict:
        data = self.model_dump(mode="json")
        for key in ("cloudflare_api_token", "tunnel_token"):
            data.pop(key, None)
        return data


class HealthCheck(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    path: str = "/"
    expected_status: int | None = Field(default=200, ge=100, le=599)
    expected_body: str | None = Field(default=None, max_length=4096)
    timeout: float = Field(default=2, gt=0, le=30)
    interval: float = Field(default=5, ge=1, le=3600)
    failures: int = Field(default=3, ge=1, le=20)
    startup_timeout: float = Field(default=30, ge=2, le=600)

    @field_validator("path")
    @classmethod
    def check_path(cls, value: str) -> str:
        if not value.startswith("/") or value.startswith("//") or any(c in value for c in "\r\n\0"):
            raise ValueError("Health path must be a local HTTP path.")
        return value


class Resources(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    memory_mb: int = Field(default=512, ge=32, le=1048576)
    cpus: float = Field(default=1, gt=0, le=256)
    pids: int = Field(default=128, ge=16, le=65536)


class Service(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    schema_version: Literal[2] = 2
    name: str
    type: Literal["frontend", "dynamic", "backend", "bot"]
    source: Path
    static_dir: str | None = None
    full_domain: str | None = None
    zone_id: str | None = None
    dns_record_id: str | None = None
    # A reused CNAME is never deleted by remove.
    dns_owned: bool = False
    port: int | None = Field(default=None, ge=1, le=65535)
    command: list[str] = Field(default_factory=list)
    custom_command: str | None = None
    build_command: str | None = None
    framework: str = "custom"
    environment_dir: Path | None = None
    external: bool = False
    status: Literal["running", "stopped"] = "running"
    autostart: bool = True
    generation: int = 1
    backend: str | None = None
    api_prefix: str = "/api"
    api_strip_prefix: bool = True
    env_allow: list[str] = Field(default_factory=list)
    health: HealthCheck | None = None
    isolation: Literal["process", "podman"] = "process"
    image: str | None = None
    resources: Resources = Field(default_factory=Resources)
    streaming: bool = False
    strict_dependencies: bool = False
    public_verified: bool = False
    public_verified_at: datetime | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    _name = field_validator("name")(valid_name)
    _domain = field_validator("full_domain")(valid_domain)

    @field_validator("env_allow")
    @classmethod
    def check_env_allow(cls, values: list[str]) -> list[str]:
        from .security import reserved_variable

        if any(
            not re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_]*", value) or reserved_variable(value)
            for value in values
        ):
            raise ValueError("Environment allowlist contains an invalid or reserved name.")
        return values

    @field_validator("image")
    @classmethod
    def check_image(cls, value: str | None) -> str | None:
        if value and not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9._:/-]*@sha256:[a-f0-9]{64}", value):
            raise ValueError("Container images must be pinned with @sha256:<64 hex digits>.")
        return value

    @field_validator("api_prefix")
    @classmethod
    def check_prefix(cls, value: str) -> str:
        if not re.fullmatch(r"/(?:[a-zA-Z0-9_-]+/?)+", value):
            raise ValueError("API prefix must be a path such as /api.")
        return value.rstrip("/")
