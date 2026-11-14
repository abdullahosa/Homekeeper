"""Homekeeper: shared household duties for Home Assistant."""

from __future__ import annotations

from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, HomeAssistant
from homeassistant.helpers.event import async_track_time_interval

from .const import DOMAIN, PLATFORMS, TICK_INTERVAL_MINUTES
from .runtime import Runtime
from .services import async_register_services

type HomekeeperConfigEntry = ConfigEntry


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    runtime = Runtime(hass, entry)
    await runtime.async_load()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = runtime

    async_register_services(hass)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    async def _tick(now) -> None:
        await runtime.async_tick()

    async def _action(event: Event) -> None:
        await runtime.async_handle_action(str(event.data.get("action", "")))

    entry.async_on_unload(
        async_track_time_interval(
            hass, _tick, timedelta(minutes=TICK_INTERVAL_MINUTES)
        )
    )
    entry.async_on_unload(
        hass.bus.async_listen("mobile_app_notification_action", _action)
    )
    entry.async_on_unload(entry.add_update_listener(_updated))
    await runtime.async_tick()
    return True


async def _updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    runtime: Runtime | None = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    if runtime is None or runtime.importing:
        return
    if runtime.compute_signature() != runtime.signature:
        await hass.config_entries.async_reload(entry.entry_id)
        return
    runtime.sync_definitions()
    runtime.schedule_save()
    runtime.notify_entities()


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    runtime: Runtime = hass.data[DOMAIN][entry.entry_id]
    await runtime.async_save_now()
    ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return ok
