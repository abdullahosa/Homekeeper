"""A duty that follows a calendar (trash pickup), through Home Assistant."""

from datetime import date, datetime

import pytest
from helpers import sub
from homeassistant.components.calendar import DATA_COMPONENT as CALENDAR_COMPONENT
from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import HomeAssistantError
from homeassistant.setup import async_setup_component

from custom_components.homekeeper.runtime import get_runtime

EVENTS = [
    {"start": "2026-11-24", "end": "2026-11-25", "summary": "Garbage, Recycling"},
    {"start": "2026-12-01", "end": "2026-12-02", "summary": "Garbage"},
]


class FakeCalendar(CalendarEntity):
    """What the Remote Calendar integration gives you for the CARTology link."""

    _attr_name = "CARTology"

    def __init__(self, state):
        self._state = state
        self.entity_id = "calendar.cartology"

    @property
    def event(self):
        return None

    async def async_get_events(self, hass, start_date, end_date):
        if self._state["fail"]:
            raise HomeAssistantError("calendar is down")
        return [
            CalendarEvent(start=date.fromisoformat(e["start"]), end=date.fromisoformat(e["end"]), summary=e["summary"])
            for e in self._state["events"]
        ]


@pytest.fixture
async def calendar_events(hass):
    state = {"events": list(EVENTS), "fail": False}
    assert await async_setup_component(hass, "calendar", {})
    await hass.data[CALENDAR_COMPONENT].async_add_entities([FakeCalendar(state)])
    await hass.async_block_till_done()
    return state


def bins_entry(entry_factory):
    return entry_factory(extra=(
        sub("duty", "bins", {
            "module": "home",
            "title": {"en": "Put the bins out", "ar": "إخراج الحاويات"},
            "schedule": {"type": "calendar", "calendar": "calendar.cartology", "lead": "1d", "notify_at": "18:00"},
            "remind": [],
            "done_by": ["button", "nfc"],
        }, "Put the bins out"),
    ))


async def start(hass, entry, freezer):
    await hass.config.async_set_time_zone("America/New_York")
    freezer.move_to("2026-11-19 14:00:00+00:00")  # a weekday morning before bin night
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return get_runtime(hass, entry.entry_id)


def local(text):
    from homeassistant.util import dt as dt_util

    return datetime.fromisoformat(text).replace(tzinfo=dt_util.get_default_time_zone())


async def test_bin_night_push_waits_for_18_00_and_says_what(hass, entry_factory, calendar_events, notify_calls, freezer):
    rt = await start(hass, bins_entry(entry_factory), freezer)
    assert rt.engine.occurrences["bins"].meta["event"] == "2026-11-24"
    await rt.async_tick(local("2026-11-23T09:00"))
    assert notify_calls == []  # due today, but it waits for the evening
    await rt.async_tick(local("2026-11-23T18:05"))
    sent = {c.service: c.data["message"] for c in notify_calls}
    assert set(sent) == {"mobile_a", "mobile_b"}
    assert "Put the bins out: Garbage + Recycling" in sent["mobile_a"]
    assert "النفايات + إعادة التدوير" in sent["mobile_b"]  # Basil reads Arabic


async def test_done_before_the_evening_cancels_the_waiting_push(hass, entry_factory, calendar_events, notify_calls, freezer):
    rt = await start(hass, bins_entry(entry_factory), freezer)
    await rt.async_tick(local("2026-11-23T09:00"))
    await hass.services.async_call(
        "homekeeper", "complete", {"duty_id": "bins", "method": "button", "by": "a"}, blocking=True
    )
    await rt.async_tick(local("2026-11-23T18:05"))
    assert notify_calls == []
    assert rt.engine.occurrences["bins"].meta["event"] == "2026-12-01"  # on to next week


