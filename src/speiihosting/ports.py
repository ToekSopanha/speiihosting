import socket

from .config import SpeiiError


def available(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


def listening(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.3)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def allocate(requested: int, reserved: set[int], auto: bool = False) -> int:
    for port in range(requested, min(requested + (100 if auto else 1), 65536)):
        if port not in reserved and available(port):
            return port
    raise SpeiiError(f"Port {requested} is unavailable. Choose --port or use --auto-port.")
