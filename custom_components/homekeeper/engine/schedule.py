"""Schedule arithmetic. Pure functions on dates; no state."""

from __future__ import annotations

import calendar
import re
from datetime import date, timedelta
from typing import Any

SCHEDULE_TYPES = (
    "interval",
    "after_completion",
    "day_of_month",
    "yearly_window",
    "condition",
    "signal",
    "calendar",
)
_HHMM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")

_DUR = re.compile(r"^([+-]?)(\d+)([dwmy])$")


def parse_duration(text: str) -> tuple[int, str]:
    """'3d' -> (3, 'd'); '-7d' -> (-7, 'd'). Units: d, w, m (months), y."""
    match = _DUR.match(str(text).strip())
    if not match:
        raise ValueError(f"bad duration: {text!r}")
    sign, num, unit = match.groups()
    value = int(num)
    return (-value if sign == "-" else value), unit


def add_months(day: date, months: int) -> date:
    index = day.year * 12 + (day.month - 1) + months
    year, month = divmod(index, 12)
    month += 1
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


def add_duration(day: date, text: str, sign: int = 1) -> date:
    value, unit = parse_duration(text)
    value *= sign
    if unit == "d":
        return day + timedelta(days=value)
    if unit == "w":
        return day + timedelta(weeks=value)
    if unit == "m":
        return add_months(day, value)
    return add_months(day, value * 12)


def _md(text: str, year: int) -> date:
    month, dom = (int(p) for p in text.split("-"))
    return date(year, month, min(dom, calendar.monthrange(year, month)[1]))


def next_business_day(day: date) -> date:
    while day.weekday() >= 5:
        day += timedelta(days=1)
    return day


def validate(sched: dict[str, Any]) -> None:
    kind = sched.get("type")
    if kind not in SCHEDULE_TYPES:
        raise ValueError(f"unknown schedule type: {kind!r}")
    if kind in ("interval", "after_completion"):
        parse_duration(sched.get("every", ""))
    if kind == "day_of_month":
        days = sched.get("days")
        if not days or not all(isinstance(d, int) and 1 <= d <= 31 for d in days):
            raise ValueError("day_of_month needs days: [1..31]")
    if kind == "yearly_window":
        _md(sched["opens"], 2001)
        _md(sched["due"], 2001)
    if kind == "condition":
        for key in ("not_before", "not_after"):
            if key in sched:
                _md(sched[key], 2001)
    if kind == "calendar":
        if not str(sched.get("calendar", "")).startswith("calendar."):
            raise ValueError("calendar needs a calendar entity, e.g. calendar.cartology")
        value, unit = parse_duration(sched.get("lead", "1d"))
        if unit not in ("d", "w") or value < 0:
            raise ValueError("lead must be days or weeks before the event, e.g. 1d")
        if sched.get("notify_at") and not _HHMM.match(str(sched["notify_at"])):
            raise ValueError("notify_at must be HH:MM")
        if not isinstance(sched.get("match", []), list):
            raise ValueError("match must be a list of words")
    for key in ("open_early_when", "when"):
        if key in sched and not isinstance(sched[key], dict):
            raise ValueError(f"{key} must be a mapping")
    if "opens_before" in sched:
        parse_duration(sched["opens_before"])


def _yearly(sched: dict[str, Any], year: int) -> tuple[date | None, date]:
    """Window (opens, due) for the given year. opens is None if `when` gates it."""
    if sched["type"] == "yearly_window":
        opens = _md(sched["opens"], year)
        due = _md(sched["due"], year)
        if due < opens:
            due = _md(sched["due"], year + 1)
        return opens, due
    opens = _md(sched.get("not_before", "01-01"), year)
    due = _md(sched.get("not_after", "12-31"), year)
    if due < opens:
        due = _md(sched.get("not_after", "12-31"), year + 1)
    return (None if sched.get("when") else opens), due


def _window_from_due(sched: dict[str, Any], due: date) -> tuple[date, date]:
    lead = sched.get("opens_before")
    return (add_duration(due, lead, -1) if lead else due), due


