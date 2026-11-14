"""Homekeeper engine: duties, occurrences, reminders, escalation, history."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from . import schedule as sch
from .models import Duty, HistoryEntry, Module, Occurrence, Person

DONE_METHODS = ("button", "nfc", "voice", "auto")
DEFAULT_EARLY_DAYS = 30


@dataclass
class Event:
    type: str  # due | overdue | completed | skipped
    duty_id: str
    occurrence_id: str
    by: str | None = None
    detail: str = ""


@dataclass
class Notification:
    kind: str  # opened | reminder | overdue | escalation | not_mine
    duty_id: str
    occurrence_id: str
    recipients: list[str]
    detail: str = ""


@dataclass
class TickResult:
    events: list[Event] = field(default_factory=list)
    notifications: list[Notification] = field(default_factory=list)


class Engine:
    def __init__(self) -> None:
        self.people: dict[str, Person] = {}
        self.modules: dict[str, Module] = {}
        self.duties: dict[str, Duty] = {}
        self.occurrences: dict[str, Occurrence] = {}  # one open occurrence per duty
        self.history: list[HistoryEntry] = []
        self.billers: dict[str, dict[str, Any]] = {}

    # ---------------------------------------------------------------- setup
    def add_person(self, person: Person) -> None:
        self.people[person.id] = person

    def add_module(self, module: Module) -> None:
        self.modules[module.id] = module

    def add_duty(self, duty: Duty, today: date) -> Occurrence | None:
        if duty.id in self.duties:
            raise ValueError(f"duty exists: {duty.id}")
        self._check_duty(duty)
        self.duties[duty.id] = duty
        return self._start(duty, today)

    def update_duty(self, duty: Duty, today: date) -> Occurrence | None:
        """Replace a duty. The open occurrence is kept when the schedule is unchanged."""
        old = self.duties.get(duty.id)
        if old is None:
            raise KeyError(duty.id)
        self._check_duty(duty)
        self.duties[duty.id] = duty
        if old.schedule != duty.schedule or old.season != duty.season:
            self.occurrences.pop(duty.id, None)
            return self._start(duty, today)
        return self.occurrences.get(duty.id)

    def remove_duty(self, duty_id: str) -> None:
        self.duties.pop(duty_id, None)
        self.occurrences.pop(duty_id, None)

    def set_enabled(self, duty_id: str, enabled: bool, today: date) -> None:
        duty = self.duties[duty_id]
        duty.enabled = enabled
        if not enabled:
            self.occurrences.pop(duty_id, None)
        elif duty_id not in self.occurrences:
            self._start(duty, today)

    def _check_duty(self, duty: Duty) -> None:
        if duty.module not in self.modules:
            raise ValueError(f"unknown module: {duty.module}")
        sch.validate(duty.schedule)
        for off in duty.remind:
            sch.parse_duration(off)
        for esc in duty.escalate:
            sch.parse_duration(esc["after"])
        for method in duty.done_by:
            if method not in DONE_METHODS:
                raise ValueError(f"unknown done_by method: {method}")

    def _start(self, duty: Duty, today: date) -> Occurrence | None:
        if not duty.enabled:
            return None
        window = sch.first_window(duty.schedule, today)
        return self._spawn(duty, window)

    def _spawn(
        self, duty: Duty, window: tuple[date | None, date] | None
    ) -> Occurrence | None:
        if window is None:
            return None
        window = sch.shift_into_season(window, duty.season)
        opens, due = window
        occ = Occurrence(duty_id=duty.id, due=due, opens=opens)
        self.occurrences[duty.id] = occ
        return occ

    # ------------------------------------------------------------ lookups
    def effective_owners(self, duty: Duty) -> list[str]:
        owners = duty.owners or self.modules[duty.module].owners
        return [o for o in owners if o in self.people]

    def _admins(self) -> list[str]:
        return [p.id for p in self.people.values() if p.role == "admin"]

    def _resolve(self, duty: Duty, tokens: list[str]) -> list[str]:
        out: list[str] = []
        for token in tokens:
            if token == "owners":
                out += self.effective_owners(duty)
            elif token == "observers":
                out += [o for o in duty.observers if o in self.people] + self._admins()
            elif token in ("admin", "admins"):
                out += self._admins()
            elif token in self.people:
                out.append(token)
        return list(dict.fromkeys(out))

    def state(self, duty_id: str, today: date) -> str:
        occ = self.occurrences.get(duty_id)
        if occ is None:
            return "idle"
        base = self._base_state(occ, today)
        if base in ("due", "overdue") and occ.snoozed_until and today < occ.snoozed_until:
            return "snoozed"
        return base

    @staticmethod
    def _base_state(occ: Occurrence, today: date) -> str:
        if occ.opens is None or today < occ.opens:
            return "upcoming"
        return "due" if today <= occ.due else "overdue"

    def open_items(self, today: date, owner: str | None = None) -> list[tuple[Duty, Occurrence, str]]:
        items = []
        for duty_id, occ in self.occurrences.items():
            duty = self.duties[duty_id]
            state = self.state(duty_id, today)
            if state in ("due", "overdue", "snoozed"):
                if owner is None or owner in self.effective_owners(duty):
                    items.append((duty, occ, state))
        return sorted(items, key=lambda i: i[1].due)

    # --------------------------------------------------------------- tick
    def tick(self, now: datetime, conditions: dict[str, float] | None = None) -> TickResult:
        today = now.date()
        conditions = conditions or {}
        result = TickResult()
        for duty_id in list(self.occurrences):
            duty = self.duties[duty_id]
            occ = self.occurrences[duty_id]
            if not duty.enabled:
                continue
            if self._update_window(duty, occ, today, conditions, result):
                continue  # occurrence replaced (auto-skipped)
            self._emit(duty, occ, today, result)
        return result

    def _update_window(
        self,
        duty: Duty,
        occ: Occurrence,
        today: date,
        conditions: dict[str, float],
        result: TickResult,
    ) -> bool:
        sched = duty.schedule
        early = sched.get("open_early_when")
        if early and occ.opens is not None and today < occ.opens:
            days_left = (occ.opens - today).days
            if days_left <= sched.get("early_days", DEFAULT_EARLY_DAYS) and sch.condition_met(
                early, conditions
            ):
                occ.opens = today
        gate = sched.get("when")
        if gate and occ.opens is None:
            if today >= sch.window_start(sched, occ.due) and sch.condition_met(gate, conditions):
                occ.opens = today
            elif today > occ.due:
                self._advance(duty, occ, today, "skipped", None, "auto", "window_closed", result)
                return True
        return False

    def _emit(self, duty: Duty, occ: Occurrence, today: date, result: TickResult) -> None:
        state = self.state(duty.id, today)
        base = self._base_state(occ, today)
        owners = self.effective_owners(duty)
        if base in ("due", "overdue") and not occ.opened_notified:
            occ.opened_notified = True
            result.events.append(Event("due", duty.id, occ.id))
            has_zero = any(sch.parse_duration(o)[0] == 0 for o in duty.remind)
            if state != "snoozed" and (occ.opens != occ.due or not has_zero):
                result.notifications.append(Notification("opened", duty.id, occ.id, owners))
        occ.last_state = state
        if state == "snoozed" or occ.opens is None:
            return
        # Point-in-time duties (opens == due) may remind ahead of the due date;
        # windows only remind once they have opened.
        if occ.opens == occ.due or today >= occ.opens:
            self._reminders(duty, occ, today, owners, result)
        if base == "overdue":
            if not occ.overdue_notified:
                occ.overdue_notified = True
                result.events.append(Event("overdue", duty.id, occ.id))
                who = list(dict.fromkeys(owners + self._resolve(duty, ["observers"])))
                result.notifications.append(Notification("overdue", duty.id, occ.id, who))
            for idx, esc in enumerate(duty.escalate):
                if idx in occ.escalations_sent:
                    continue
                if today >= sch.add_duration(occ.due, esc["after"]):
                    occ.escalations_sent.append(idx)
                    who = self._resolve(duty, list(esc.get("notify", ["admin"])))
                    result.notifications.append(
                        Notification("escalation", duty.id, occ.id, who, detail=esc["after"])
                    )

    def _reminders(
        self, duty: Duty, occ: Occurrence, today: date, owners: list[str], result: TickResult
    ) -> None:
        passed = [o for o in duty.remind if today >= sch.add_duration(occ.due, o)]
        unsent = [o for o in passed if o not in occ.reminders_sent]
        if not unsent:
            return
        latest = max(passed, key=lambda o: sch.add_duration(occ.due, o))
        occ.reminders_sent.extend(unsent)
        if latest in unsent:
            result.notifications.append(
                Notification("reminder", duty.id, occ.id, owners, detail=latest)
            )

    # ----------------------------------------------------------- actions
    def complete(
        self, duty_id: str, by: str | None, now: datetime, method: str = "button", note: str = ""
    ) -> TickResult:
        duty = self.duties[duty_id]
        if method not in DONE_METHODS:
            raise ValueError(f"unknown method: {method}")
        if method not in duty.done_by:
            raise ValueError(f"{duty_id} cannot be completed by {method}")
        occ = self._open(duty_id)
        result = TickResult()
        self._advance(duty, occ, now.date(), "done", by, method, note, result)
        return result

    def skip(self, duty_id: str, by: str | None, now: datetime, reason: str) -> TickResult:
        if not reason or not reason.strip():
            raise ValueError("skip needs a reason")
        duty = self.duties[duty_id]
        occ = self._open(duty_id)
        result = TickResult()
        self._advance(duty, occ, now.date(), "skipped", by, "button", reason, result)
        return result

    def snooze(self, duty_id: str, until: date, today: date) -> None:
        occ = self._open(duty_id)
        if until <= today:
            raise ValueError("snooze must end in the future")
        occ.snoozed_until = until

    def _open(self, duty_id: str) -> Occurrence:
        occ = self.occurrences.get(duty_id)
        if occ is None:
            raise ValueError(f"{duty_id} has no open occurrence")
        return occ

    def _advance(
        self,
        duty: Duty,
        occ: Occurrence,
        today: date,
        kind: str,
        by: str | None,
        method: str,
        note: str,
        result: TickResult,
    ) -> None:
        self.history.append(HistoryEntry(duty.id, occ.due, kind, today, by, method, note))
        result.events.append(
            Event("completed" if kind == "done" else "skipped", duty.id, occ.id, by, note)
        )
        self.occurrences.pop(duty.id, None)
        self._spawn(duty, sch.next_window(duty.schedule, occ.due, today))

    def signal(self, duty_id: str, now: datetime) -> TickResult:
        """An external event arrived (e.g. bill posted, rent received)."""
        duty = self.duties[duty_id]
        if duty.schedule.get("type") != "signal":
            raise ValueError(f"{duty_id} is not signal-driven")
        today = now.date()
        result = TickResult()
        if duty_id not in self.occurrences:
            due = sch.add_duration(today, duty.schedule.get("due_in", "0d"))
            self.occurrences[duty_id] = Occurrence(duty_id=duty_id, due=due, opens=today)
        for target in duty.schedule.get("completes", []):
            if target in self.occurrences and target in self.duties:
                self._advance(
                    self.duties[target],
                    self.occurrences[target],
                    today,
                    "done",
                    None,
                    "auto",
                    f"signal:{duty_id}",
                    result,
                )
        return result

    def not_mine(self, duty_id: str, by: str, today: date) -> Notification:
        duty = self.duties[duty_id]
        occ = self._open(duty_id)
        owners = list(duty.owners or self.modules[duty.module].owners)
        if owners and owners[0] == by and len(owners) > 1:
            owners = owners[1:] + owners[:1]
            duty.owners = owners
        recipients = list(
            dict.fromkeys(
                ([owners[0]] if owners and owners[0] != by else []) + self._admins()
            )
        )
        return Notification("not_mine", duty_id, occ.id, recipients, detail=by)

    # ------------------------------------------------------------ reports
    def health(self) -> list[str]:
        problems = []
        for duty in self.duties.values():
            if duty.enabled and not self.effective_owners(duty):
                problems.append(f"no_owner:{duty.id}")
        return problems

    def digest(self, today: date, days: int = 7) -> dict[str, list[str]]:
        since = today.toordinal() - days
        done = [
            f"{h.duty_id}@{h.on.isoformat()}"
            for h in self.history
            if h.kind == "done" and h.on.toordinal() > since
        ]
        late = [d.id for d, _, s in self.open_items(today) if s == "overdue"]
        return {"done": done, "overdue": late}

    # ------------------------------------------------------------ storage
    def to_dict(self) -> dict[str, Any]:
        return {
            "people": [p.to_dict() for p in self.people.values()],
            "modules": [m.to_dict() for m in self.modules.values()],
            "duties": [d.to_dict() for d in self.duties.values()],
            "occurrences": [o.to_dict() for o in self.occurrences.values()],
            "history": [h.to_dict() for h in self.history],
            "billers": self.billers,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Engine:
        eng = cls()
        for p in data.get("people", []):
            eng.add_person(Person.from_dict(p))
        for m in data.get("modules", []):
            eng.add_module(Module.from_dict(m))
        for d in data.get("duties", []):
            duty = Duty.from_dict(d)
            eng.duties[duty.id] = duty
        for o in data.get("occurrences", []):
            occ = Occurrence.from_dict(o)
            eng.occurrences[occ.duty_id] = occ
        eng.history = [HistoryEntry.from_dict(h) for h in data.get("history", [])]
        eng.billers = dict(data.get("billers", {}))
        return eng
