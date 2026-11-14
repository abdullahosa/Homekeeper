import json

from pytest_homeassistant_custom_component.common import async_fire_mqtt_message

from custom_components.homekeeper.const import DOMAIN
from custom_components.homekeeper.runtime import get_runtime


def bill(status="due", due="2026-12-10", amount=120.5, arrived="2026-11-20", **kw):
    return json.dumps(
        {"status": status, "due_date": due, "amount": amount, "arrived": arrived,
         "paid": None, "paid_amount": None, "autopay": False, **kw}
    )


async def start(hass, entry):
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return get_runtime(hass, entry.entry_id)


def published(mqtt_mock, topic):
    return [c.args for c in mqtt_mock.async_publish.call_args_list if c.args[0] == topic]


async def test_publishes_biller_list_retained(hass, mqtt_mock, bill_entry, freezer):
    freezer.move_to("2026-11-14 09:00:00")
    await start(hass, bill_entry())
    calls = published(mqtt_mock, "homekeeper/billers")
    assert calls, "biller list was not published"
    topic, payload, qos, retain = calls[-1]
    assert retain is True
    data = json.loads(payload)
    assert data["billers"] == {
        "duke-energy.com": "Duke Energy",
        "dukeenergy.com": "Duke Energy",
        "zillow.com": "Rent payments",
    }


async def test_bill_posted_opens_duty_notifies_owner_with_amount(
    hass, mqtt_mock, bill_entry, notify_calls, freezer
):
    freezer.move_to("2026-11-21 09:00:00")
    rt = await start(hass, bill_entry())
    async_fire_mqtt_message(hass, "billbot/duke_energy/state", bill())
    await hass.async_block_till_done()
    assert rt.engine.occurrences["bill-duke"].due.isoformat() == "2026-12-10"
    sent = {c.service: c.data for c in notify_calls}
    assert set(sent) == {"mobile_b"}  # the biller's owner only
    assert "$120.50" in sent["mobile_b"]["message"]
    assert sent["mobile_b"]["message"].startswith("مهمة جديدة")  # Basil gets Arabic
    items = (await hass.services.async_call(
        "todo", "get_items", {"entity_id": "todo.homekeeper_bills"}, blocking=True, return_response=True
    ))["todo.homekeeper_bills"]["items"]
    assert [i["uid"] for i in items] == ["bill-duke"]


async def test_marking_paid_in_homekeeper_presses_billbot_button(
    hass, mqtt_mock, bill_entry, freezer
):
    freezer.move_to("2026-11-21 09:00:00")
    rt = await start(hass, bill_entry())
    async_fire_mqtt_message(hass, "billbot/duke_energy/state", bill())
    await hass.async_block_till_done()
    await hass.services.async_call(
        DOMAIN, "complete", {"duty_id": "bill-duke", "by": "b"}, blocking=True
    )
    assert published(mqtt_mock, "billbot/duke_energy/mark_paid")[-1][1] == "PRESS"
    assert "bill-duke" not in rt.engine.occurrences


async def test_paid_by_billbot_closes_without_pressing_again(hass, mqtt_mock, bill_entry, freezer):
    freezer.move_to("2026-11-21 09:00:00")
    rt = await start(hass, bill_entry())
    async_fire_mqtt_message(hass, "billbot/duke_energy/state", bill())
    await hass.async_block_till_done()
    async_fire_mqtt_message(
        hass, "billbot/duke_energy/state", bill("paid", paid="2026-12-01", paid_amount=120.5)
    )
    await hass.async_block_till_done()
    assert "bill-duke" not in rt.engine.occurrences
    assert rt.engine.history[-1].method == "auto"
    assert not published(mqtt_mock, "billbot/duke_energy/mark_paid")
    # a replay of the old retained state does not reopen it
    async_fire_mqtt_message(hass, "billbot/duke_energy/state", bill())
    await hass.async_block_till_done()
    assert "bill-duke" not in rt.engine.occurrences


async def test_rent_payment_completes_rent_check(hass, mqtt_mock, bill_entry, freezer):
    freezer.move_to("2026-11-30 09:00:00")
    rt = await start(hass, bill_entry())
    assert rt.engine.occurrences["rent-check"].due.isoformat() == "2026-12-01"
    async_fire_mqtt_message(
        hass, "billbot/rent_payments/state",
        json.dumps({"status": "paid", "due_date": "2026-11-30", "paid": "2026-11-30",
                    "amount": 2000, "arrived": None}),
    )
    await hass.async_block_till_done()
    assert rt.engine.occurrences["rent-check"].due.isoformat() == "2026-12-15"
    assert rt.engine.history[-1].method == "auto"


