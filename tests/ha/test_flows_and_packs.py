from pathlib import Path

import pytest
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import ServiceValidationError

from custom_components.homekeeper.const import DOMAIN
from custom_components.homekeeper.runtime import get_runtime, parse_conditions

PACKS = Path(__file__).resolve().parents[2] / "packs"


async def test_user_flow_single_instance(hass):
    r = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert r["type"] is FlowResultType.FORM
    r = await hass.config_entries.flow.async_configure(r["flow_id"], {})
    assert r["type"] is FlowResultType.CREATE_ENTRY
    r2 = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert r2["type"] is FlowResultType.ABORT


async def _sub(hass, entry, stype, steps):
    r = await hass.config_entries.subentries.async_init(
        (entry.entry_id, stype), context={"source": "user"}
    )
    for step in steps:
        assert r["type"] is FlowResultType.FORM, r
        r = await hass.config_entries.subentries.async_configure(r["flow_id"], step)
    return r


async def test_add_person_module_duty_via_ui(hass, entry_factory, freezer):
    freezer.move_to("2026-11-14 09:00:00")
    entry = entry_factory()
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    r = await _sub(hass, entry, "person", [
        {"id": "dad", "name": "Dad", "role": "owner", "language": "ar",
         "notify": "notify.mobile_dad", "quiet_start": "22:00", "quiet_end": "07:00"}])
    assert r["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()

    r = await _sub(hass, entry, "module", [
        {"id": "lawn", "title_en": "Lawn", "title_ar": "العشب", "owners": ["dad"]}])
    assert r["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()

    r = await _sub(hass, entry, "duty", [
        {"id": "mow", "module": "lawn", "title_en": "Mow", "title_ar": "قص العشب",
         "owners": [], "observers": [], "schedule_type": "after_completion"},
        {"every": "7d"},
        {"remind": "0d", "escalate_after": "2d", "how_to": "EGO mower", "season": "3,4,5",
         "done_by": ["button", "nfc"], "enabled": True},
    ])
    assert r["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()

    rt = get_runtime(hass, entry.entry_id)
    assert rt.engine.people["dad"].quiet_hours == ["22:00", "07:00"]
    assert rt.engine.duties["mow"].season == [3, 4, 5]
    assert rt.engine.duties["mow"].escalate == [{"after": "2d", "notify": ["admin"]}]
    # new todo list + sensors appeared (entry reloaded because the entity set changed)
    assert hass.states.get("todo.homekeeper_lawn") is not None
    assert hass.states.get("sensor.homekeeper_mow_next_due") is not None


async def test_duplicate_and_bad_ids_rejected(hass, entry_factory):
    entry = entry_factory()
    assert await hass.config_entries.async_setup(entry.entry_id)
    r = await hass.config_entries.subentries.async_init(
        (entry.entry_id, "person"), context={"source": "user"})
    r = await hass.config_entries.subentries.async_configure(
        r["flow_id"], {"id": "a", "name": "X", "role": "owner", "language": "en"})
    assert r["errors"] == {"id": "id_exists"}
    r = await hass.config_entries.subentries.async_configure(
        r["flow_id"], {"id": "Bad Id", "name": "X", "role": "owner", "language": "en"})
    assert r["errors"] == {"id": "bad_id"}
    r = await hass.config_entries.subentries.async_configure(
        r["flow_id"], {"id": "ok", "name": "X", "role": "owner", "language": "en",
                       "quiet_start": "22:00"})
    assert r["errors"] == {"quiet_start": "quiet_both"}


async def test_bad_schedule_is_rejected(hass, entry_factory):
    entry = entry_factory()
    assert await hass.config_entries.async_setup(entry.entry_id)
    r = await hass.config_entries.subentries.async_init(
        (entry.entry_id, "duty"), context={"source": "user"})
    r = await hass.config_entries.subentries.async_configure(
        r["flow_id"], {"id": "x", "module": "home", "title_en": "X", "owners": [],
                       "observers": [], "schedule_type": "day_of_month"})
    r = await hass.config_entries.subentries.async_configure(r["flow_id"], {"days": "40"})
    assert r["errors"] == {"base": "bad_schedule"}


async def test_reconfigure_duty_keeps_id_and_updates_schedule(hass, entry_factory, freezer):
    freezer.move_to("2026-11-14 09:00:00")
    entry = entry_factory()
    assert await hass.config_entries.async_setup(entry.entry_id)
    sub = next(s for s in entry.subentries.values() if s.data["id"] == "filters")
    r = await hass.config_entries.subentries.async_init(
        (entry.entry_id, "duty"), context={"source": "reconfigure", "subentry_id": sub.subentry_id})
    assert r["type"] is FlowResultType.FORM
    for step in (
        {"module": "home", "title_en": "Replace filters", "title_ar": "", "owners": ["a"],
         "observers": [], "schedule_type": "after_completion"},
        {"every": "2m", "first_due": "2026-12-20"},
        {"remind": "-3d,0d", "escalate_after": "", "how_to": "", "season": "",
         "done_by": ["button"], "enabled": True},
    ):
        r = await hass.config_entries.subentries.async_configure(r["flow_id"], step)
    assert r["type"] is FlowResultType.ABORT and r["reason"] == "reconfigure_successful"
    await hass.async_block_till_done()
    rt = get_runtime(hass, entry.entry_id)
    assert rt.engine.duties["filters"].owners == ["a"]
    assert rt.engine.occurrences["filters"].due.isoformat() == "2026-12-20"


async def test_options_conditions_feed_engine(hass, entry_factory, freezer):
    freezer.move_to("2027-01-20 09:00:00")
    entry = entry_factory()
    assert await hass.config_entries.async_setup(entry.entry_id)
    r = await hass.config_entries.options.async_init(entry.entry_id)
    r = await hass.config_entries.options.async_configure(
        r["flow_id"], {"conditions": "soil_temp_5day_avg_f=sensor.soil_avg"})
    assert r["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    hass.states.async_set("sensor.soil_avg", "53.2")
    rt = get_runtime(hass, entry.entry_id)
    assert rt.read_conditions() == {"soil_temp_5day_avg_f": 53.2}
    hass.states.async_set("sensor.soil_avg", "unavailable")
    assert rt.read_conditions() == {"soil_temp_5day_avg_f": None}


def test_parse_conditions():
    assert parse_conditions("a=sensor.x, b = sensor.y\nc=sensor.z") == {
        "a": "sensor.x", "b": "sensor.y", "c": "sensor.z"}
    assert parse_conditions("junk") == {}


async def test_import_pack_service_dry_run_apply_and_idempotent(hass, entry_factory, freezer):
    freezer.move_to("2026-11-14 09:00:00")
    entry = entry_factory()
    assert await hass.config_entries.async_setup(entry.entry_id)
    text = (PACKS / "lawn-fescue.yaml").read_text()

    dry = await hass.services.async_call(
        DOMAIN, "import_pack", {"pack": text, "dry_run": True}, blocking=True, return_response=True)
    assert dry["applied"] is False and "duty:mow" in dry["created"]
    assert "lawn" not in get_runtime(hass, entry.entry_id).engine.modules

    out = await hass.services.async_call(
        DOMAIN, "import_pack", {"pack": text}, blocking=True, return_response=True)
    assert out["applied"] is True
    await hass.async_block_till_done()
    rt = get_runtime(hass, entry.entry_id)
    assert {"preemergent", "mow", "soil-test"} <= set(rt.engine.duties)
    assert hass.states.get("todo.homekeeper_lawn") is not None

    again = await hass.services.async_call(
        DOMAIN, "import_pack", {"pack": text}, blocking=True, return_response=True)
    assert again["created"] == [] and again["applied"] is True


async def test_import_pack_errors(hass, entry_factory):
    entry = entry_factory()
    assert await hass.config_entries.async_setup(entry.entry_id)
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(DOMAIN, "import_pack", {}, blocking=True, return_response=True)
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN, "import_pack", {"pack": "duties: []"}, blocking=True, return_response=True)
    bad = "module: m\nduties:\n  - {id: x, title: {en: x}, schedule: {type: nope}}\n"
    out = await hass.services.async_call(
        DOMAIN, "import_pack", {"pack": bad}, blocking=True, return_response=True)
    assert out["applied"] is False and out["errors"]


async def test_export_pack_service(hass, entry_factory):
    entry = entry_factory()
    assert await hass.config_entries.async_setup(entry.entry_id)
    out = await hass.services.async_call(
        DOMAIN, "export_pack", {"module": "home"}, blocking=True, return_response=True)
    assert out["module"] == "home" and out["duties"][0]["id"] == "filters"
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN, "export_pack", {"module": "ghost"}, blocking=True, return_response=True)


async def test_quiet_hours_hold_non_escalation(hass, entry_factory, notify_calls, freezer):
    await hass.config.async_set_time_zone("UTC")
    freezer.move_to("2026-12-01 23:30:00")
    entry = entry_factory()
    # give Alex quiet hours 22:00-07:00
    sub = next(s for s in entry.subentries.values() if s.data["id"] == "a")
    hass.config_entries.async_update_subentry(
        entry, sub, data={**sub.data, "quiet_hours": ["22:00", "07:00"]})
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    rt = get_runtime(hass, entry.entry_id)
    assert "mobile_a" not in {c.service for c in notify_calls}
    assert any(p == "a" for p, _ in rt.queue)
    freezer.move_to("2026-12-02 07:30:00")
    await rt.async_flush_queue(__import__("homeassistant.util.dt", fromlist=["now"]).now())
    assert "mobile_a" in {c.service for c in notify_calls}