async def test_still_out_on_pickup_morning_waits_until_6(hass, entry_factory, calendar_events, notify_calls, freezer):
    rt = await start(hass, bins_entry(entry_factory), freezer)
    await rt.async_tick(local("2026-11-23T18:05"))
    notify_calls.clear()
    await rt.async_tick(local("2026-11-24T00:05"))
    assert notify_calls == []
    await rt.async_tick(local("2026-11-24T06:05"))
    assert {c.service for c in notify_calls} == {"mobile_a", "mobile_b", "mobile_adm"}  # owners + admin
    assert all(c.data["message"].startswith(("Overdue", "متأخرة")) for c in notify_calls)


async def test_missing_calendar_is_a_health_problem(hass, entry_factory, calendar_events, notify_calls, freezer):
    calendar_events["fail"] = True
    rt = await start(hass, bins_entry(entry_factory), freezer)
    assert "calendar_unavailable:bins" in rt.health_problems()
    calendar_events["fail"] = False
    await rt.async_tick(local("2026-11-19T10:00"))
    assert "calendar_unavailable:bins" not in rt.health_problems()
    assert "bins" in rt.engine.occurrences


async def test_todo_item_says_what_is_collected(hass, entry_factory, calendar_events, notify_calls, freezer):
    rt = await start(hass, bins_entry(entry_factory), freezer)
    await rt.async_tick(local("2026-11-23T09:00"))
    freezer.move_to("2026-11-23 14:00:00+00:00")
    rt.notify_entities()
    await hass.async_block_till_done()
    items = (await hass.services.async_call(
        "todo", "get_items", {"entity_id": "todo.homekeeper_home"}, blocking=True, return_response=True
    ))["todo.homekeeper_home"]["items"]
    bins = next(i for i in items if i["uid"] == "bins")
    assert "Collecting: Garbage + Recycling on 2026-11-24" in bins["description"]


async def test_duty_form_follows_a_calendar(hass, entry_factory, calendar_events, freezer):
    entry = entry_factory()
    rt = await start(hass, entry, freezer)
    r = await hass.config_entries.subentries.async_init((entry.entry_id, "duty"), context={"source": "user"})
    r = await hass.config_entries.subentries.async_configure(r["flow_id"], {
        "id": "recycling", "module": "home", "title_en": "Put recycling out", "owners": ["a"],
        "schedule_type": "calendar",
    })
    assert r["step_id"] == "schedule"
    assert "opens_before" not in {str(k) for k in r["data_schema"].schema}
    r = await hass.config_entries.subentries.async_configure(r["flow_id"], {
        "calendar": "calendar.cartology", "match": "Recycling", "lead": "1d", "notify_at": "18:30:00",
    })
    assert r["step_id"] == "details"
    r = await hass.config_entries.subentries.async_configure(r["flow_id"], {"done_by": ["button"]})
    assert r["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    rt = get_runtime(hass, entry.entry_id)
    assert rt.engine.duties["recycling"].schedule == {
        "type": "calendar", "calendar": "calendar.cartology", "match": ["Recycling"], "lead": "1d",
        "notify_at": "18:30",
    }
    await rt.async_tick(local("2026-11-19T10:00"))
    assert rt.engine.occurrences["recycling"].meta["event"] == "2026-11-24"


async def test_holiday_move_the_day_before_sends_a_moved_push(hass, entry_factory, calendar_events, notify_calls, freezer):
    rt = await start(hass, bins_entry(entry_factory), freezer)
    calendar_events["events"] = [
        {"start": "2026-11-25", "end": "2026-11-26", "summary": "Garbage, Recycling"},
        *EVENTS[1:],
    ]
    await rt.async_tick(local("2026-11-22T12:00"))  # bin night was tomorrow
    sent = {c.service: c.data["message"] for c in notify_calls}
    assert sent["mobile_a"] == "Moved to 2026-11-25: Put the bins out: Garbage + Recycling"
    assert sent["mobile_b"].startswith("تغيّر الموعد إلى 2026-11-25")
    assert rt.engine.occurrences["bins"].due.isoformat() == "2026-11-24"
