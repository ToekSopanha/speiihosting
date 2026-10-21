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
