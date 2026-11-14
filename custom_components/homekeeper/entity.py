"""Shared entity base."""

from __future__ import annotations

from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import Entity

from .const import DOMAIN, SIGNAL_UPDATE
from .runtime import Runtime


class HomekeeperEntity(Entity):
    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, runtime: Runtime) -> None:
        self.runtime = runtime
        entry_id = runtime.entry.entry_id
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry_id)},
            name="Homekeeper",
            manufacturer="Homekeeper",
        )

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_UPDATE.format(entry_id=self.runtime.entry.entry_id),
                self._handle_update,
            )
        )

    @callback
    def _handle_update(self) -> None:
        self.async_write_ha_state()
