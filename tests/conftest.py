import socket

import pytest

from speiihosting.config import Settings
from speiihosting.process import stop_daemon
from speiihosting.storage import Store


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
