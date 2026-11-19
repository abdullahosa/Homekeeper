"""One calendar with every occurrence, projected forward."""

from __future__ import annotations

from datetime import date, datetime, timedelta

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .entity import HomekeeperEntity
from .runtime import Runtime, get_runtime


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    async_add_entities([HomekeeperCalendar(get_runtime(hass, entry.entry_id))])


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
