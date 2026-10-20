import plistlib
import xml.etree.ElementTree as ET

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
