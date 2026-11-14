"""Homekeeper services."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigSubentry
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.util import dt as dt_util

from .const import DOMAIN, SUBENTRY_DUTY, SUBENTRY_MODULE
from .engine import Engine
from .engine.packs import export_pack, import_pack, load_pack_text
from .runtime import Runtime, get_runtime

COMPLETE = vol.Schema(
    {
        vol.Required("duty_id"): cv.string,
        vol.Optional("by"): cv.string,
        vol.Optional("method", default="button"): vol.In(
            ["button", "nfc", "voice", "auto"]
        ),
        vol.Optional("note", default=""): cv.string,
    }
)
SNOOZE = vol.Schema(
    {
        vol.Required("duty_id"): cv.string,
        vol.Optional("hours"): vol.All(vol.Coerce(int), vol.Range(min=1, max=24 * 60)),
        vol.Optional("until"): cv.date,
    }
)
SKIP = vol.Schema(
    {
        vol.Required("duty_id"): cv.string,
        vol.Required("reason"): cv.string,
        vol.Optional("by"): cv.string,
    }
)
REASSIGN = vol.Schema(
    {vol.Required("duty_id"): cv.string, vol.Required("owners"): vol.All(cv.ensure_list, [cv.string])}
)
SIGNAL = vol.Schema({vol.Required("duty_id"): cv.string})
IMPORT = vol.Schema(
    {
        vol.Optional("pack"): cv.string,
        vol.Optional("path"): cv.string,
        vol.Optional("overwrite", default=False): cv.boolean,
        vol.Optional("dry_run", default=False): cv.boolean,
    }
)
EXPORT = vol.Schema({vol.Required("module"): cv.string})


def _known(runtime: Runtime, duty_id: str) -> None:
    if duty_id not in runtime.engine.duties:
        raise ServiceValidationError(f"Unknown duty: {duty_id}")


def async_register_services(hass: HomeAssistant) -> None:
    if hass.services.has_service(DOMAIN, "complete"):
        return

    async def complete(call: ServiceCall) -> None:
        rt = get_runtime(hass)
        _known(rt, call.data["duty_id"])
        try:
            result = rt.engine.complete(
                call.data["duty_id"],
                call.data.get("by"),
                dt_util.now(),
                call.data["method"],
                call.data["note"],
            )
        except ValueError as err:
            raise ServiceValidationError(str(err)) from err
        await rt._dispatch(result, dt_util.now())

    async def snooze(call: ServiceCall) -> None:
        rt = get_runtime(hass)
        _known(rt, call.data["duty_id"])
        now = dt_util.now()
        if "until" in call.data:
            until = call.data["until"]
        else:
            until = (now + timedelta(hours=call.data.get("hours", 24))).date()
        try:
            rt.engine.snooze(call.data["duty_id"], until, now.date())
        except ValueError as err:
            raise ServiceValidationError(str(err)) from err
        rt.schedule_save()
        rt.notify_entities()

    async def skip(call: ServiceCall) -> None:
        rt = get_runtime(hass)
        _known(rt, call.data["duty_id"])
        try:
            result = rt.engine.skip(
                call.data["duty_id"], call.data.get("by"), dt_util.now(), call.data["reason"]
            )
        except ValueError as err:
            raise ServiceValidationError(str(err)) from err
        await rt._dispatch(result, dt_util.now())

    async def signal(call: ServiceCall) -> None:
        rt = get_runtime(hass)
        _known(rt, call.data["duty_id"])
        try:
            result = rt.engine.signal(call.data["duty_id"], dt_util.now())
        except ValueError as err:
            raise ServiceValidationError(str(err)) from err
        await rt._dispatch(result, dt_util.now())

    async def reassign(call: ServiceCall) -> None:
        rt = get_runtime(hass)
        _known(rt, call.data["duty_id"])
        unknown = [o for o in call.data["owners"] if o not in rt.engine.people]
        if unknown:
            raise ServiceValidationError(f"Unknown people: {', '.join(unknown)}")
        rt.engine.duties[call.data["duty_id"]].owners = list(call.data["owners"])
        rt.persist_owners(call.data["duty_id"])

    async def import_pack_service(call: ServiceCall) -> dict[str, Any]:
        rt = get_runtime(hass)
        text = call.data.get("pack")
        if not text and call.data.get("path"):
            path = call.data["path"]
            if not hass.config.is_allowed_path(path):
                raise ServiceValidationError(f"Path not allowed: {path}")
            text = await hass.async_add_executor_job(_read, path)
        if not text:
            raise ServiceValidationError("Give either `pack` (YAML text) or `path`")
        try:
            data = load_pack_text(text)
        except Exception as err:  # noqa: BLE001
            raise ServiceValidationError(f"Bad pack: {err}") from err
        # import_pack validates on its own copy and only applies to `trial` when
        # everything is valid and this is not a dry run.
        trial = Engine.from_dict(rt.engine.to_dict())
        today = dt_util.now().date()
        report = import_pack(
            trial,
            data,
            today,
            overwrite=call.data["overwrite"],
            dry_run=call.data["dry_run"],
        )
        out = {
            "created": report.created,
            "updated": report.updated,
            "unchanged": report.unchanged,
            "errors": report.errors,
            "applied": False,
        }
        if report.errors or call.data["dry_run"]:
            return out
        _apply_report(hass, rt, trial, report)
        out["applied"] = True
        return out

    async def export_pack_service(call: ServiceCall) -> dict[str, Any]:
        rt = get_runtime(hass)
        if call.data["module"] not in rt.engine.modules:
            raise ServiceValidationError(f"Unknown module: {call.data['module']}")
        return export_pack(rt.engine, call.data["module"])

    hass.services.async_register(DOMAIN, "complete", complete, COMPLETE)
    hass.services.async_register(DOMAIN, "snooze", snooze, SNOOZE)
    hass.services.async_register(DOMAIN, "skip", skip, SKIP)
    hass.services.async_register(DOMAIN, "signal", signal, SIGNAL)
    hass.services.async_register(DOMAIN, "reassign", reassign, REASSIGN)
    hass.services.async_register(
        DOMAIN, "import_pack", import_pack_service, IMPORT, supports_response=SupportsResponse.OPTIONAL
    )
    hass.services.async_register(
        DOMAIN, "export_pack", export_pack_service, EXPORT, supports_response=SupportsResponse.ONLY
    )


def _read(path: str) -> str:
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def _apply_report(hass: HomeAssistant, rt: Runtime, trial: Engine, report) -> None:
    """Turn a validated trial import into config subentries (one reload at the end)."""
    entry = rt.entry
    rt.importing = True
    try:
        existing = {
            (s.subentry_type, s.data.get("id")): s for s in entry.subentries.values()
        }
        for item in report.created + report.updated:
            kind, _, ident = item.partition(":")
            if kind == "module":
                data = trial.modules[ident].to_dict()
                stype = SUBENTRY_MODULE
                title = data["title"].get("en") or ident
            elif kind == "duty":
                data = trial.duties[ident].to_dict()
                stype = SUBENTRY_DUTY
                title = trial.duties[ident].display_title("en")
            else:
                continue  # billers live in engine state for now
            current = existing.get((stype, ident))
            if current is not None:
                hass.config_entries.async_update_subentry(
                    entry, current, data=data, title=title
                )
            else:
                hass.config_entries.async_add_subentry(
                    entry,
                    ConfigSubentry(
                        data=data,
                        subentry_type=stype,
                        title=title,
                        unique_id=f"{stype}:{ident}",
                    ),
                )
        rt.engine.billers = dict(trial.billers)
    except Exception as err:
        raise HomeAssistantError(f"Import failed: {err}") from err
    finally:
        rt.importing = False
    hass.async_create_task(hass.config_entries.async_reload(entry.entry_id))
