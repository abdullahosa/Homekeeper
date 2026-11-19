from pathlib import Path

import pytest
import voluptuous as vol
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import ServiceValidationError
from homeassistant.util import dt as dt_util

from custom_components.homekeeper.const import DOMAIN
from custom_components.homekeeper.runtime import get_runtime, parse_conditions

PACKS = Path(__file__).resolve().parents[2] / "custom_components" / "homekeeper" / "packs"


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
        {"name": "Dad", "role": "owner", "language": "ar",
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


async def test_person_id_is_made_from_the_name(hass, entry_factory):
    entry = entry_factory()
    assert await hass.config_entries.async_setup(entry.entry_id)

    async def add(name, **extra):
        r = await hass.config_entries.subentries.async_init(
            (entry.entry_id, "person"), context={"source": "user"})
        assert "id" not in {str(k) for k in r["data_schema"].schema}
        return await hass.config_entries.subentries.async_configure(
            r["flow_id"], {"name": name, "role": "owner", "language": "en", **extra})

    assert (await add("Sam"))["type"] is FlowResultType.CREATE_ENTRY
    assert (await add("Sam"))["type"] is FlowResultType.CREATE_ENTRY  # same name again
    assert (await add("أحمد"))["type"] is FlowResultType.CREATE_ENTRY
    assert (await add("!!!"))["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    ids = {s.data["id"] for s in entry.subentries.values() if s.subentry_type == "person"}
    assert {"sam", "sam_2", "hmd", "person"} <= ids  # Arabic names are transliterated


async def test_quiet_hours_need_both_times(hass, entry_factory):
    entry = entry_factory()
    assert await hass.config_entries.async_setup(entry.entry_id)
    r = await hass.config_entries.subentries.async_init(
        (entry.entry_id, "person"), context={"source": "user"})
    r = await hass.config_entries.subentries.async_configure(
        r["flow_id"], {"name": "X", "role": "owner", "language": "en", "quiet_start": "22:00"})
    assert r["errors"] == {"quiet_start": "quiet_both"}


async def test_owner_pickers_show_names_but_store_ids(hass, entry_factory):
    entry = entry_factory()
    assert await hass.config_entries.async_setup(entry.entry_id)
    r = await hass.config_entries.subentries.async_init(
        (entry.entry_id, "module"), context={"source": "user"})
    owners = next(v for k, v in r["data_schema"].schema.items() if str(k) == "owners")
    opts = owners.config["options"]
    assert all(set(o) == {"value", "label"} for o in opts) and {o["value"] for o in opts} >= {"a", "b"}


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


async def test_import_bundled_pack_by_name(hass, entry_factory, freezer):
    freezer.move_to("2026-11-14 09:00:00")
    entry = entry_factory()
    assert await hass.config_entries.async_setup(entry.entry_id)
    out = await hass.services.async_call(
        DOMAIN, "import_pack", {"name": "lawn-fescue"}, blocking=True, return_response=True)
    assert out["applied"] is True and "duty:mow" in out["created"]
    with pytest.raises(vol.Invalid):
        await hass.services.async_call(DOMAIN, "import_pack", {"name": "nope"}, blocking=True)


def test_services_yaml_lists_every_bundled_pack():
    import yaml

    from custom_components.homekeeper.services import BUNDLED_PACKS

    spec = yaml.safe_load((PACKS.parent / "services.yaml").read_text())
    assert spec["import_pack"]["fields"]["name"]["selector"]["select"]["options"] == BUNDLED_PACKS
    assert BUNDLED_PACKS == sorted(p.stem for p in PACKS.glob("*.yaml"))


async def test_bad_reminder_shows_the_field_and_keeps_what_was_typed(hass, entry_factory):
    entry = entry_factory()
    assert await hass.config_entries.async_setup(entry.entry_id)
    r = await hass.config_entries.subentries.async_init(
        (entry.entry_id, "duty"), context={"source": "user"})
    r = await hass.config_entries.subentries.async_configure(
        r["flow_id"], {"id": "x", "module": "home", "title_en": "X", "owners": [],
                       "observers": [], "schedule_type": "after_completion"})
    r = await hass.config_entries.subentries.async_configure(r["flow_id"], {"every": "7d"})
    assert r["step_id"] == "details"
    r = await hass.config_entries.subentries.async_configure(
        r["flow_id"], {"remind": "-3, 0d", "escalate_after": "2 days", "season": "3,13",
                       "how_to": "Keep me", "done_by": ["button"], "enabled": True})
    assert r["errors"] == {"remind": "bad_duration", "escalate_after": "bad_duration",
                           "season": "bad_months"}
    defaults = {str(k): k.default() for k in r["data_schema"].schema}
    assert defaults["remind"] == "-3, 0d" and defaults["how_to"] == "Keep me"
    r = await hass.config_entries.subentries.async_configure(
        r["flow_id"], {"remind": "-3d,0d", "escalate_after": "2d", "season": "3,4",
                       "how_to": "Keep me", "done_by": ["button"], "enabled": True})
    assert r["type"] is FlowResultType.CREATE_ENTRY


async def test_biller_creates_its_module_when_none_exists(hass, entry_factory):
    entry = entry_factory()
    for sub in [s for s in entry.subentries.values() if s.subentry_type == "module"]:
        hass.config_entries.async_remove_subentry(entry, sub.subentry_id)
    assert await hass.config_entries.async_setup(entry.entry_id)
    r = await hass.config_entries.subentries.async_init(
        (entry.entry_id, "biller"), context={"source": "user"})
    assert r["type"] is FlowResultType.FORM and r["step_id"] == "first_module"
    r = await hass.config_entries.subentries.async_configure(
        r["flow_id"], {"module_name": "Bills", "owners": ["a"]})
    assert r["type"] is FlowResultType.FORM and r["step_id"] == "user"
    modules = {s.data["id"]: s.data for s in entry.subentries.values() if s.subentry_type == "module"}
    assert modules["bills"]["owners"] == ["a"] and modules["bills"]["title"] == {"en": "Bills"}
    r = await hass.config_entries.subentries.async_configure(
        r["flow_id"], {"id": "duke", "name": "Duke Energy", "kind": "bill", "module": "bills",
                       "sender_domains": "duke-energy.com"})
    assert r["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    rt = get_runtime(hass, entry.entry_id)
    assert "duke" in rt.engine.billers and "bill-duke" in rt.engine.duties
    assert rt.engine.duties["bill-duke"].module == "bills"


async def test_duty_creates_its_module_when_none_exists(hass, entry_factory):
    entry = entry_factory()
    for sub in [s for s in entry.subentries.values() if s.subentry_type == "module"]:
        hass.config_entries.async_remove_subentry(entry, sub.subentry_id)
    assert await hass.config_entries.async_setup(entry.entry_id)
    r = await hass.config_entries.subentries.async_init(
        (entry.entry_id, "duty"), context={"source": "user"})
    assert r["step_id"] == "first_module"
    r = await hass.config_entries.subentries.async_configure(r["flow_id"], {"module_name": "Home"})
    assert r["type"] is FlowResultType.FORM and r["step_id"] == "user"
    assert any(s.data["id"] == "home" for s in entry.subentries.values())


async def test_rows_are_titled_by_kind_and_follow_renames(hass, entry_factory, freezer):
    freezer.move_to("2026-11-14 09:00:00")
    entry = entry_factory()
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    titles = {s.data["id"]: s.title for s in entry.subentries.values()}
    assert titles["a"].startswith("Person · ")
    assert titles["home"] == "Module · " + next(
        s.data["title"]["en"] for s in entry.subentries.values() if s.data["id"] == "home"
    )
    duty = next(s for s in entry.subentries.values() if s.data["id"] == "filters")
    assert duty.title.startswith("Duty · ") and duty.title.count(" · ") == 2

    # renaming a module renames the titles of its duties
    module = next(s for s in entry.subentries.values() if s.data["id"] == "home")
    hass.config_entries.async_update_subentry(
        entry, module, data={**module.data, "title": {"en": "Household"}}
    )
    await hass.async_block_till_done()
    duty = next(s for s in entry.subentries.values() if s.data["id"] == "filters")
    assert duty.title.startswith("Duty · Household · ")


async def test_biller_login_fields_are_saved_and_shown_on_the_todo(hass, bill_entry, freezer):
    from homeassistant.setup import async_setup_component

    freezer.move_to("2026-11-21 09:00:00")
    entry = bill_entry()
    assert await async_setup_component(hass, "homeassistant", {})
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    duke = next(s for s in entry.subentries.values() if s.data.get("id") == "duke")
    r = await entry.start_subentry_reconfigure_flow(hass, duke.subentry_id)
    form = {
        "name": "Duke Energy", "kind": "bill", "module": "bills", "sender_domains": "duke-energy.com",
        "owners": ["b"], "cadence_days": "31", "grace_days": "7", "remind": "-3d,0d",
        "escalate_after": "2d", "enabled": True,
        "login_url": "duke-energy.com/login",  # no https://
        "login_note": "Bitwarden > Home Bills > Duke Energy",
    }
    r = await hass.config_entries.subentries.async_configure(r["flow_id"], form)
    assert r["type"] is FlowResultType.FORM and r["errors"] == {"login_url": "bad_url"}
    defaults = {str(k): k.default() for k in r["data_schema"].schema if hasattr(k, "default")}
    assert defaults["login_note"] == "Bitwarden > Home Bills > Duke Energy"  # nothing typed is lost
    assert defaults["cadence_days"] == "31" and defaults["sender_domains"] == "duke-energy.com"
    r = await hass.config_entries.subentries.async_configure(
        r["flow_id"], {**form, "login_url": "https://example.com/login"})
    assert r["type"] is FlowResultType.ABORT and r["reason"] == "reconfigure_successful"
    await hass.async_block_till_done()
    rt = get_runtime(hass, entry.entry_id)
    assert rt.engine.billers["duke"].login_url == "https://example.com/login"
    rt.engine.apply_bill_state(
        "duke", {"status": "due", "due_date": "2026-12-10", "amount": 50}, dt_util.now())
    rt.notify_entities()
    await hass.async_block_till_done()
    items = (await hass.services.async_call(
        "todo", "get_items", {"entity_id": "todo.homekeeper_bills"}, blocking=True, return_response=True
    ))["todo.homekeeper_bills"]["items"]
    (item,) = items
    assert "Log in: https://example.com/login" in item["description"]
    assert "Bitwarden > Home Bills > Duke Energy" in item["description"]
