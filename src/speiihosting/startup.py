from __future__ import annotations

import getpass
import os
import platform
import plistlib
import subprocess
import sys
from pathlib import Path
from xml.sax.saxutils import escape

from .config import SpeiiError
from .storage import Store, atomic_write

LABEL = "io.speiihosting.daemon"


def location(system: str | None = None) -> Path | None:
    system = system or platform.system()
    if system == "Darwin":
        return Path.home() / "Library/LaunchAgents" / f"{LABEL}.plist"
    if system == "Linux":
        return Path.home() / ".config/systemd/user/speiihos.service"
    return None


def installed() -> bool:
    path = location()
    if path:
        return path.exists()
    if platform.system() == "Windows":
        return (
            subprocess.run(["schtasks", "/Query", "/TN", LABEL], capture_output=True).returncode
            == 0
        )
    return False


def render(store: Store, system: str) -> bytes:
    python = str(Path(sys.executable).absolute())
    if system == "Darwin":
        return plistlib.dumps(
            {
                "Label": LABEL,
                "ProgramArguments": [python, "-m", "speiihosting.daemon"],
                "EnvironmentVariables": {
                    "SPEIIHOSTING_HOME": str(store.home),
                    "PATH": os.environ.get("PATH", ""),
                },
                "RunAtLoad": True,
                "KeepAlive": {"SuccessfulExit": False},
                "ThrottleInterval": 10,
                "StandardOutPath": str(store.home / "logs/startup.log"),
                "StandardErrorPath": str(store.home / "logs/startup.log"),
            }
        )
    if system == "Linux":
        # systemd expands % specifiers even in quoted paths.
        def quote(value: str) -> str:
            return (
                '"'
                + value.replace("\\", "\\\\")
                .replace('"', '\\"')
                .replace("%", "%%")
                .replace("\n", "\\n")
                + '"'
            )

        return (
            "[Unit]\nDescription=SpeiiHosting supervisor\nAfter=network-online.target\n\n"
            "[Service]\nType=simple\n"
            f"Environment={quote('SPEIIHOSTING_HOME=' + str(store.home))}\n"
            f"Environment={quote('PATH=' + os.environ.get('PATH', ''))}\n"
            f"ExecStart={quote(python)} -m speiihosting.daemon\n"
            "Restart=on-failure\nRestartSec=5\nTimeoutStopSec=30\nKillMode=mixed\n\n"
            "[Install]\nWantedBy=default.target\n"
        ).encode()
    # Per-user startup works without an administrator. ONSTART/SYSTEM would use
    # another user's credentials and state, so Windows uses the logon trigger.
    user = getpass.getuser()
    if os.environ.get("USERDOMAIN"):
        user = os.environ["USERDOMAIN"] + "\\" + user
    user = escape(user)
    # Write as UTF-16 LE with BOM: schtasks /XML reads the file with
    # CreateFile + IXmlReader which honours the BOM and therefore works
    # regardless of the system ANSI code-page (the root cause of the
    # "unable to switch the encoding" error on non-English Windows).
    # The XML declaration must match the chosen encoding.
    xml = (
        '<?xml version="1.0" encoding="UTF-16"?>'
        '<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">'
        f"<Triggers><LogonTrigger><Enabled>true</Enabled><UserId>{user}</UserId></LogonTrigger></Triggers>"
        f'<Principals><Principal id="Author"><UserId>{user}</UserId>'
        "<LogonType>InteractiveToken</LogonType><RunLevel>LeastPrivilege</RunLevel></Principal></Principals>"
        "<Settings><MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>"
        "<DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>"
        "<StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>"
        "<ExecutionTimeLimit>PT0S</ExecutionTimeLimit><RestartOnFailure>"
        "<Interval>PT1M</Interval><Count>3</Count></RestartOnFailure></Settings>"
        '<Actions Context="Author"><Exec>'
        f"<Command>{escape(python)}</Command>"
        "<Arguments>-m speiihosting.daemon</Arguments>"
        f"<WorkingDirectory>{escape(str(store.home))}</WorkingDirectory>"
        "</Exec></Actions></Task>"
    )
    return xml.encode("utf-16")


def checked(command: list[str]) -> None:
    result = subprocess.run(command, capture_output=True, text=True, timeout=30)
    if result.returncode:
        raise SpeiiError(
            f"Autostart registration failed: {result.stderr.strip() or result.stdout.strip()}"
        )


def configure(store: Store, enabled: bool) -> None:
    system = platform.system()
    path = location(system)
    if enabled:
        if system == "Darwin":
            loaded = (
                subprocess.run(
                    ["launchctl", "print", f"gui/{os.getuid()}/{LABEL}"], capture_output=True
                ).returncode
                == 0
            )
            atomic_write(path, render(store, system))
            if not loaded:
                checked(["launchctl", "bootstrap", f"gui/{os.getuid()}", str(path)])
        elif system == "Linux":
            atomic_write(path, render(store, system))
            checked(["systemctl", "--user", "daemon-reload"])
            checked(["systemctl", "--user", "enable", "speiihos.service"])
        elif system == "Windows":
            # Scheduled tasks have no environment field; a generated Python runner
            # supplies the chosen data directory without shell interpolation.
            runner = store.home / "startup.py"
            atomic_write(
                runner,
                "import os, runpy\nos.environ['SPEIIHOSTING_HOME'] = "
                + repr(str(store.home))
                + "\nrunpy.run_module('speiihosting.daemon', run_name='__main__')\n",
            )
            # render() returns UTF-16 bytes (with BOM). Decode with the same
            # codec, patch the arguments, then re-encode as UTF-16 so the BOM
            # and declared encoding stay consistent.  schtasks /XML uses
            # IXmlReader which honours the UTF-16 BOM on every Windows locale,
            # avoiding the "unable to switch the encoding" Task Scheduler error.
            xml_text = render(store, system).decode("utf-16")
            xml_text = xml_text.replace(
                "<Arguments>-m speiihosting.daemon</Arguments>",
                "<Arguments>" + escape(subprocess.list2cmdline([str(runner)])) + "</Arguments>",
            )
            task = store.home / "startup.xml"
            atomic_write(task, xml_text.encode("utf-16"))
            checked(["schtasks", "/Create", "/TN", LABEL, "/XML", str(task), "/F"])
        else:
            raise SpeiiError("Autostart is not supported on this OS.")
    elif path and path.exists():
        if system == "Darwin":
            checked(["launchctl", "bootout", f"gui/{os.getuid()}", str(path)])
        elif system == "Linux":
            checked(["systemctl", "--user", "disable", "speiihos.service"])
        path.unlink()
    elif system == "Windows" and installed():
        checked(["schtasks", "/Delete", "/TN", LABEL, "/F"])