def _day_of_month_candidates(sched: dict[str, Any], start: date, count: int = 3) -> list[date]:
    out: list[date] = []
    month_anchor = date(start.year, start.month, 1)
    for step in range(0, 14):
        month = add_months(month_anchor, step)
        last = calendar.monthrange(month.year, month.month)[1]
        for dom in sorted(sched["days"]):
            out.append(date(month.year, month.month, min(dom, last)))
        if len(out) >= count + len(sched["days"]):
            break
    return sorted(set(out))


def first_window(sched: dict[str, Any], today: date) -> tuple[date | None, date] | None:
    """Window for a newly created duty, or None for signal- and calendar-driven duties
    (those open when the signal or calendar event arrives)."""
    kind = sched["type"]
    if kind in ("signal", "calendar"):
        return None
    if kind == "interval":
        every = sched["every"]
        anchor = date.fromisoformat(sched["anchor"]) if sched.get("anchor") else today
        due = anchor
        while due < today:
            due = add_duration(due, every)
        return _window_from_due(sched, due)
    if kind == "after_completion":
        due = (
            date.fromisoformat(sched["first_due"])
            if sched.get("first_due")
            else add_duration(today, sched["every"])
        )
        return _window_from_due(sched, due)
    if kind == "day_of_month":
        for cand in _day_of_month_candidates(sched, today):
            due = next_business_day(cand) if sched.get("next_business_day") else cand
            if due >= today:
                return _window_from_due(sched, due)
        raise ValueError("no day_of_month candidate found")
    # yearly_window / condition
    for year in (today.year - 1, today.year, today.year + 1):
        opens, due = _yearly(sched, year)
        if due >= today:
            return opens, due
    raise ValueError("no window found")


def next_window(
    sched: dict[str, Any], prev_due: date, done_on: date
) -> tuple[date | None, date] | None:
    """Window that follows an occurrence that was completed or skipped."""
    kind = sched["type"]
    if kind in ("signal", "calendar"):
        return None
    if kind == "interval":
        due = add_duration(prev_due, sched["every"])
        while due <= done_on:
            due = add_duration(due, sched["every"])
        return _window_from_due(sched, due)
    if kind == "after_completion":
        return _window_from_due(sched, add_duration(done_on, sched["every"]))
    if kind == "day_of_month":
        for cand in _day_of_month_candidates(sched, prev_due, count=4):
            if cand <= prev_due or cand < done_on:
                continue
            due = next_business_day(cand) if sched.get("next_business_day") else cand
            if due > prev_due:
                return _window_from_due(sched, due)
        raise ValueError("no day_of_month candidate found")
    for year in (prev_due.year - 1, prev_due.year, prev_due.year + 1, prev_due.year + 2):
        opens, due = _yearly(sched, year)
        if due > prev_due and due >= done_on:
            return opens, due
    raise ValueError("no window found")


def in_season(day: date, season: list[int] | None) -> bool:
    return not season or day.month in season


def shift_into_season(
    window: tuple[date | None, date], season: list[int] | None
) -> tuple[date | None, date]:
    """If the due date is out of season, move to the first day of the next in-season month."""
    opens, due = window
    if in_season(due, season):
        return window
    probe = date(due.year, due.month, 1)
    for _ in range(13):
        probe = add_months(probe, 1)
        if probe.month in season:  # type: ignore[operator]
            return probe, probe
    return window


def condition_met(spec: dict[str, Any], conditions: dict[str, float]) -> bool:
    """spec: {key: number} means value >= number; {key: {gte|lte|gt|lt: n}} also allowed."""
    if not spec:
        return False
    for key, rule in spec.items():
        if key not in conditions or conditions[key] is None:
            return False
        value = conditions[key]
        if isinstance(rule, dict):
            checks = {
                "gte": lambda a, b: a >= b,
                "lte": lambda a, b: a <= b,
                "gt": lambda a, b: a > b,
                "lt": lambda a, b: a < b,
            }
            for op, bound in rule.items():
                if op not in checks or not checks[op](value, bound):
                    return False
        elif value < rule:
            return False
    return True


def window_start(sched: dict[str, Any], due: date) -> date:
    """Start of the calendar window that ends at `due` (for `when`-gated conditions)."""
    start = _md(sched.get("not_before", "01-01"), due.year)
    if start > due:
        start = _md(sched.get("not_before", "01-01"), due.year - 1)
    return start
