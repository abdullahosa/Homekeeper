"""Health of the integration: on means everything is fine."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import BinarySensorEntity

from .entity import HomekeeperEntity
from .runtime import Runtime, get_runtime


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    async_add_entities([HomekeeperHealthy(get_runtime(hass, entry.entry_id))])


class HomekeeperHealthy(HomekeeperEntity, BinarySensorEntity):
    _attr_name = "Healthy"

    def __init__(self, runtime: Runtime) -> None:
        super().__init__(runtime)
        self._attr_unique_id = f"{runtime.entry.entry_id}_healthy"

    @property
    def is_on(self) -> bool:
        return not self.runtime.health_problems()

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"problems": self.runtime.health_problems()}
