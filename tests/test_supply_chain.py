import hashlib
import re
from pathlib import Path

import httpx
import pytest

from speiihosting.config import Service, SpeiiError
from speiihosting.doctor import pinned_binaries, verified_download
from speiihosting.projects import prepare


def test_download_requires_a_reviewed_matching_checksum():
    data = b"verified binary"
    calls = []
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: calls.append(request) or httpx.Response(200, content=data)
        )
    )
    url = "https://nginx.org/download/nginx-test.zip"
    with pytest.raises(SpeiiError, match="No reviewed"):
        verified_download(client, {"url": url})
    assert not calls
    with pytest.raises(SpeiiError, match="did not match"):
        verified_download(client, {"url": url, "sha256": "0" * 64})
    assert (
        verified_download(client, {"url": url, "sha256": hashlib.sha256(data).hexdigest()}) == data
    )


def test_download_manifest_and_ci_actions_are_pinned():
    manifest = pinned_binaries()
    assert manifest["schema_version"] == 1
    for asset in [manifest["nginx_windows"], *manifest["cloudflared"]["assets"].values()]:
        assert re.fullmatch("[a-f0-9]{64}", asset["sha256"])
        assert "/latest/" not in asset["url"]
    workflow = (Path(__file__).parents[1] / ".github/workflows/ci.yml").read_text()
    actions = re.findall(r"uses: ([^\s]+)", workflow)
    assert actions and all(
        re.fullmatch(r"[\w-]+/[\w-]+@[a-f0-9]{40}", action) for action in actions
    )
    assert "contents: read" in workflow
    assert "pip-audit" in workflow and "--locked" in workflow


def test_strict_node_install_requires_lockfile(tmp_path):
    (tmp_path / "package.json").write_text('{"name":"test","scripts":{"start":"node bot.js"}}')
    service = Service(name="test", type="bot", source=tmp_path, strict_dependencies=True)
    with pytest.raises(SpeiiError, match="package-lock"):
        prepare(service, tmp_path, tmp_path / "site", tmp_path / "build.log")


def test_strict_python_install_passes_hash_and_binary_checks(tmp_path, monkeypatch):
    source = tmp_path / "candidate"
    source.mkdir()
    (source / "bot.py").write_text("print('hello')")
    (source / "requirements.lock").write_text("example==1.0 --hash=sha256:" + "a" * 64 + "\n")
    commands = []

    def build(command, cwd, log, env=None):
        commands.append(command)
        if command[1:3] == ["-m", "venv"]:
            Path(command[-1]).mkdir(parents=True)

    monkeypatch.setattr("speiihosting.projects.run_build", build)
    service = Service(name="test", type="bot", source=source, strict_dependencies=True)
    prepare(service, source, tmp_path / "site", tmp_path / "build.log")
    install = next(c for c in commands if "install" in c)
    assert "--require-hashes" in install
    assert "--only-binary=:all:" in install
    assert str(source / "requirements.lock") in install
