from datetime import date
from pathlib import Path

import pytest

from engine import Engine, Person
from engine.packs import export_pack, import_pack, load_pack_text

PACKS = sorted((Path(__file__).resolve().parents[1] / "packs").glob("*.yaml"))
TODAY = date(2026, 11, 14)


def fresh():
    e = Engine()
    e.add_person(Person("adm", "Admin", role="admin"))
    return e


@pytest.mark.parametrize("path", PACKS, ids=lambda p: p.name)
def test_every_shipped_pack_imports_cleanly(path):
    e = fresh()
    report = import_pack(e, load_pack_text(path.read_text()), TODAY)
    assert report.ok, report.errors
    assert any(c.startswith("duty:") or c.startswith("biller:") for c in report.created)


@pytest.mark.parametrize("path", PACKS, ids=lambda p: p.name)
def test_reimport_is_idempotent(path):
    e = fresh()
    data = load_pack_text(path.read_text())
    import_pack(e, data, TODAY)
    before = e.to_dict()
    report = import_pack(e, data, TODAY)
    assert not report.created and not report.updated
    assert e.to_dict() == before


def test_import_does_not_clobber_edits_unless_overwrite():
    e = fresh()
    data = load_pack_text(next(p for p in PACKS if p.name == "home.yaml").read_text())
    import_pack(e, data, TODAY)
    e.duties["hvac-filters"].owners = ["adm"]
    import_pack(e, data, TODAY)
    assert e.duties["hvac-filters"].owners == ["adm"]
    report = import_pack(e, data, TODAY, overwrite=True)
    assert "duty:hvac-filters" in report.updated
    assert e.duties["hvac-filters"].owners == []


def test_dry_run_and_bad_pack_change_nothing():
    e = fresh()
    data = load_pack_text(PACKS[0].read_text())
    report = import_pack(e, data, TODAY, dry_run=True)
    assert report.created and not e.duties and not e.modules

    bad = {"module": "m", "duties": [
        {"id": "ok", "title": {"en": "ok"}, "schedule": {"type": "interval", "every": "1m"}},
        {"id": "bad", "title": {"en": "bad"}, "schedule": {"type": "nope"}},
    ]}
    report = import_pack(e, bad, TODAY)
    assert not report.ok and "duty:bad" in report.errors[0]
    assert not e.modules and not e.duties


def test_export_round_trip():
    e = fresh()
    path = next(p for p in PACKS if p.name == "rental.yaml")
    import_pack(e, load_pack_text(path.read_text()), TODAY)
    exported = export_pack(e, "rental")
    e2 = fresh()
    assert import_pack(e2, exported, TODAY).ok
    assert set(e2.duties) == set(e.duties)


def test_pack_without_module_is_rejected():
    with pytest.raises(ValueError):
        load_pack_text("duties: []")
