"""Explicit environment boundaries and independently stored hosting credentials."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Protocol

from .config import SpeiiError

BASE_VARIABLES = frozenset(
    {
        "PATH",
        "HOME",
        "USER",
        "LOGNAME",
        "SHELL",
        "LANG",
        "LC_ALL",
        "LC_CTYPE",
        "TMP",
        "TEMP",
        "TMPDIR",
        "SYSTEMROOT",
        "SYSTEMDRIVE",
        "WINDIR",
        "COMSPEC",
        "PATHEXT",
        "USERPROFILE",
        "HOMEDRIVE",
        "HOMEPATH",
        "APPDATA",
        "LOCALAPPDATA",
        "PROGRAMDATA",
        "PROGRAMFILES",
        "PROGRAMFILES(X86)",
        "NUMBER_OF_PROCESSORS",
        "PROCESSOR_ARCHITECTURE",
    }
)


def reserved_variable(name: str) -> bool:
    upper = name.upper()
    return upper.startswith("SPEIIHOSTING_") or upper in {
        "CLOUDFLARE_API_TOKEN",
        "TUNNEL_TOKEN",
        "TUNNEL_TOKEN_FILE",
        "TUNNEL_ORIGIN_CERT",
        "TUNNEL_CRED_FILE",
    }


def safe_environment(allow: list[str] = ()) -> dict[str, str]:
    allowed = BASE_VARIABLES | {name.upper() for name in allow if not reserved_variable(name)}
    return {
        key: value
        for key, value in os.environ.items()
        if key.upper() in allowed and not reserved_variable(key)
    }


def app_values(*paths: Path) -> dict[str, str]:
    """Load app variables in precedence order without expansion or host credentials."""
    from dotenv import dotenv_values

    values = {}
    for path in paths:
        values.update(
            {
                key: value
                for key, value in dotenv_values(
                    path, encoding="utf-8-sig", interpolate=False
                ).items()
                if value is not None and not reserved_variable(key)
            }
        )
    return values


class Credentials(Protocol):
    def read(self) -> dict[str, str]: ...
    def write(self, values: dict[str, str]) -> None: ...


class FileCredentials:
    def __init__(self, home: Path):
        self.path = home / "credentials.json"

    def read(self) -> dict[str, str]:
        from .storage import read_json

        values = read_json(self.path, {})
        if not isinstance(values, dict) or any(
            not isinstance(k, str) or not isinstance(v, str) for k, v in values.items()
        ):
            raise SpeiiError("Invalid credentials.json; restore the credential store.")
        return values

    def write(self, values: dict[str, str]) -> None:
        from .storage import write_json

        write_json(self.path, values)


class KeyringCredentials:
    def __init__(self, home: Path):
        import hashlib

        self.account = hashlib.sha256(str(home).encode()).hexdigest()
        try:
            import keyring
        except ImportError:
            raise SpeiiError("Install speiihosting[secrets] to use the OS keyring.") from None
        self.keyring = keyring
        backend = keyring.get_keyring()
        trusted = (
            "keyring.backends.macOS",
            "keyring.backends.Windows",
            "keyring.backends.SecretService",
            "keyring.backends.kwallet",
            "keyring.backends.libsecret",
        )
        candidates = getattr(backend, "backends", [backend])
        secure = [
            item
            for item in candidates
            if type(item).__module__.startswith(trusted) and item.priority > 0
        ]
        if not secure:
            raise SpeiiError(
                "A secure OS keyring is unavailable. Use the private file credential store."
            )
        keyring.set_keyring(secure[0])

    def read(self) -> dict[str, str]:
        import json

        try:
            data = self.keyring.get_password("speiihosting", self.account)
            return json.loads(data) if data else {}
        except Exception as error:
            raise SpeiiError("Cannot unlock the OS keyring.") from error

    def write(self, values: dict[str, str]) -> None:
        import json

        try:
            self.keyring.set_password("speiihosting", self.account, json.dumps(values))
        except Exception as error:
            raise SpeiiError("Cannot save hosting credentials to the OS keyring.") from error


def credentials(home: Path, provider: str) -> Credentials:
    return KeyringCredentials(home) if provider == "keyring" else FileCredentials(home)
