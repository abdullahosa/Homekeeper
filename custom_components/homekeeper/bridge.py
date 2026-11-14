"""BillBot bridge: reads BillBot's MQTT topics, publishes the biller list.

BillBot reads, Homekeeper runs: BillBot keeps the mailbox pipeline and Duke PDF
parsing; this module only listens to its state and presses its Mark paid button.
"""

from __future__ import annotations

import json
import logging
import re
from typing import TYPE_CHECKING, Any

from homeassistant.components import mqtt
from homeassistant.core import callback
from homeassistant.util import dt as dt_util

if TYPE_CHECKING:
    from .runtime import Runtime

_LOGGER = logging.getLogger(__name__)

BILLERS_TOPIC = "homekeeper/billers"
STATE_TOPIC = "billbot/+/state"
STATUS_TOPIC = "billbot/status"


def slug(name: str) -> str:
    """Same rule BillBot uses to turn a biller name into its topic segment."""
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_") or "unknown"


class BillBotBridge:
    def __init__(self, runtime: Runtime) -> None:
        self.rt = runtime
        self.available: bool | None = None  # None until the first BillBot status message
        self.mqtt_ready = False
        self._unsubs: list = []

    # ---------------------------------------------------------------- wiring
    async def async_start(self) -> None:
        hass = self.rt.hass
        if not await mqtt.async_wait_for_mqtt_client(hass):
            _LOGGER.warning("MQTT is not available; BillBot bridge is off")
            return
        self.mqtt_ready = True
        self._unsubs.append(await mqtt.async_subscribe(hass, STATE_TOPIC, self._on_state, 1))
        self._unsubs.append(await mqtt.async_subscribe(hass, STATUS_TOPIC, self._on_status, 1))
        await self.async_publish_billers()
        self.rt.notify_entities()  # health no longer reports mqtt_unavailable

    def stop(self) -> None:
        for unsub in self._unsubs:
            unsub()
        self._unsubs.clear()

    # ------------------------------------------------------------- outbound
    def biller_map(self) -> dict[str, str]:
        """sender domain or address -> BillBot biller name, for every enabled biller."""
        out: dict[str, str] = {}
        for biller in self.rt.engine.billers.values():
            if biller.enabled:
                for domain in biller.sender_domains:
                    out[domain.lower()] = biller.name
        return out

    async def async_publish_billers(self) -> None:
        if not self.mqtt_ready:
            return
        payload = json.dumps({"version": 1, "billers": self.biller_map()}, sort_keys=True)
        await mqtt.async_publish(self.rt.hass, BILLERS_TOPIC, payload, 1, True)

    async def async_press_mark_paid(self, biller_id: str) -> None:
        """Tell BillBot a bill was paid (so it, the source of truth, records it)."""
        biller = self.rt.engine.billers.get(biller_id)
        if biller is None or not self.mqtt_ready:
            return
        await mqtt.async_publish(
            self.rt.hass, f"billbot/{slug(biller.name)}/mark_paid", "PRESS", 1, False
        )

    # -------------------------------------------------------------- inbound
    @callback
    def _on_status(self, msg: Any) -> None:
        payload = str(msg.payload).strip().lower()
        if payload in ("online", "offline"):
            self.available = payload == "online"
            self.rt.notify_entities()

    async def _on_state(self, msg: Any) -> None:
        parts = msg.topic.split("/")
        if len(parts) != 3:
            return
        biller_id = self._biller_for_slug(parts[1])
        if biller_id is None:
            return
        try:
            payload = json.loads(msg.payload)
        except (TypeError, ValueError):
            _LOGGER.debug("Ignoring non-JSON BillBot state on %s", msg.topic)
            return
        if not isinstance(payload, dict):
            return
        await self.handle_state(biller_id, payload)

    def _biller_for_slug(self, topic_slug: str) -> str | None:
        for biller in self.rt.engine.billers.values():
            if slug(biller.name) == topic_slug:
                return biller.id
        return None

    async def handle_state(self, biller_id: str, payload: dict[str, Any]) -> None:
        now = dt_util.now()
        try:
            result = self.rt.engine.apply_bill_state(biller_id, payload, now)
        except (ValueError, KeyError, TypeError):
            _LOGGER.warning("Could not apply BillBot state for %s: %s", biller_id, payload, exc_info=True)
            return
        await self.rt._dispatch(result, now)
        await self.rt.async_tick(now)
