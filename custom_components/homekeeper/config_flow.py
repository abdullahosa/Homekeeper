"""Config flow, options and the person / module / duty subentry flows."""

from __future__ import annotations

import re
from types import MappingProxyType
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    ConfigSubentry,
    ConfigSubentryFlow,
    OptionsFlow,
    SubentryFlowResult,
)
from homeassistant.core import callback
from homeassistant.helpers import selector
from homeassistant.util import slugify

from .const import (
    CONF_CONDITIONS,
    DOMAIN,
    SUBENTRY_BILLER,
    SUBENTRY_DUTY,
    SUBENTRY_MODULE,
    SUBENTRY_PERSON,
)
from .engine import Biller, Duty
from .engine import schedule as sch
from .engine.models import is_web_url
from .labels import entry_label

SLUG = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
SCHEDULE_CHOICES = list(sch.SCHEDULE_TYPES)
DONE_BY_CHOICES = ["button", "nfc", "voice", "auto"]


def _text(multiline: bool = False) -> selector.TextSelector:
    return selector.TextSelector(selector.TextSelectorConfig(multiline=multiline))


def _select(options: list[Any], multiple: bool = False) -> selector.SelectSelector:
    return selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=options,
            multiple=multiple,
            mode=selector.SelectSelectorMode.DROPDOWN,
        )
    )


def _csv(text: str | None) -> list[str]:
    return [p.strip() for p in (text or "").split(",") if p.strip()]


def _people(entry: ConfigEntry) -> list[selector.SelectOptionDict]:
    """People for an owner picker: the value is the id, the label is the name."""
    found = sorted(
        (s.data["name"], s.data["id"])
        for s in entry.subentries.values()
        if s.subentry_type == SUBENTRY_PERSON
    )
    return [selector.SelectOptionDict(value=i, label=n) for n, i in found]


def _new_person_id(name: str, taken: set[str]) -> str:
    return _new_id(name, taken, "person")


def _new_id(name: str, taken: set[str], fallback: str) -> str:
    """Make a short unique id from a name (Arabic names are transliterated)."""
    base = slugify(name)
    if base in ("", "unknown"):  # a name with nothing usable in it
        base = fallback
    ident, n = base, 2
    while ident in taken:
        ident, n = f"{base}_{n}", n + 1
    return ident


def _modules(entry: ConfigEntry) -> list[str]:
    return sorted(
        s.data["id"] for s in entry.subentries.values() if s.subentry_type == SUBENTRY_MODULE
    )


def _ids(entry: ConfigEntry, stype: str, skip: str | None = None) -> set[str]:
    return {
        s.data["id"]
        for s in entry.subentries.values()
        if s.subentry_type == stype and s.data["id"] != skip
    }


class HomekeeperConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")
        if user_input is not None:
            return self.async_create_entry(title="Homekeeper", data={})
        return self.async_show_form(step_id="user")

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return HomekeeperOptionsFlow()

    @classmethod
    @callback
    def async_get_supported_subentry_types(
        cls, config_entry: ConfigEntry
    ) -> dict[str, type[ConfigSubentryFlow]]:
        return {
            SUBENTRY_PERSON: PersonFlow,
            SUBENTRY_MODULE: ModuleFlow,
            SUBENTRY_DUTY: DutyFlow,
            SUBENTRY_BILLER: BillerFlow,
        }


class HomekeeperOptionsFlow(OptionsFlow):
    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        current = self.config_entry.options.get(CONF_CONDITIONS, "")
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {vol.Optional(CONF_CONDITIONS, default=current): _text(True)}
            ),
        )


