import plistlib
import subprocess
import xml.etree.ElementTree as ET
from types import SimpleNamespace

import pytest

from speiihosting.process import detached_flags
from speiihosting.startup import render


def test_platform_startup_definitions(store):
    mac = plistlib.loads(render(store, "Darwin"))
    assert mac["EnvironmentVariables"]["SPEIIHOSTING_HOME"] == str(store.home)
    assert mac["KeepAlive"] == {"SuccessfulExit": False}
    assert "speiihosting.daemon" in mac["ProgramArguments"]
    linux = render(store, "Linux").decode()
    assert "Restart=on-failure" in linux
    assert "KillMode=mixed" in linux
    windows = ET.fromstring(render(store, "Windows"))
    ns = {"t": "http://schemas.microsoft.com/windows/2004/02/mit/task"}
    assert windows.find("t:Triggers/t:LogonTrigger", ns) is not None
    assert windows.find("t:Settings/t:ExecutionTimeLimit", ns).text == "PT0S"


@pytest.mark.parametrize("system", ["nt", "posix"])
def test_background_launch_is_windowless_on_windows_and_detached_on_posix(monkeypatch, system):
    monkeypatch.setattr("speiihosting.process.os", SimpleNamespace(name=system))
    # These constants are only exported by subprocess on Windows.
    monkeypatch.setattr(subprocess, "CREATE_NO_WINDOW", 0x08000000, raising=False)
    monkeypatch.setattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200, raising=False)
    flags = detached_flags()
    if system == "nt":
        assert flags["creationflags"] & 0x08000000
        assert flags["creationflags"] & 0x00000200
        assert not flags["creationflags"] & (0x00000008 | 0x00000010)
    else:
        assert flags == {"start_new_session": True}


def test_windows_cmd_string_preserves_quoted_command():
    from speiihosting.process import windows_cmd_string

    cmd = ["cmd.exe", "/d", "/s", "/c", '"C:\\Program Files\\Python\\python.exe" build.py']
    formatted = windows_cmd_string(cmd)
    assert formatted == 'cmd.exe /d /s /c ""C:\\Program Files\\Python\\python.exe" build.py"'


def test_run_logged_formats_windows_cmd_command(monkeypatch, tmp_path):
    import speiihosting.process as proc

    monkeypatch.setattr(proc.os, "name", "nt")
    monkeypatch.setattr(proc.subprocess, "CREATE_NO_WINDOW", 0x08000000, raising=False)
    captured = {}

    class DummyPopen:
        def __init__(self, command, **kwargs):
            captured["command"] = command
            self.stdout = None
            self.pid = 1234

        def wait(self, timeout=None):
            return 0

    monkeypatch.setattr(proc.subprocess, "Popen", DummyPopen)
    monkeypatch.setattr(proc, "pump", lambda *a: None)
    proc.run_logged(
        ["cmd.exe", "/d", "/s", "/c", '"python.exe" script.py'],
        tmp_path,
        tmp_path / "test.log",
    )
    assert captured["command"] == 'cmd.exe /d /s /c ""python.exe" script.py"'
