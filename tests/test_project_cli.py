import json

import pytest
from typer.testing import CliRunner

from speiihosting.cli import app
from speiihosting.config import Service, SpeiiError
from speiihosting.nginx import render_site
from speiihosting.project_config import load, options
from speiihosting.storage import Store, write_json


def test_project_manifest_and_cli_overrides(tmp_path):
    (tmp_path / "speiihosting.toml").write_text(
        'schema_version=1\ntype="backend"\nname="my-api"\nport=8000\nenv_allow=["APP_REGION"]\n[health]\npath="/health"\nexpected_status=204\n'
    )
    values = options(tmp_path, "backend", {"port": 9000})
    assert values["port"] == 9000
    assert values["health"].path == "/health"
    assert values["health"].expected_status == 204
    assert values["env_allow"] == ["APP_REGION"]
    assert values["frontend"] is None


def test_manifest_rejects_unknown_keys_and_type_mismatch(tmp_path):
    path = tmp_path / "speiihosting.toml"
    path.write_text('type="backend"\nport=8000\nsecrettypo=true\n')
    with pytest.raises(SpeiiError):
        load(tmp_path, "backend")
    path.write_text('type="bot"\n')
    with pytest.raises(SpeiiError, match="matching host command"):
        load(tmp_path, "backend")


def test_preview_creates_no_hosting_directory(tmp_path, monkeypatch):
    source = tmp_path / "source"
    source.mkdir()
    (source / "bot.py").write_text("print('preview')")
    home = tmp_path / "does-not-exist"
    monkeypatch.setenv("SPEIIHOSTING_HOME", str(home))
    monkeypatch.chdir(source)
    result = CliRunner().invoke(app, ["host-bot", "--dry-run", "--json"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["dry_run"] and data["type"] == "bot"
    assert data["routes"] == []
    assert "bot.py" in data["command"]
    assert not home.exists()
    assert not (source / "speiihosting.toml").exists()


def test_configured_host_command_preview_and_project_generation(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "main.py").write_text("print('app')")
    runner = CliRunner()
    result = runner.invoke(app, ["project", "init", "--type", "backend"])
    assert result.exit_code == 0, result.output
    assert load(tmp_path, "backend").type == "backend"
    assert runner.invoke(app, ["project", "init", "--type", "backend"]).exit_code == 1
    result = runner.invoke(app, ["host-back", "--port", "9001", "--dry-run", "--json"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["requested_port"] == 9001
    assert data["health"]["expected_status"] == 200


def test_json_inspection_does_not_expose_credentials(store, tmp_path):
    service = Service(name="private-api", type="backend", source=tmp_path, port=8000)
    store.save_services({service.name: service})
    settings = store.settings()
    settings.cloudflare_api_token = "private-host-token"
    store.save_settings(settings)
    result = CliRunner().invoke(app, ["inspect", "private-api", "--json"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["routes"] == []
    assert "private-host-token" not in result.output
    assert data["isolation_boundary"] == "trusted code under the current OS user"
    result = CliRunner().invoke(app, ["list", "--json"])
    assert result.exit_code == 0
    assert json.loads(result.output)[0]["name"] == "private-api"


@pytest.mark.parametrize(
    ("flags", "strip_prefix"),
    [([], True), (["--strip-prefix"], True), (["--preserve-prefix"], False)],
)
def test_link_prefix_mode_is_applied_persisted_and_inspectable(
    store, tmp_path, monkeypatch, flags, strip_prefix
):
    front = Service(
        name="web",
        type="frontend",
        source=tmp_path,
        full_domain="web.example.com",
        api_strip_prefix=not strip_prefix,
    )
    back = Service(name="api", type="backend", source=tmp_path, port=3001)
    store.save_services({front.name: front, back.name: back})
    rendered = []
    monkeypatch.setattr(
        "speiihosting.nginx.Nginx.apply",
        lambda _, services: rendered.append(render_site(services[front.name], services, store)),
    )
    runner = CliRunner()
    result = runner.invoke(app, ["link", "web", "api", "--prefix", "/api", *flags])
    assert result.exit_code == 0, result.output
    assert ("prefix stripped" if strip_prefix else "prefix preserved") in result.output
    saved = Store(store.home).resolve(front.name)
    assert saved.backend == back.name
    assert saved.api_strip_prefix is strip_prefix
    target = "http://speii_3001/" if strip_prefix else "http://speii_3001"
    assert f"proxy_pass {target};" in rendered[0]
    for name in (front.name, back.name):
        result = runner.invoke(app, ["inspect", name, "--json"])
        assert result.exit_code == 0, result.output
        assert json.loads(result.output)["routes"][0]["strip_prefix"] is strip_prefix


def test_existing_services_keep_stripping_api_prefix(store, tmp_path):
    service = Service(name="web", type="frontend", source=tmp_path, backend="api")
    legacy = service.model_dump(mode="json")
    legacy.pop("api_strip_prefix")
    write_json(store.home / "services.json", {service.name: legacy})
    assert Store(store.home).resolve(service.name).api_strip_prefix is True
