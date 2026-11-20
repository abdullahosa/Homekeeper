"""Calendars: one with every occurrence projected forward, and tidy copies of other
calendars (trash pickups as "Garbage + Recycling"): one per Calendar item and one per
duty that follows a calendar."""

from __future__ import annotations

from datetime import date, datetime, timedelta

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .entity import HomekeeperEntity
from .runtime import Runtime, get_runtime


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    runtime = get_runtime(hass, entry.entry_id)
    entities: list[CalendarEntity] = [HomekeeperCalendar(runtime)]
    for cal_id, cfg in runtime.tidy_calendars.items():
        entities.append(
            PickupCalendar(runtime, f"cal:{cal_id}", cfg.get("name") or cal_id, f"tidycal_{cal_id}")
        )
    for duty in runtime.engine.duties.values():
        if duty.schedule.get("type") == "calendar":
            lead = duty.schedule.get("lead", "1d")
            when = {"0d": "on the day", "1d": "the evening before"}.get(lead, f"{lead} before")
            title = duty.display_title("en")
            entities.append(
                PickupCalendar(runtime, duty.id, f"{title} pickups", f"pickups_{duty.id}", f"{title}: {when}")
            )
    async_add_entities(entities)


class HomekeeperCalendar(HomekeeperEntity, CalendarEntity):
    _attr_name = "Schedule"

    def __init__(self, runtime: Runtime) -> None:
        super().__init__(runtime)
        self._attr_unique_id = f"{runtime.entry.entry_id}_calendar"

    def _events_between(self, start: date, end: date) -> list[CalendarEvent]:
        eng = self.runtime.engine
        events: list[CalendarEvent] = []
        for duty in eng.duties.values():
            for due in eng.project(duty.id, end):
                if due < start:
                    continue
                events.append(
                    CalendarEvent(
                        start=due,
                        end=due + timedelta(days=1),
                        summary=duty.display_title("en"),
                        description="\n".join(
                            p for p in (duty.how_to, *eng.login_lines(duty), *eng.calendar_lines(duty)) if p
                        )
                        or None,
                        uid=f"{duty.id}:{due.isoformat()}",
                    )
                )
        return sorted(events, key=lambda e: (e.start, e.summary))

    @property
    def event(self) -> CalendarEvent | None:
        today = dt_util.now().date()
        events = self._events_between(today, today + timedelta(days=366))
        return events[0] if events else None

    async def async_get_events(
        self, hass: HomeAssistant, start_date: datetime, end_date: datetime
    ) -> list[CalendarEvent]:
        return self._events_between(start_date.date(), end_date.date())


class PickupCalendar(HomekeeperEntity, CalendarEntity):
    """Another calendar, cleaned up: only the days asked for, each titled with the carts
    ("Garbage + Recycling + Yard waste"), original titles in the description. Made for
    the calendar card. From a Calendar item, or from a duty that follows a calendar."""

    _attr_icon = "mdi:trash-can-outline"

    def __init__(self, runtime: Runtime, key: str, name: str, unique: str, note: str = "") -> None:
        super().__init__(runtime)
        self._key = key
        self._note = note
        self._attr_unique_id = f"{runtime.entry.entry_id}_{unique}"
        self._attr_name = name

    def _events_between(self, start: date, end: date) -> list[CalendarEvent]:
        out = []
        for day, what, raw in self.runtime.pickups.get(self._key, []):
            if start <= day < end:
                out.append(
                    CalendarEvent(
                        start=day,
                        end=day + timedelta(days=1),
                        summary=what or raw or "Pickup",
                        description="\n".join(p for p in (self._note, raw) if p) or None,
                        uid=f"{self._key}:{day.isoformat()}",
                    )
                )
        return out

    @property
    def event(self) -> CalendarEvent | None:
        today = dt_util.now().date()
        upcoming = self._events_between(today, today + timedelta(days=366))
        return upcoming[0] if upcoming else None

    async def async_get_events(
        self, hass: HomeAssistant, start_date: datetime, end_date: datetime
    ) -> list[CalendarEvent]:
        return self._events_between(start_date.date(), end_date.date())
