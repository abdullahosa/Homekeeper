"""What is set up and what still needs setting up, for the Homekeeper setup panel.

Pure Python, like the rest of the engine. The panel groups these four sections itself,
because Home Assistant's own integration page can only show one flat, alphabetical list.
"""

from __future__ import annotations

from typing import Any

from .core import Engine

# Issue codes are stable; the panel turns them into sentences.
SECTIONS = ("people", "modules", "duties", "billers")


def describe_schedule(sched: dict[str, Any]) -> str:
    kind = sched.get("type")
    if kind == "interval":
        return f"Every {sched.get('every', '?')}"
    if kind == "after_completion":
        return f"{sched.get('every', '?')} after it was last done"
    if kind == "day_of_month":
        days = ", ".join(str(d) for d in sched.get("days", []))
        return f"Day {days} of each month"
    if kind == "yearly_window":
        return f"Yearly, {sched.get('opens', '?')} to {sched.get('due', '?')}"
    if kind == "condition":
        return "When its condition is met"
    if kind == "signal":
        return "When a machine signals it"
    if kind == "calendar":
        words = ", ".join(sched.get("match") or [])
        lead = sched.get("lead", "1d")
        return f"{lead} before each {words + ' ' if words else ''}event in {sched.get('calendar', '?')}"
    return "No schedule"


def _name(titles: dict[str, str], fallback: str) -> str:
    return titles.get("en") or next(iter(titles.values()), "") or fallback


def build_setup(engine: Engine) -> dict[str, Any]:
    """Four sections of rows, each with the problems that make it incomplete."""
    people = []
    for p in engine.people.values():
        issues = [] if p.notify else ["no_notify"]
        people.append(
            {
                "id": p.id,
                "title": p.name,
                "detail": f"{p.role.capitalize()} · {'Arabic' if p.language == 'ar' else 'English'}",
                "issues": issues,
            }
        )

    modules = []
    for m in engine.modules.values():
        mine = [d for d in engine.duties.values() if d.module == m.id and not d.biller]
        billers = [b for b in engine.billers.values() if b.module == m.id]
        issues = []
        if not [o for o in m.owners if o in engine.people]:
            issues.append("no_owners")
        if not mine and not billers:
            issues.append("no_duties")
        owners = ", ".join(engine.people[o].name for o in m.owners if o in engine.people)
        modules.append(
            {
                "id": m.id,
                "title": _name(m.title, m.id),
                "detail": f"{len(mine) + len(billers)} item(s) · Owners: {owners or 'none'}",
                "issues": issues,
            }
        )

    duties = []
    for d in engine.duties.values():
        if d.biller:  # shown under Billers
            continue
        module = engine.modules.get(d.module)
        issues = [] if engine.effective_owners(d) else ["no_owner"] if module else ["no_module"]
        duties.append(
            {
                "id": d.id,
                "title": d.display_title(),
                "detail": f"{_name(module.title, module.id) if module else d.module} · "
                f"{describe_schedule(d.schedule)}",
                "issues": issues,
            }
        )

    billers = []
    for b in engine.billers.values():
        module = engine.modules.get(b.module)
        issues = []
        if module is None:
            issues.append("no_module")
        elif not [o for o in (b.owners or module.owners) if o in engine.people]:
            issues.append("no_owner")
        if b.kind == "income" and not b.completes:
            issues.append("income_completes_nothing")
        billers.append(
            {
                "id": b.id,
                "title": b.name,
                "detail": f"{'Income' if b.kind == 'income' else 'Bill'} · "
                f"{_name(module.title, module.id) if module else b.module}",
                "issues": issues,
            }
        )

    sections = {"people": people, "modules": modules, "duties": duties, "billers": billers}
    return {
        "sections": [{"kind": kind, "items": sections[kind]} for kind in SECTIONS],
        "todo_count": sum(1 for rows in sections.values() for r in rows if r["issues"]),
    }
