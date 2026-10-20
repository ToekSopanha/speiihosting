import pytest

from speiihosting.config import Service, SpeiiError
from speiihosting.projects import Release
from speiihosting.storage import write_json
from speiihosting.transactions import Phase, Transaction, check_budget, recover


def setup_release(store, tmp_path):
    service = Service(name="worker", type="bot", source=tmp_path, status="stopped")
    store.save_services({service.name: service})
    release = Release(store.site(service.name))
    for path, value in (
        (release.live, "one"),
        (release.previous, "zero"),
        (release.candidate, "two"),
    ):
        path.mkdir()
        (path / "version.txt").write_text(value)
    metadata = service.model_copy(update={"framework": "previous-runtime"}).model_dump(mode="json")
    write_json(release.site / "previous.json", metadata)
    new = service.model_copy(update={"generation": 3})
    transaction = Transaction(store, new, store.services())
    transaction.begin()
    return service, release, transaction


@pytest.mark.parametrize(
    "point",
    ["prepared", "before_rename", "previous_retired", "live_retired", "promoted", "committed"],
)
def test_recovery_at_every_promotion_boundary(store, tmp_path, point):
    old, release, transaction = setup_release(store, tmp_path)
    if point != "prepared":
        transaction.phase(Phase.PROMOTING)
    if point in {"previous_retired", "live_retired", "promoted", "committed"}:
        release.previous.rename(release.obsolete)
    if point in {"live_retired", "promoted", "committed"}:
        release.live.rename(release.previous)
    if point in {"promoted", "committed"}:
        release.candidate.rename(release.live)
    if point == "committed":
        transaction.phase(Phase.COMMITTED)
    assert recover(store) == ["worker"]
    assert (release.live / "version.txt").read_text() == ("two" if point == "committed" else "one")
    assert (release.previous / "version.txt").read_text() == (
        "one" if point == "committed" else "zero"
    )
    assert not release.obsolete.exists() and not release.candidate.exists()
    assert not transaction.path.exists()
    assert recover(store) == []


def test_failed_recovery_can_resume_without_losing_releases(store, tmp_path, monkeypatch):
    old, release, transaction = setup_release(store, tmp_path)
    transaction.phase(Phase.PROMOTING)
    release.promote()
    original = type(release.previous).rename

    def fail(path, target):
        if path == release.previous and target == release.live:
            raise PermissionError("simulated file lock")
        return original(path, target)

    with monkeypatch.context() as scoped:
        scoped.setattr(type(release.previous), "rename", fail)
        with pytest.raises(PermissionError):
            recover(store)
    assert transaction.path.exists()
    assert (release.previous / "version.txt").read_text() == "one"
    assert (release.candidate / "version.txt").read_text() == "two"
    recover(store)
    assert (release.live / "version.txt").read_text() == "one"
    assert (release.previous / "version.txt").read_text() == "zero"


def test_invalid_journal_changes_nothing(store, tmp_path):
    old, release, transaction = setup_release(store, tmp_path)
    write_json(transaction.path, {"schema_version": 99})
    with pytest.raises(SpeiiError, match="Invalid deployment journal"):
        recover(store)
    assert (release.live / "version.txt").read_text() == "one"
    assert transaction.path.exists()


def test_persistent_data_survives_promotion_and_recovery(store, tmp_path):
    old, release, transaction = setup_release(store, tmp_path)
    data = release.site / "data"
    data.mkdir()
    (data / "database.sqlite").write_text("persistent")
    transaction.phase(Phase.PROMOTING)
    release.promote()
    recover(store)
    assert (data / "database.sqlite").read_text() == "persistent"


def test_release_budget_failure_does_not_promote(store, tmp_path, monkeypatch):
    old, release, transaction = setup_release(store, tmp_path)
    monkeypatch.setattr("speiihosting.transactions.tree_bytes", lambda _: 10_000_000_000)
    with pytest.raises(SpeiiError, match="budget exceeded"):
        check_budget(store, release.site)
    assert (release.live / "version.txt").read_text() == "one"
