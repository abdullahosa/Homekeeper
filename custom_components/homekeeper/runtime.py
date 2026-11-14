"""Runtime glue between the pure engine and Home Assistant."""

from __future__ import annotations

import logging
from datetime import datetime, time
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from . import messages
from .bridge import BillBotBridge
from .const import (
    ACTION_PREFIX,
    CONF_CONDITIONS,
    DOMAIN,
    EVENT_PREFIX,
    SIGNAL_UPDATE,
    STORAGE_KEY,
    STORAGE_VERSION,
    SUBENTRY_BILLER,
    SUBENTRY_DUTY,
    SUBENTRY_MODULE,
    SUBENTRY_PERSON,
)
from .engine import Biller, Duty, Engine, Module, Notification, Person, TickResult

_LOGGER = logging.getLogger(__name__)


def parse_conditions(text: str) -> dict[str, str]:
    """'key=sensor.a, key2=sensor.b' -> {'key': 'sensor.a', ...}"""
    out: dict[str, str] = {}
    for part in (text or "").replace("\n", ",").split(","):
        if "=" in part:
            key, entity = (p.strip() for p in part.split("=", 1))
            if key and entity:
                out[key] = entity
    return out


def in_quiet_hours(person: Person, now: datetime) -> bool:
    if not person.quiet_hours or len(person.quiet_hours) != 2:
        return False
    start, end = (time.fromisoformat(t) for t in person.quiet_hours)
    here = now.time()
    if start <= end:
        return start <= here < end
    return here >= start or here < end


