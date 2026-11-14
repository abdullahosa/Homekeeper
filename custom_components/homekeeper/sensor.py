"""Overdue counts (total and per person) and per-duty next-due dates."""

from __future__ import annotations

from datetime import date

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.const import EntityCategory
from homeassistant.util import dt as dt_util

from .entity import HomekeeperEntity
from .runtime import Runtime, get_runtime


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    runtime = get_runtime(hass, entry.entry_id)
    eng = runtime.engine
    entities: list[SensorEntity] = [OverdueCount(runtime, None)]
    entities += [OverdueCount(runtime, pid) for pid in eng.people]
    for duty_id in eng.duties:
        entities.append(NextDue(runtime, duty_id))
        entities.append(DutyState(runtime, duty_id))
    async_add_entities(entities)


class OverdueCount(HomekeeperEntity, SensorEntity):
    _attr_icon = "mdi:alert-circle-outline"
    _attr_native_unit_of_measurement = "duties"

    def __init__(self, runtime: Runtime, person_id: str | None) -> None:
        super().__init__(runtime)
        self._person = person_id
        suffix = person_id or "all"
        self._attr_unique_id = f"{runtime.entry.entry_id}_overdue_{suffix}"
        self._attr_name = (
            "Overdue"
            if person_id is None
            else f"{runtime.engine.people[person_id].name} overdue"
        )

    @property
    def native_value(self) -> int:
        today = dt_util.now().date()
        items = self.runtime.engine.open_items(today, owner=self._person)
        return sum(1 for _, _, s in items if s == "overdue")


class NextDue(HomekeeperEntity, SensorEntity):
    _attr_device_class = SensorDeviceClass.DATE

    def __init__(self, runtime: Runtime, duty_id: str) -> None:
        super().__init__(runtime)
        self._duty_id = duty_id
        duty = runtime.engine.duties[duty_id]
        self._attr_unique_id = f"{runtime.entry.entry_id}_{duty_id}_next_due"
        self._attr_name = f"{duty.display_title('en')} next due"

    @property
    def native_value(self) -> date | None:
        occ = self.runtime.engine.occurrences.get(self._duty_id)
        return occ.due if occ else None


class DutyState(HomekeeperEntity, SensorEntity):
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = ["idle", "upcoming", "due", "overdue", "snoozed"]
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, runtime: Runtime, duty_id: str) -> None:
        super().__init__(runtime)
        self._duty_id = duty_id
        duty = runtime.engine.duties[duty_id]
        self._attr_unique_id = f"{runtime.entry.entry_id}_{duty_id}_state"
        self._attr_name = f"{duty.display_title('en')} state"

    @property
    def native_value(self) -> str:
        return self.runtime.engine.state(self._duty_id, dt_util.now().date())
