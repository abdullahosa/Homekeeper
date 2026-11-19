"""A read-only snapshot of what needs doing, for the dashboard card. Pure Python."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from .core import Engine

_ORDER = {"overdue": 0, "due": 1, "upcoming": 2, "snoozed": 3}


def build_overview(engine: Engine, today: date, horizon_days: int = 14) -> dict[str, Any]:
    """Everything the card shows: who, what, how late. Dates are ISO strings and `days`
    is computed here, so the browser never needs the server's time zone."""
    horizon = today + timedelta(days=max(0, horizon_days))
    items: list[dict[str, Any]] = []
    for duty_id, occ in engine.occurrences.items():
        duty = engine.duties[duty_id]
        state = engine.state(duty_id, today)
        if state == "upcoming" and occ.due > horizon:
            continue
        if state == "idle":
            continue
        module = engine.modules.get(duty.module)
        login = engine.login_for(duty)
        items.append(
            {
                "duty_id": duty.id,
                "module": duty.module,
                "module_title": module.title if module else {},
                "title": duty.title,
                "owners": engine.effective_owners(duty),
                "state": state,
                "due": occ.due.isoformat(),
                "days": (occ.due - today).days,
                "snoozed_until": occ.snoozed_until.isoformat() if occ.snoozed_until else None,
                "amount": occ.meta.get("amount"),
                "how_to": duty.how_to,
                "done_by": duty.done_by,
                "biller": duty.biller,
                "login_url": login.login_url if login else "",
                "login_note": login.login_note if login else "",
            }
        )
    items.sort(key=lambda i: (_ORDER.get(i["state"], 9), i["due"], i["duty_id"]))
    return {
        "today": today.isoformat(),
        "items": items,
        "people": [
            {"id": p.id, "name": p.name, "language": p.language, "role": p.role}
            for p in engine.people.values()
        ],
        "modules": [{"id": m.id, "title": m.title} for m in engine.modules.values()],
        "counts": {
            "overdue": sum(1 for i in items if i["state"] == "overdue"),
            "due": sum(1 for i in items if i["state"] == "due"),
        },
    }