class Runtime:
    """Owns the engine for one config entry."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self.engine = Engine()
        self.store: Store[dict[str, Any]] = Store(
            hass, STORAGE_VERSION, f"{STORAGE_KEY}.{entry.entry_id}"
        )
        self.queue: list[tuple[str, Notification]] = []
        self.invalid: list[str] = []
        self.last_tick: datetime | None = None
        self._saved_occurrences: dict[str, dict[str, Any]] = {}
        self.signature: tuple = ()
        self.importing = False
        self.bridge = BillBotBridge(self)

    # ------------------------------------------------------------ lifecycle
    async def async_load(self) -> None:
        saved = await self.store.async_load() or {}
        self.engine.history = Engine.from_dict(
            {"history": saved.get("history", [])}
        ).history
        self.engine.biller_seen = dict(saved.get("biller_seen", {}))
        self.engine.biller_since = dict(saved.get("biller_since", {}))
        saved_occ = {o["duty_id"]: o for o in saved.get("occurrences", [])}
        self._saved_occurrences = saved_occ
        self.sync_definitions()

    def sync_definitions(self) -> None:
        """Rebuild people, modules and duties from the config entry's subentries."""
        eng = self.engine
        today = dt_util.now().date()
        eng.people = {}
        eng.modules = {}
        for sub in self.entry.subentries.values():
            if sub.subentry_type == SUBENTRY_PERSON:
                person = Person.from_dict(dict(sub.data))
                eng.people[person.id] = person
            elif sub.subentry_type == SUBENTRY_MODULE:
                module = Module.from_dict(dict(sub.data))
                eng.modules[module.id] = module
        wanted: dict[str, Duty] = {}
        self.invalid = []
        billers: dict[str, Biller] = {}
        for sub in self.entry.subentries.values():
            if sub.subentry_type == SUBENTRY_BILLER:
                try:
                    biller = Biller.from_dict(dict(sub.data))
                except (TypeError, KeyError, ValueError) as err:
                    self.invalid.append(f"{sub.title}: {err}")
                    continue
                billers[biller.id] = biller
                duty = eng.biller_duty(biller)
                if duty is not None:
                    wanted[duty.id] = duty
        eng.billers = billers
        for biller in billers.values():
            eng.biller_since.setdefault(biller.id, today.isoformat())
        self.signature = self.compute_signature()
        for sub in self.entry.subentries.values():
            if sub.subentry_type == SUBENTRY_DUTY:
                try:
                    duty = Duty.from_dict(dict(sub.data))
                    wanted[duty.id] = duty
                except (TypeError, KeyError) as err:
                    self.invalid.append(f"{sub.title}: {err}")
        for duty_id in list(eng.duties):
            if duty_id not in wanted:
                eng.remove_duty(duty_id)
        for duty_id, duty in wanted.items():
            try:
                if duty_id in eng.duties:
                    eng.update_duty(duty, today)
                else:
                    eng.add_duty(duty, today)
                    saved = self._saved_occurrences.get(duty_id)
                    if saved:
                        from .engine import Occurrence

                        eng.occurrences[duty_id] = Occurrence.from_dict(saved)
            except (ValueError, KeyError) as err:
                self.invalid.append(f"{duty_id}: {err}")
                eng.duties.pop(duty_id, None)
                eng.occurrences.pop(duty_id, None)

    def compute_signature(self) -> tuple:
        """Identity of the entity set; when it changes entities must be rebuilt."""
        subs = self.entry.subentries.values()
        return tuple(
            sorted(
                (s.subentry_type, s.data.get("id", ""))
                for s in subs
            )
        )

    def persist_owners(self, duty_id: str) -> None:
        """Write a duty's in-memory owners back to its subentry."""
        for sub in self.entry.subentries.values():
            if sub.subentry_type == SUBENTRY_DUTY and sub.data.get("id") == duty_id:
                data = {**sub.data, "owners": list(self.engine.duties[duty_id].owners)}
                self.hass.config_entries.async_update_subentry(self.entry, sub, data=data)
                return

    def schedule_save(self) -> None:
        self.store.async_delay_save(self._data_to_save, 1)

    def _data_to_save(self) -> dict[str, Any]:
        full = self.engine.to_dict()
        return {
            "occurrences": full["occurrences"],
            "history": full["history"],
            "biller_seen": full["biller_seen"],
            "biller_since": full["biller_since"],
        }

    async def async_save_now(self) -> None:
        await self.store.async_save(self._data_to_save())

    # ------------------------------------------------------------- ticking
    def read_conditions(self) -> dict[str, float]:
        out: dict[str, float] = {}
        mapping = parse_conditions(self.entry.options.get(CONF_CONDITIONS, ""))
        for key, entity_id in mapping.items():
            state = self.hass.states.get(entity_id)
            try:
                out[key] = float(state.state) if state else None  # type: ignore[assignment]
            except (TypeError, ValueError):
                out[key] = None  # type: ignore[assignment]
        return out

    async def async_tick(self, now: datetime | None = None) -> TickResult:
        now = now or dt_util.now()
        result = self.engine.tick(now, self.read_conditions())
        self.last_tick = now
        await self._dispatch(result, now)
        return result

    async def _dispatch(self, result: TickResult, now: datetime) -> None:
        for event in result.events:
            self.hass.bus.async_fire(
                f"{EVENT_PREFIX}{event.type}",
                {
                    "duty_id": event.duty_id,
                    "occurrence_id": event.occurrence_id,
                    "by": event.by,
                    "detail": event.detail,
                },
            )
        for event in result.events:
            if event.type != "completed" or event.method in ("", "auto"):
                continue
            duty = self.engine.duties.get(event.duty_id)
            if duty is not None and duty.biller:
                await self.bridge.async_press_mark_paid(duty.biller)
        for note in result.notifications:
            for person_id in note.recipients:
                self.queue.append((person_id, note))
        await self.async_flush_queue(now)
        self.schedule_save()
        self.notify_entities()

    async def async_flush_queue(self, now: datetime) -> None:
        held: list[tuple[str, Notification]] = []
        for person_id, note in self.queue:
            person = self.engine.people.get(person_id)
            if person is None:
                continue
            if in_quiet_hours(person, now) and note.kind != "escalation":
                held.append((person_id, note))
                continue
            await self._send(person, note)
        self.queue = held

    async def _send(self, person: Person, note: Notification) -> None:
        if not person.notify:
            return
        duty = self.engine.duties.get(note.duty_id)
        if duty is None:
            return
        occ = self.engine.occurrences.get(note.duty_id)
        lang = person.language
        by = self.engine.people[note.detail].name if note.kind == "not_mine" and note.detail in self.engine.people else note.detail
        title_text = duty.display_title(lang)
        if occ and occ.meta.get("amount") is not None:
            title_text += f" (${float(occ.meta['amount']):,.2f})"
        body = messages.text(
            note.kind,
            lang,
            title=title_text,
            due=occ.due.isoformat() if occ else "",
            by=by,
        )
        actions = [
            {
                "action": f"{ACTION_PREFIX}{verb}|{duty.id}|{person.id}",
                "title": messages.button(verb, lang),
            }
            for verb in ("done", "snooze", "not_mine")
        ]
        service = person.notify.split(".", 1)[-1]
        try:
            await self.hass.services.async_call(
                "notify",
                service,
                {
                    "title": messages.APP_TITLE.get(lang, "Homekeeper"),
                    "message": body,
                    "data": {"tag": f"homekeeper-{duty.id}", "actions": actions},
                },
                blocking=True,
            )
        except Exception:  # noqa: BLE001 - a failed push must never stop the tick
            _LOGGER.warning("Notification to %s failed", person.id, exc_info=True)
            self.invalid.append(f"notify_failed:{person.id}")

    # ---------------------------------------------------------- user actions
    async def async_handle_action(self, action: str) -> bool:
        """Handle a mobile-app notification button. Returns True if it was ours."""
        if not action.startswith(ACTION_PREFIX):
            return False
        try:
            _, verb, duty_id, person_id = action.split("|", 3)
        except ValueError:
            return False
        now = dt_util.now()
        if duty_id not in self.engine.duties or duty_id not in self.engine.occurrences:
            return True
        if verb == "done":
            result = self.engine.complete(duty_id, person_id, now, "button")
            await self._dispatch(result, now)
        elif verb == "snooze":
            from datetime import timedelta

            self.engine.snooze(duty_id, now.date() + timedelta(days=1), now.date())
            self.schedule_save()
            self.notify_entities()
        elif verb == "not_mine":
            note = self.engine.not_mine(duty_id, person_id, now.date())
            self.persist_owners(duty_id)
            await self._dispatch(TickResult(notifications=[note]), now)
        return True

    def notify_entities(self) -> None:
        async_dispatcher_send(
            self.hass, SIGNAL_UPDATE.format(entry_id=self.entry.entry_id)
        )

    def health_problems(self) -> list[str]:
        problems = list(self.engine.health(dt_util.now().date())) + list(self.invalid)
        if self.last_tick is None:
            problems.append("never_ticked")
        if self.engine.billers:
            if not self.bridge.mqtt_ready:
                problems.append("mqtt_unavailable")
            elif self.bridge.available is False:
                problems.append("billbot_offline")
        return problems


def get_runtime(hass: HomeAssistant, entry_id: str | None = None) -> Runtime:
    runtimes: dict[str, Runtime] = hass.data.get(DOMAIN, {})
    if entry_id:
        return runtimes[entry_id]
    return next(iter(runtimes.values()))
