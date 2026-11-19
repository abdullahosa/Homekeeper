"""A read-only snapshot of what needs doing, for the dashboard card. Pure Python."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from .core import Engine

_ORDER = {"overdue": 0, "due": 1, "upcoming": 2, "snoozed": 3}
_BILL_ORDER = {"overdue": 0, "due": 1, "autopay": 2, "paid": 3, "received": 4, "none": 5}


def _days(text: str | None, today: date) -> int | None:
    try:
        return (date.fromisoformat(str(text)) - today).days if text else None
    except ValueError:
        return None


def build_bills(engine: Engine, today: date) -> list[dict[str, Any]]:
    """One row per biller for the bills table: BillBot's latest status, amount and due
    date, plus the open pay duty (so the card can mark it paid). Bills first, most
    urgent first; income (rent) after."""
    rows: list[dict[str, Any]] = []
    for b in engine.billers.values():
        if not b.enabled:
            continue
        st = engine.bill_states.get(b.id, {})
        duty_id = None
        if b.kind == "income":
            status = "received" if st.get("status") == "paid" else "none"
            day = st.get("paid") or st.get("due_date")
            amount = st.get("paid_amount") if st.get("paid_amount") is not None else st.get("amount")
            module = engine.modules.get(b.module)
            owners = list(b.owners) or (list(module.owners) if module else [])
        else:
            status = st.get("status") if st.get("status") in _BILL_ORDER else "none"
            day, amount = st.get("due_date"), st.get("amount")
            duty = engine.duties.get(engine.biller_duty_id(b.id))
            occ = engine.occurrences.get(duty.id) if duty else None
            if duty is not None and occ is not None and engine.state(duty.id, today) != "idle":
                duty_id = duty.id  # open in Homekeeper: the card can mark it paid
                if status not in ("due", "overdue", "autopay"):
                    status = "due"
                day = occ.due.isoformat()
                if occ.meta.get("amount") is not None:
                    amount = occ.meta["amount"]
            if status == "due" and (_days(day, today) or 0) < 0:
                status = "overdue"
            owners = engine.effective_owners(duty) if duty else list(b.owners)
        rows.append(
            {
                "id": b.id,
                "name": b.name,
                "name_ar": b.name_ar,
                "icon": b.icon,
                "kind": b.kind,
                "module": b.module,
                "status": status,
                "amount": amount,
                "date": day,
                "days": _days(day, today),
                "autopay": bool(st.get("autopay")),
                "duty_id": duty_id,
                "owners": owners,
                "login_url": b.login_url,
                "login_note": b.login_note,
            }
        )
    rows.sort(key=lambda r: (r["kind"] == "income", _BILL_ORDER[r["status"]], r["date"] or "9999", r["name"]))
    return rows


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
                "what": occ.meta.get("what", ""),
                "event": occ.meta.get("event"),
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
        "bills": build_bills(engine, today),
        "counts": {
            "overdue": sum(1 for i in items if i["state"] == "overdue"),
            "due": sum(1 for i in items if i["state"] == "due"),
        },
    }
