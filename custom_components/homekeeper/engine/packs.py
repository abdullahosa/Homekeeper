"""Starter-pack import/export. Idempotent and keyed by id."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from .core import Engine
from .models import Duty, Module


@dataclass
class PackReport:
    created: list[str] = field(default_factory=list)
    updated: list[str] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def load_pack_text(text: str) -> dict[str, Any]:
    import yaml  # HA ships PyYAML

    data = yaml.safe_load(text)
    if not isinstance(data, dict) or "module" not in data:
        raise ValueError("pack must be a mapping with a `module` key")
    return data


def import_pack(
    engine: Engine,
    pack: dict[str, Any],
    today: date,
    *,
    overwrite: bool = False,
    dry_run: bool = False,
) -> PackReport:
    """Create the pack's module, duties and billers. Existing ids are kept as-is
    unless overwrite=True, so a re-import never clobbers a family's edits."""
    # Validate on a throwaway copy first, so a bad pack changes nothing.
    report = PackReport()
    _apply(Engine.from_dict(engine.to_dict()), pack, today, overwrite, report)
    if report.errors or dry_run:
        return report
    _apply(engine, pack, today, overwrite, PackReport())
    return report


def _apply(
    engine: Engine, pack: dict[str, Any], today: date, overwrite: bool, report: PackReport
) -> None:
    mid = pack["module"]
    if mid not in engine.modules:
        engine.add_module(
            Module(mid, dict(pack.get("title", {})), list(pack.get("owners", [])))
        )
        report.created.append(f"module:{mid}")
    else:
        report.unchanged.append(f"module:{mid}")
    for biller in pack.get("billers", []):
        key = f"biller:{biller['id']}"
        record = {**biller, "module": mid}
        if biller["id"] not in engine.billers:
            engine.billers[biller["id"]] = record
            report.created.append(key)
        elif overwrite and engine.billers[biller["id"]] != record:
            engine.billers[biller["id"]] = record
            report.updated.append(key)
        else:
            report.unchanged.append(key)
    for raw in pack.get("duties", []):
        key = f"duty:{raw.get('id')}"
        try:
            duty = Duty.from_dict({**raw, "module": mid})
            if duty.id not in engine.duties:
                engine.add_duty(duty, today)
                report.created.append(key)
            elif overwrite and engine.duties[duty.id].to_dict() != duty.to_dict():
                engine.update_duty(duty, today)
                report.updated.append(key)
            else:
                report.unchanged.append(key)
        except (ValueError, KeyError, TypeError) as err:
            report.errors.append(f"{key}: {err}")


def export_pack(engine: Engine, module_id: str) -> dict[str, Any]:
    module = engine.modules[module_id]
    duties = []
    for duty in engine.duties.values():
        if duty.module != module_id:
            continue
        item = duty.to_dict()
        item.pop("module")
        duties.append(item)
    return {
        "module": module_id,
        "title": module.title,
        "owners": module.owners,
        "billers": [
            {k: v for k, v in b.items() if k != "module"}
            for b in engine.billers.values()
            if b.get("module") == module_id
        ],
        "duties": duties,
    }
