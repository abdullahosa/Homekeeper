"""WebSocket API for the Homekeeper card."""

from __future__ import annotations

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .engine.overview import build_overview
from .runtime import Runtime


def _runtime(hass: HomeAssistant) -> Runtime | None:
    runtimes = hass.data.get(DOMAIN, {})
    return next((r for r in runtimes.values() if isinstance(r, Runtime)), None)


def me_for_user(hass: HomeAssistant, runtime: Runtime, user_id: str | None) -> str | None:
    """The Homekeeper person whose linked `person.*` entity belongs to this login."""
    if not user_id:
        return None
    for person in runtime.engine.people.values():
        if not person.person_entity:
            continue
        state = hass.states.get(person.person_entity)
        if state is not None and state.attributes.get("user_id") == user_id:
            return person.id
    return None


@callback
def async_register(hass: HomeAssistant) -> None:
    websocket_api.async_register_command(hass, ws_overview)


@websocket_api.websocket_command(
    {
        vol.Required("type"): "homekeeper/overview",
        vol.Optional("horizon_days", default=14): vol.All(int, vol.Range(min=0, max=366)),
    }
)
@callback
def ws_overview(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict) -> None:
    runtime = _runtime(hass)
    if runtime is None:
        connection.send_error(msg["id"], "not_loaded", "Homekeeper is not set up")
        return
    overview = build_overview(runtime.engine, dt_util.now().date(), msg["horizon_days"])
    overview["me"] = me_for_user(hass, runtime, connection.user.id if connection.user else None)
    overview["health"] = {"ok": not runtime.health_problems(), "problems": runtime.health_problems()}
    connection.send_result(msg["id"], overview)