async def test_garbage_and_unknown_messages_are_ignored(hass, mqtt_mock, bill_entry, freezer):
    freezer.move_to("2026-11-21 09:00:00")
    rt = await start(hass, bill_entry())
    async_fire_mqtt_message(hass, "billbot/duke_energy/state", "not json")
    async_fire_mqtt_message(hass, "billbot/duke_energy/state", "[1,2]")
    async_fire_mqtt_message(hass, "billbot/some_other_biller/state", bill())
    async_fire_mqtt_message(hass, "billbot/duke_energy/state", json.dumps({"status": "due", "due_date": "garbage"}))
    await hass.async_block_till_done()
    assert "bill-duke" not in rt.engine.occurrences
    assert hass.states.get("binary_sensor.homekeeper_healthy").state == "on"


async def test_billbot_offline_and_silent_biller_trip_health(hass, mqtt_mock, bill_entry, freezer):
    freezer.move_to("2026-11-21 09:00:00")
    rt = await start(hass, bill_entry())
    assert hass.states.get("binary_sensor.homekeeper_healthy").state == "on"
    async_fire_mqtt_message(hass, "billbot/status", "offline")
    await hass.async_block_till_done()
    state = hass.states.get("binary_sensor.homekeeper_healthy")
    assert state.state == "off" and "billbot_offline" in state.attributes["problems"]
    async_fire_mqtt_message(hass, "billbot/status", "online")
    await hass.async_block_till_done()
    assert hass.states.get("binary_sensor.homekeeper_healthy").state == "on"
    freezer.move_to("2027-02-01 09:00:00")  # months with no bill from Duke
    assert "biller_silent:duke" in rt.health_problems()


async def test_add_biller_via_ui_republishes_list(hass, mqtt_mock, bill_entry, freezer):
    freezer.move_to("2026-11-21 09:00:00")
    entry = bill_entry()
    rt = await start(hass, entry)
    r = await hass.config_entries.subentries.async_init(
        (entry.entry_id, "biller"), context={"source": "user"}
    )
    r = await hass.config_entries.subentries.async_configure(
        r["flow_id"],
        {"id": "gas", "name": "Enbridge Gas", "kind": "bill", "module": "bills",
         "sender_domains": "enbridgegas.com", "owners": ["b"], "observers": [],
         "cadence_days": "31", "grace_days": "7", "completes": "",
         "remind": "-3d,0d", "escalate_after": "2d", "enabled": True},
    )
    assert r["type"].value == "create_entry"
    await hass.async_block_till_done()
    rt = get_runtime(hass, entry.entry_id)
    assert "gas" in rt.engine.billers
    last = json.loads(published(mqtt_mock, "homekeeper/billers")[-1][1])
    assert last["billers"]["enbridgegas.com"] == "Enbridge Gas"
    # removing it again drops the domain
    sub = next(s for s in entry.subentries.values() if s.data["id"] == "gas")
    hass.config_entries.async_remove_subentry(entry, sub.subentry_id)
    await hass.async_block_till_done()
    last = json.loads(published(mqtt_mock, "homekeeper/billers")[-1][1])
    assert "enbridgegas.com" not in last["billers"]


async def test_bills_pack_imports_billers_as_subentries(hass, mqtt_mock, bill_entry, freezer):
    from pathlib import Path

    freezer.move_to("2026-11-21 09:00:00")
    entry = bill_entry()
    rt = await start(hass, entry)
    text = (Path(__file__).resolve().parents[2] / "packs" / "bills.yaml").read_text()
    # the shipped pack's module id collides with the existing "bills" module: kept as-is
    out = await hass.services.async_call(
        DOMAIN, "import_pack", {"pack": text}, blocking=True, return_response=True)
    assert out["applied"] and "biller:electric" in out["created"]
    await hass.async_block_till_done()
    rt = get_runtime(hass, entry.entry_id)
    assert {"electric", "water", "internet", "duke"} <= set(rt.engine.billers)
    assert "bill-electric" in rt.engine.duties
    exported = await hass.services.async_call(
        DOMAIN, "export_pack", {"module": "bills"}, blocking=True, return_response=True)
    assert {b["id"] for b in exported["billers"]} >= {"electric", "duke"}
    assert all(not d["id"].startswith("bill-") for d in exported["duties"])


async def test_state_survives_reload(hass, mqtt_mock, bill_entry, freezer):
    freezer.move_to("2026-11-21 09:00:00")
    entry = bill_entry()
    await start(hass, entry)
    async_fire_mqtt_message(hass, "billbot/duke_energy/state", bill())
    await hass.async_block_till_done()
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    rt = get_runtime(hass, entry.entry_id)
    occ = rt.engine.occurrences["bill-duke"]
    assert occ.due.isoformat() == "2026-12-10" and occ.meta["amount"] == 120.5
    assert rt.engine.biller_seen["duke"] == "2026-11-20"