class _BaseSubentryFlow(ConfigSubentryFlow):
    """Shared plumbing: new vs reconfigure."""

    def _existing(self) -> dict[str, Any]:
        if self.source == "reconfigure":
            return dict(self._get_reconfigure_subentry().data)
        return {}

    def _finish(self, title: str, data: dict[str, Any], ident: str) -> SubentryFlowResult:
        title = entry_label(self._get_entry(), self._subentry_type, data)
        if self.source == "reconfigure":
            return self.async_update_and_abort(
                self._get_entry(),
                self._get_reconfigure_subentry(),
                title=title,
                data=data,
            )
        return self.async_create_entry(
            title=title, data=data, unique_id=f"{self._subentry_type}:{ident}"
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        return await self.async_step_user(user_input)

    _first_module_name = "Home"

    async def async_step_first_module(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """No module exists yet: make one here, then carry on with the form."""
        entry = self._get_entry()
        if user_input is not None:
            name = user_input["module_name"].strip()
            ident = _new_id(name, _ids(entry, SUBENTRY_MODULE), "module")
            data = {"id": ident, "title": {"en": name}, "owners": user_input.get("owners", [])}
            self.hass.config_entries.async_add_subentry(
                entry,
                ConfigSubentry(
                    data=MappingProxyType(data),
                    subentry_type=SUBENTRY_MODULE,
                    title=name,
                    unique_id=f"{SUBENTRY_MODULE}:{ident}",
                ),
            )
            return await self.async_step_user()
        return self.async_show_form(
            step_id="first_module",
            data_schema=vol.Schema(
                {
                    vol.Required("module_name", default=self._first_module_name): _text(),
                    vol.Optional("owners", default=[]): _select(_people(entry), multiple=True),
                }
            ),
        )


class PersonFlow(_BaseSubentryFlow):
    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        entry = self._get_entry()
        old = self._existing()
        errors: dict[str, str] = {}
        if user_input is not None:
            ident = old.get("id") or _new_person_id(
                user_input["name"], _ids(entry, SUBENTRY_PERSON)
            )
            quiet = [q for q in (user_input.get("quiet_start"), user_input.get("quiet_end")) if q]
            if len(quiet) == 1:
                errors["quiet_start"] = "quiet_both"
            if not errors:
                data = {
                    "id": ident,
                    "name": user_input["name"],
                    "role": user_input["role"],
                    "language": user_input["language"],
                    "notify": user_input.get("notify") or None,
                    "ha_user": None,
                    "person_entity": user_input.get("person_entity") or None,
                    "quiet_hours": quiet or None,
                }
                return self._finish(user_input["name"], data, ident)
        quiet = old.get("quiet_hours") or ["", ""]
        fields: dict[Any, Any] = {}
        fields.update(
            {
                vol.Required("name", default=old.get("name", "")): _text(),
                vol.Required("role", default=old.get("role", "owner")): _select(
                    ["owner", "observer", "admin"]
                ),
                vol.Required("language", default=old.get("language", "en")): _select(["en", "ar"]),
                vol.Optional("notify", default=old.get("notify") or ""): _text(),
                vol.Optional(
                    "person_entity", description={"suggested_value": old.get("person_entity")}
                ): selector.EntitySelector(selector.EntitySelectorConfig(domain="person")),
                vol.Optional("quiet_start", default=quiet[0]): _text(),
                vol.Optional("quiet_end", default=quiet[1]): _text(),
            }
        )
        return self.async_show_form(
            step_id="user", data_schema=vol.Schema(fields), errors=errors
        )


class ModuleFlow(_BaseSubentryFlow):
    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        entry = self._get_entry()
        old = self._existing()
        errors: dict[str, str] = {}
        if user_input is not None:
            ident = old.get("id") or user_input["id"]
            if not SLUG.match(ident):
                errors["id"] = "bad_id"
            elif not old and ident in _ids(entry, SUBENTRY_MODULE):
                errors["id"] = "id_exists"
            if not errors:
                title = {"en": user_input["title_en"]}
                if user_input.get("title_ar"):
                    title["ar"] = user_input["title_ar"]
                data = {"id": ident, "title": title, "owners": user_input.get("owners", [])}
                return self._finish(user_input["title_en"], data, ident)
        fields: dict[Any, Any] = {}
        if not old:
            fields[vol.Required("id")] = _text()
        title = old.get("title", {})
        fields.update(
            {
                vol.Required("title_en", default=title.get("en", "")): _text(),
                vol.Optional("title_ar", default=title.get("ar", "")): _text(),
                vol.Optional("owners", default=old.get("owners", [])): _select(
                    _people(entry), multiple=True
                ),
            }
        )
        return self.async_show_form(
            step_id="user", data_schema=vol.Schema(fields), errors=errors
        )


def _schedule_fields(kind: str, old: dict[str, Any]) -> dict[Any, Any]:
    def d(key: str, default: Any = "") -> Any:
        value = old.get(key, default)
        return value if value is not None else default

    f: dict[Any, Any] = {}
    if kind == "interval":
        f[vol.Required("every", default=d("every"))] = _text()
        f[vol.Optional("anchor", default=d("anchor"))] = _text()
    elif kind == "after_completion":
        f[vol.Required("every", default=d("every"))] = _text()
        f[vol.Optional("first_due", default=d("first_due"))] = _text()
    elif kind == "day_of_month":
        f[vol.Required("days", default=",".join(str(x) for x in old.get("days", [])))] = _text()
        f[vol.Optional("next_business_day", default=bool(old.get("next_business_day")))] = (
            selector.BooleanSelector()
        )
    elif kind == "yearly_window":
        f[vol.Required("opens", default=d("opens"))] = _text()
        f[vol.Required("due", default=d("due"))] = _text()
    elif kind == "condition":
        f[vol.Optional("not_before", default=d("not_before"))] = _text()
        f[vol.Optional("not_after", default=d("not_after"))] = _text()
        f[vol.Optional("when", default=_fmt_cond(old.get("when")))] = _text()
        f[vol.Optional("open_early_when", default=_fmt_cond(old.get("open_early_when")))] = _text()
    elif kind == "signal":
        f[vol.Optional("completes", default=",".join(old.get("completes", [])))] = _text()
        f[vol.Optional("due_in", default=d("due_in", "0d"))] = _text()
    f[vol.Optional("opens_before", default=d("opens_before"))] = _text()
    return f


def _fmt_cond(spec: dict[str, Any] | None) -> str:
    return ", ".join(f"{k}:{v}" for k, v in (spec or {}).items() if not isinstance(v, dict))


def _parse_cond(text: str) -> dict[str, float]:
    out: dict[str, float] = {}
    for part in _csv(text):
        key, _, value = part.partition(":")
        out[key.strip()] = float(value)
    return out


def _build_schedule(kind: str, raw: dict[str, Any]) -> dict[str, Any]:
    sched: dict[str, Any] = {"type": kind}
    if kind in ("interval", "after_completion"):
        sched["every"] = raw["every"].strip()
        for key in ("anchor", "first_due"):
            if raw.get(key):
                sched[key] = raw[key].strip()
    elif kind == "day_of_month":
        sched["days"] = [int(x) for x in _csv(raw["days"])]
        if raw.get("next_business_day"):
            sched["next_business_day"] = True
    elif kind == "yearly_window":
        sched["opens"], sched["due"] = raw["opens"].strip(), raw["due"].strip()
    elif kind == "condition":
        for key in ("not_before", "not_after"):
            if raw.get(key):
                sched[key] = raw[key].strip()
        for key in ("when", "open_early_when"):
            if raw.get(key):
                sched[key] = _parse_cond(raw[key])
    elif kind == "signal":
        if raw.get("completes"):
            sched["completes"] = _csv(raw["completes"])
        sched["due_in"] = (raw.get("due_in") or "0d").strip()
    if raw.get("opens_before"):
        sched["opens_before"] = raw["opens_before"].strip()
    return sched


class DutyFlow(_BaseSubentryFlow):
    _first_module_name = "Home"

    def __init__(self) -> None:
        self._basic: dict[str, Any] = {}
        self._schedule: dict[str, Any] = {}

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        if not self._existing() and not _modules(self._get_entry()):
            return await self.async_step_first_module()
        entry = self._get_entry()
        old = self._existing()
        errors: dict[str, str] = {}
        if user_input is not None:
            ident = old.get("id") or user_input["id"]
            if not SLUG.match(ident):
                errors["id"] = "bad_id"
            elif not old and ident in _ids(entry, SUBENTRY_DUTY):
                errors["id"] = "id_exists"
            if not errors:
                self._basic = {**user_input, "id": ident}
                return await self.async_step_schedule()
        title = old.get("title", {})
        fields: dict[Any, Any] = {}
        if not old:
            fields[vol.Required("id")] = _text()
        fields.update(
            {
                vol.Required("module", default=old.get("module", vol.UNDEFINED)): _select(
                    _modules(entry)
                ),
                vol.Required("title_en", default=title.get("en", "")): _text(),
                vol.Optional("title_ar", default=title.get("ar", "")): _text(),
                vol.Optional("owners", default=old.get("owners", [])): _select(
                    _people(entry), multiple=True
                ),
                vol.Optional("observers", default=old.get("observers", [])): _select(
                    _people(entry), multiple=True
                ),
                vol.Required(
                    "schedule_type",
                    default=old.get("schedule", {}).get("type", "interval"),
                ): _select(SCHEDULE_CHOICES),
            }
        )
        return self.async_show_form(
            step_id="user", data_schema=vol.Schema(fields), errors=errors
        )

    async def async_step_schedule(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        kind = self._basic["schedule_type"]
        old = self._existing().get("schedule", {})
        if old.get("type") != kind:
            old = {}
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                sched = _build_schedule(kind, user_input)
                sch.validate(sched)
            except (ValueError, KeyError):
                errors["base"] = "bad_schedule"
            else:
                self._schedule = sched
                return await self.async_step_details()
        return self.async_show_form(
            step_id="schedule",
            data_schema=vol.Schema(_schedule_fields(kind, old)),
            errors=errors,
            description_placeholders={"type": kind},
        )

    async def async_step_details(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        old = self._existing()
        errors: dict[str, str] = {}
        if user_input is not None:
            remind: list[str] = []
            escalate: list[dict[str, Any]] = []
            season: list[int] | None = None
            for off in _csv(user_input.get("remind")):
                try:
                    sch.parse_duration(off)
                    remind.append(off)
                except ValueError:
                    errors["remind"] = "bad_duration"
            after = (user_input.get("escalate_after") or "").strip()
            if after:
                try:
                    sch.parse_duration(after)
                    escalate = [{"after": after, "notify": ["admin"]}]
                except ValueError:
                    errors["escalate_after"] = "bad_duration"
            try:
                season = [int(m) for m in _csv(user_input.get("season"))] or None
                if season and not all(1 <= m <= 12 for m in season):
                    raise ValueError("season")
            except ValueError:
                errors["season"] = "bad_months"
            if not errors:
                b = self._basic
                title = {"en": b["title_en"]}
                if b.get("title_ar"):
                    title["ar"] = b["title_ar"]
                data = Duty(
                    id=b["id"],
                    module=b["module"],
                    title=title,
                    schedule=self._schedule,
                    owners=b.get("owners", []),
                    observers=b.get("observers", []),
                    remind=remind,
                    escalate=escalate,
                    how_to=user_input.get("how_to", ""),
                    done_by=user_input.get("done_by") or ["button"],
                    nfc_tags=_csv(user_input.get("nfc_tags")),
                    enabled=user_input.get("enabled", True),
                    season=season,
                ).to_dict()
                return self._finish(b["title_en"], data, b["id"])
        esc = old.get("escalate") or []
        if user_input is not None:  # keep what was typed so a typo does not wipe the form
            shown = user_input
        else:
            shown = {
                "remind": ",".join(old.get("remind", [])),
                "escalate_after": esc[0]["after"] if esc else "",
                "how_to": old.get("how_to", ""),
                "season": ",".join(str(m) for m in old.get("season") or []),
                "nfc_tags": ",".join(old.get("nfc_tags", [])),
                "done_by": old.get("done_by", ["button", "nfc", "voice"]),
                "enabled": old.get("enabled", True),
            }
        fields = {
            vol.Optional("remind", default=shown.get("remind", "")): _text(),
            vol.Optional("escalate_after", default=shown.get("escalate_after", "")): _text(),
            vol.Optional("how_to", default=shown.get("how_to", "")): _text(True),
            vol.Optional("season", default=shown.get("season", "")): _text(),
            vol.Optional("nfc_tags", default=shown.get("nfc_tags", "")): _text(),
            vol.Optional("done_by", default=shown.get("done_by", ["button"])): _select(
                DONE_BY_CHOICES, multiple=True
            ),
            vol.Optional("enabled", default=shown.get("enabled", True)): selector.BooleanSelector(),
        }
        return self.async_show_form(
            step_id="details", data_schema=vol.Schema(fields), errors=errors
        )


class BillerFlow(_BaseSubentryFlow):
    """A sender BillBot reads: a bill to pay, or income (rent) to expect."""

    _first_module_name = "Bills"

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        if not self._existing() and not _modules(self._get_entry()):
            return await self.async_step_first_module()
        entry = self._get_entry()
        old = self._existing()
        errors: dict[str, str] = {}
        if user_input is not None:
            ident = old.get("id") or user_input["id"]
            if not SLUG.match(ident):
                errors["id"] = "bad_id"
            elif not old and ident in _ids(entry, SUBENTRY_BILLER):
                errors["id"] = "id_exists"
            try:
                remind = _csv(user_input.get("remind"))
                for off in remind:
                    sch.parse_duration(off)
                escalate = []
                if user_input.get("escalate_after"):
                    sch.parse_duration(user_input["escalate_after"])
                    escalate = [{"after": user_input["escalate_after"], "notify": ["admin"]}]
                cadence = int(user_input["cadence_days"]) if user_input.get("cadence_days") else None
                grace = int(user_input.get("grace_days") or 5)
            except ValueError:
                errors["base"] = "bad_details"
            login_url = (user_input.get("login_url") or "").strip()
            if login_url and not is_web_url(login_url):
                errors["login_url"] = "bad_url"
            if not errors:
                data = Biller(
                    id=ident,
                    name=user_input["name"].strip(),
                    kind=user_input["kind"],
                    module=user_input["module"],
                    sender_domains=[d.lower() for d in _csv(user_input.get("sender_domains"))],
                    owners=user_input.get("owners", []),
                    observers=user_input.get("observers", []),
                    cadence_days=cadence,
                    grace_days=grace,
                    completes=_csv(user_input.get("completes")),
                    remind=remind,
                    escalate=escalate,
                    enabled=user_input.get("enabled", True),
                    login_url=login_url,
                    login_note=(user_input.get("login_note") or "").strip(),
                ).to_dict()
                return self._finish(data["name"], data, ident)
        esc = old.get("escalate") or []
        typed = user_input or {}

        def cur(key: str, saved: Any) -> Any:
            """What to show: what was just typed (after an error), else the saved value."""
            return typed[key] if key in typed else saved

        fields: dict[Any, Any] = {}
        if not old:
            fields[vol.Required("id", default=typed.get("id", ""))] = _text()
        fields.update(
            {
                vol.Required("name", default=cur("name", old.get("name", ""))): _text(),
                vol.Required("kind", default=cur("kind", old.get("kind", "bill"))): _select(
                    ["bill", "income"]
                ),
                vol.Required(
                    "module",
                    default=cur(
                        "module",
                        old.get("module") or ("bills" if "bills" in _modules(entry) else _modules(entry)[0]),
                    ),
                ): _select(_modules(entry)),
                vol.Optional(
                    "sender_domains", default=cur("sender_domains", ",".join(old.get("sender_domains", [])))
                ): _text(),
                vol.Optional("owners", default=cur("owners", old.get("owners", []))): _select(
                    _people(entry), multiple=True
                ),
                vol.Optional("observers", default=cur("observers", old.get("observers", []))): _select(
                    _people(entry), multiple=True
                ),
                vol.Optional(
                    "cadence_days", default=cur("cadence_days", str(old.get("cadence_days") or ""))
                ): _text(),
                vol.Optional("grace_days", default=cur("grace_days", str(old.get("grace_days", 5)))): _text(),
                vol.Optional("completes", default=cur("completes", ",".join(old.get("completes", [])))): _text(),
                vol.Optional(
                    "remind", default=cur("remind", ",".join(old.get("remind", ["-3d", "0d"])))
                ): _text(),
                vol.Optional(
                    "escalate_after", default=cur("escalate_after", esc[0]["after"] if esc else "2d")
                ): _text(),
                vol.Optional("login_url", default=cur("login_url", old.get("login_url", ""))): _text(),
                vol.Optional("login_note", default=cur("login_note", old.get("login_note", ""))): _text(True),
                vol.Optional("enabled", default=cur("enabled", old.get("enabled", True))): selector.BooleanSelector(),
            }
        )
        return self.async_show_form(
            step_id="user", data_schema=vol.Schema(fields), errors=errors
        )
