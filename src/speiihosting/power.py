import platform
import subprocess

from .config import SpeiiError
from .storage import Store, read_json, write_json


def configure(store: Store, enabled: bool) -> None:
    system = platform.system()
    if system == "Darwin":
        # The supervisor owns caffeinate, so disabling it stops only our inhibitor.
        return
    if system == "Linux":
        # A reversible drop-in, never replace an existing logind.conf.
        destination = "/etc/systemd/logind.conf.d/90-speiihosting.conf"
        if enabled:
            local = store.home / "lid.conf"
            local.write_text(
                "[Login]\nHandleLidSwitch=ignore\nHandleLidSwitchExternalPower=ignore\n"
            )
            commands = [["sudo", "install", "-D", "-m", "644", str(local), destination]]
        else:
            commands = [["sudo", "rm", "-f", destination]]
        for command in commands:
            if subprocess.run(command).returncode:
                raise SpeiiError(
                    "Could not update the lid policy. Run with sudo credentials available."
                )
        return
    if system == "Windows":
        backup = store.home / "power-backup.json"
        if enabled:
            # Save the current AC lid action, rather than guessing on disable.
            result = subprocess.run(
                ["powercfg", "/query", "SCHEME_CURRENT", "SUB_BUTTONS", "LIDACTION"],
                capture_output=True,
                text=True,
            )
            import re

            indexes = re.findall(r"0x([0-9a-fA-F]{8})", result.stdout)
            if result.returncode or len(indexes) < 2:
                raise SpeiiError("Cannot read the current Windows AC lid policy.")
            if not backup.exists():
                write_json(backup, {"ac_lid": int(indexes[-2], 16)})
            action = 0
        else:
            data = read_json(backup, None)
            if data is None:
                raise SpeiiError("No saved lid policy to restore.")
            action = data["ac_lid"]
        for command in (
            [
                "powercfg",
                "/setacvalueindex",
                "SCHEME_CURRENT",
                "SUB_BUTTONS",
                "LIDACTION",
                str(action),
            ],
            ["powercfg", "/setactive", "SCHEME_CURRENT"],
        ):
            if subprocess.run(command, capture_output=True).returncode:
                raise SpeiiError(
                    "Windows rejected the power setting; use an administrator terminal."
                )
        if not enabled:
            backup.unlink(missing_ok=True)
        return
    raise SpeiiError("Sleep prevention is not supported on this OS.")
