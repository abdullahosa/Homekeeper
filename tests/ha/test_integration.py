
import pytest
from homeassistant.exceptions import ServiceValidationError

from custom_components.homekeeper.const import DOMAIN
from custom_components.homekeeper.runtime import get_runtime


async def setup(hass, entry):
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return get_runtime(hass, entry.entry_id)


async def test_setup_creates_entities(hass, entry_factory, freezer):
    freezer.move_to("2026-11-14 09:00:00")
    entry = entry_factory()
    rt = await setup(hass, entry)
    assert set(rt.engine.people) == {"adm", "a", "b"}
    assert hass.states.get("todo.homekeeper_home") is not None
    assert hass.states.get("calendar.homekeeper_schedule") is not None
    assert hass.states.get("binary_sensor.homekeeper_healthy").state == "on"
    assert hass.states.get("sensor.homekeeper_overdue").state == "0"
    nxt = hass.states.get("sensor.homekeeper_replace_filters_next_due")
    assert nxt.state == "2026-12-01"


async def test_tick_notifies_owner_in_their_language(hass, entry_factory, notify_calls, freezer):
    freezer.move_to("2026-12-01 09:00:00")
    rt = await setup(hass, entry_factory())
    to = {c.service: c.data for c in notify_calls}
    assert set(to) == {"mobile_b", "mobile_a"}  # owners only, via module default
    assert to["mobile_a"]["message"] == "Reminder: Replace filters (due 2026-12-01)"
    assert to["mobile_b"]["message"].startswith("تذكير: تغيير الفلاتر")
    actions = to["mobile_b"]["data"]["actions"]
    assert [a["action"].split("|")[1] for a in actions] == ["done", "snooze", "not_mine"]
    assert actions[0]["title"] == "تم"
    # ticking again the same day does not repeat
    n = len(notify_calls)
    await rt.async_tick()
    assert len(notify_calls) == n


async def test_overdue_and_escalation_reach_admin(hass, entry_factory, notify_calls, freezer):
    freezer.move_to("2026-12-03 09:00:00")
    await setup(hass, entry_factory())
    assert "mobile_adm" in {c.service for c in notify_calls}
    assert hass.states.get("sensor.homekeeper_overdue").state == "1"
    assert hass.states.get("sensor.homekeeper_alex_overdue").state == "1"


async def test_complete_service_and_history(hass, entry_factory, freezer):
    freezer.move_to("2026-12-01 09:00:00")
    rt = await setup(hass, entry_factory())
    events = []
    hass.bus.async_listen("homekeeper_completed", lambda e: events.append(e))
    await hass.services.async_call(
        DOMAIN, "complete", {"duty_id": "filters", "by": "a", "note": "ok"}, blocking=True
    )
    await hass.async_block_till_done()
    assert rt.engine.history[-1].by == "a"
    assert hass.states.get("sensor.homekeeper_replace_filters_next_due").state == "2027-03-01"
    assert len(events) == 1
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(DOMAIN, "complete", {"duty_id": "nope"}, blocking=True)
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN, "complete", {"duty_id": "filters", "method": "voice"}, blocking=True
        )


async def test_todo_lists_open_items_and_completes(hass, entry_factory, freezer):
    freezer.move_to("2026-12-01 09:00:00")
    rt = await setup(hass, entry_factory())
    resp = await hass.services.async_call(
        "todo", "get_items", {"entity_id": "todo.homekeeper_home"}, blocking=True, return_response=True
    )
    items = resp["todo.homekeeper_home"]["items"]
    assert [i["uid"] for i in items] == ["filters"]
    await hass.services.async_call(
        "todo", "update_item",
        {"entity_id": "todo.homekeeper_home", "item": "filters", "status": "completed"},
        blocking=True,
    )
    assert rt.engine.history[-1].duty_id == "filters"
    resp = await hass.services.async_call(
        "todo", "get_items", {"entity_id": "todo.homekeeper_home"}, blocking=True, return_response=True
    )
    assert resp["todo.homekeeper_home"]["items"] == []


async def test_calendar_projects_future(hass, entry_factory, freezer):
    freezer.move_to("2026-11-14 09:00:00")
    await setup(hass, entry_factory())
    resp = await hass.services.async_call(
        "calendar", "get_events",
        {"entity_id": "calendar.homekeeper_schedule",
         "start_date_time": "2026-11-01 00:00:00", "end_date_time": "2027-12-31 00:00:00"},
        blocking=True, return_response=True,
    )
    events = resp["calendar.homekeeper_schedule"]["events"]
    assert events and events[0]["summary"] == "Replace filters"
    assert events[0]["start"] == "2026-12-01"


async def test_snooze_and_skip_services(hass, entry_factory, freezer):
    freezer.move_to("2026-12-01 09:00:00")
    rt = await setup(hass, entry_factory())
    await hass.services.async_call(DOMAIN, "snooze", {"duty_id": "filters", "hours": 24}, blocking=True)
    assert hass.states.get("sensor.homekeeper_replace_filters_state").state == "snoozed"
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(DOMAIN, "skip", {"duty_id": "filters", "reason": " "}, blocking=True)
    await hass.services.async_call(DOMAIN, "skip", {"duty_id": "filters", "reason": "away"}, blocking=True)
    assert rt.engine.history[-1].kind == "skipped"


async def test_mobile_action_buttons(hass, entry_factory, notify_calls, freezer):
    freezer.move_to("2026-12-01 09:00:00")
    rt = await setup(hass, entry_factory())
    hass.bus.async_fire("mobile_app_notification_action", {"action": "HK|not_mine|filters|b"})
    await hass.async_block_till_done()
    assert rt.engine.duties["filters"].owners == ["a", "b"]
    sub = next(s for s in rt.entry.subentries.values() if s.data.get("id") == "filters")
    assert sub.data["owners"] == ["a", "b"]  # persisted, survives reload
    assert "mobile_adm" in {c.service for c in notify_calls}  # admin told
    hass.bus.async_fire("mobile_app_notification_action", {"action": "HK|done|filters|a"})
    await hass.async_block_till_done()
    assert rt.engine.history[-1].by == "a"
    hass.bus.async_fire("mobile_app_notification_action", {"action": "SOMETHING_ELSE"})
    await hass.async_block_till_done()


async def test_state_survives_reload(hass, entry_factory, freezer):
    freezer.move_to("2026-12-01 09:00:00")
    entry = entry_factory()
    rt = await setup(hass, entry)
    await hass.services.async_call(DOMAIN, "complete", {"duty_id": "filters", "by": "a"}, blocking=True)
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    rt2 = get_runtime(hass, entry.entry_id)
    assert rt2 is not rt
    assert rt2.engine.history and rt2.engine.history[-1].by == "a"
    assert rt2.engine.occurrences["filters"].due.isoformat() == "2027-03-01"


async def test_unload(hass, entry_factory, freezer):
    freezer.move_to("2026-12-01 09:00:00")
    entry = entry_factory()
    await setup(hass, entry)
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert DOMAIN not in hass.data or entry.entry_id not in hass.data[DOMAIN]
