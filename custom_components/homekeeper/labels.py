"""Names for the rows on the integration page.

Home Assistant lists subentries alphabetically by title, so each title starts with its
kind ("Person · Dad", "Module · Lawn", "Duty · Lawn · Mow the lawn", "Biller · Duke
Energy"). That groups the list by kind, and duties by module, without any extra screens.
"""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import SUBENTRY_BILLER, SUBENTRY_DUTY, SUBENTRY_MODULE, SUBENTRY_PERSON

_KIND = {
    SUBENTRY_PERSON: "Person",
    SUBENTRY_MODULE: "Module",
    SUBENTRY_DUTY: "Duty",
    SUBENTRY_BILLER: "Biller",
}


def _module_names(entry: ConfigEntry) -> dict[str, str]:
    return {
        s.data["id"]: (s.data.get("title") or {}).get("en") or s.data["id"]
        for s in entry.subentries.values()
        if s.subentry_type == SUBENTRY_MODULE
    }


def label_for(
    stype: str, data: dict[str, Any], modules: dict[str, str] | None = None
) -> str:
    kind = _KIND.get(stype, stype.title())
    if stype == SUBENTRY_PERSON:
        return f"{kind} · {data.get('name') or data.get('id')}"
    if stype == SUBENTRY_MODULE:
        return f"{kind} · {(data.get('title') or {}).get('en') or data.get('id')}"
    if stype == SUBENTRY_BILLER:
        return f"{kind} · {data.get('name') or data.get('id')}"
    name = (data.get("title") or {}).get("en") or data.get("id")
    module = (modules or {}).get(data.get("module", ""), data.get("module", ""))
    return f"{kind} · {module} · {name}" if module else f"{kind} · {name}"


def entry_label(entry: ConfigEntry, stype: str, data: dict[str, Any]) -> str:
    return label_for(stype, data, _module_names(entry))


def relabel(hass: HomeAssistant, entry: ConfigEntry) -> int:
    """Give every existing row its tidy title. Returns how many changed."""
    modules = _module_names(entry)
    changed = 0
    for sub in list(entry.subentries.values()):
        want = label_for(sub.subentry_type, dict(sub.data), modules)
        if sub.title != want:
            hass.config_entries.async_update_subentry(entry, sub, title=want)
            changed += 1
    return changed
