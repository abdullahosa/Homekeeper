"""Homekeeper engine: duties, occurrences, reminders, escalation, history."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any

from . import collected
from . import schedule as sch
from .models import Biller, Duty, HistoryEntry, Module, Occurrence, Person

DONE_METHODS = ("button", "nfc", "voice", "auto")
DEFAULT_EARLY_DAYS = 30


@dataclass
class Event:
    type: str  # due | overdue | completed | skipped
    duty_id: str
    occurrence_id: str
    by: str | None = None
    detail: str = ""
    method: str = ""


@dataclass
class Notification:
    kind: str  # opened | reminder | overdue | escalation | not_mine | moved
    duty_id: str
    occurrence_id: str
    recipients: list[str]
    detail: str = ""


@dataclass
class TickResult:
    events: list[Event] = field(default_factory=list)
    notifications: list[Notification] = field(default_factory=list)


# What the bills table keeps from each BillBot state message.
BILL_STATE_KEYS = ("status", "due_date", "amount", "paid", "paid_amount", "autopay")


class Engine:
    def __init__(self) -> None:
        self.people: dict[str, Person] = {}
        self.modules: dict[str, Module] = {}
        self.duties: dict[str, Duty] = {}
        self.occurrences: dict[str, Occurrence] = {}  # one open occurrence per duty
        self.history: list[HistoryEntry] = []
        self.billers: dict[str, Biller] = {}
        self.biller_seen: dict[str, str] = {}  # biller id -> ISO date of newest bill/payment
        self.biller_since: dict[str, str] = {}  # biller id -> ISO date it was added
        # biller id -> BillBot's latest state message (status, due date, amount...),
        # so the bills table can show paid bills too, not only open ones.
        self.bill_states: dict[str, dict[str, Any]] = {}

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
        for tag in duty.nfc_tags:
            other = self.find_by_tag(tag)
            if other is not None and other.id != duty.id:
                raise ValueError(f"tag {tag} already belongs to {other.id}")

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
    def find_by_tag(self, tag_id: str) -> Duty | None:
        for duty in self.duties.values():
            if duty.enabled and tag_id in duty.nfc_tags:
                return duty
        return None

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
            Event("completed" if kind == "done" else "skipped", duty.id, occ.id, by, note, method)
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
        self._complete_targets(
            duty.schedule.get("completes", []), today, f"signal:{duty_id}", result
        )
        return result


    # ------------------------------------------------------------ calendars
    def apply_calendar(
        self, duty_id: str, events: list[tuple[date, str]], now: datetime
    ) -> TickResult:
        """Follow a calendar (e.g. trash pickup): keep one occurrence for the next
        matching event, due `lead` before it (1d = the evening before). If the event
        moves or is cancelled, the occurrence moves with it; once the event day has
        passed undone, it is skipped. `events` is (event day, summary) for the coming
        weeks. An empty list means "no data" (calendar not loaded yet) and changes nothing."""
        result = TickResult()
        duty = self.duties.get(duty_id)
        if duty is None or not duty.enabled or duty.schedule.get("type") != "calendar" or not events:
            return result
        today = now.date()
        lead = duty.schedule.get("lead", "1d")
        by_day = self.calendar_days(duty, events)
        handled = {h.occurrence_due for h in self.history if h.duty_id == duty_id}
        upcoming = [d for d in sorted(by_day) if d >= today and sch.add_duration(d, lead, -1) not in handled]
        target = upcoming[0] if upcoming else None

        occ = self.occurrences.get(duty_id)
        if occ is not None:
            event_day = (
                date.fromisoformat(occ.meta["event"]) if occ.meta.get("event")
                else sch.add_duration(occ.due, lead)
            )
            if event_day < today:  # the pickup came and went
                self._advance(duty, occ, today, "skipped", None, "auto", "event_passed", result)
            elif target == event_day:
                occ.meta["what"] = " + ".join(collected.tidy(by_day[event_day]))
                return result
            else:  # moved, cancelled, or an earlier one appeared
                imminent = today >= occ.due - timedelta(days=1)
                self.occurrences.pop(duty_id)
                if target is not None:
                    new = self._calendar_occurrence(duty, target, by_day[target], lead)
                    result.events.append(Event("moved", duty.id, new.id, None, target.isoformat()))
                    if imminent:
                        result.notifications.append(
                            Notification(
                                "moved", duty.id, new.id, self.effective_owners(duty),
                                detail=target.isoformat(),
                            )
                        )
                return result
        if target is not None and duty_id not in self.occurrences:
            self._calendar_occurrence(duty, target, by_day[target], lead)
        return result

    @staticmethod
    def calendar_days(duty: Duty, events: list[tuple[date, str]]) -> dict[date, list[str]]:
        """The event titles on each day that the duty's `match` words select."""
        words = [w.lower() for w in duty.schedule.get("match", []) if str(w).strip()]
        by_day: dict[date, list[str]] = {}
        for day, summary in sorted(events):
            text = (summary or "").strip()
            if words and not any(w in text.lower() for w in words):
                continue
            seen = by_day.setdefault(day, [])
            if text and text not in seen:
                seen.append(text)
        return by_day

    def pickups(self, duty: Duty, events: list[tuple[date, str]]) -> list[tuple[date, str]]:
        """Each selected day with what is collected, tidied: (day, "Garbage + Recycling")."""
        return [
            (day, " + ".join(collected.tidy(texts)))
            for day, texts in sorted(self.calendar_days(duty, events).items())
        ]

    def calendar_lines(self, duty: Duty) -> list[str]:
        occ = self.occurrences.get(duty.id)
        if occ is None or not occ.meta.get("event"):
            return []
        what = occ.meta.get("what") or "pickup"
        return [f"Collecting: {what} on {occ.meta['event']}"]

    def _calendar_occurrence(
        self, duty: Duty, event_day: date, whats: list[str], lead: str
    ) -> Occurrence:
        due = sch.add_duration(event_day, lead, -1)
        occ = Occurrence(
            duty_id=duty.id, due=due, opens=due,
            meta={"event": event_day.isoformat(), "what": " + ".join(collected.tidy(whats))},
        )
        self.occurrences[duty.id] = occ
        return occ

    def _complete_targets(
        self,
        targets: list[str],
        today: date,
        note: str,
        result: TickResult,
        paid_on: date | None = None,
        lead_days: int = 7,
    ) -> None:
        """Auto-complete the open occurrences of `targets`. With `paid_on`, only those
        due no more than `lead_days` after that date, so an old payment can't close a
        fresh occurrence."""
        for target in targets:
            occ = self.occurrences.get(target)
            duty = self.duties.get(target)
            if occ is None or duty is None:
                continue
            if paid_on is not None and (occ.due - paid_on).days > lead_days:
                continue
            self._advance(duty, occ, today, "done", None, "auto", note, result)

    # --------------------------------------------------------------- billers
    @staticmethod
    def biller_duty_id(biller_id: str) -> str:
        return f"bill-{biller_id}"

    def biller_duty(self, biller: Biller) -> Duty | None:
        """The 'pay this bill' duty for a bill-kind biller; None for income billers."""
        if biller.kind != "bill":
            return None
        title = dict(biller.title) or {
            "en": f"Pay {biller.name}",
            "ar": f"سداد فاتورة {biller.name_ar or biller.name}",
        }
        return Duty(
            id=self.biller_duty_id(biller.id),
            module=biller.module,
            title=title,
            schedule={"type": "signal"},
            owners=list(biller.owners),
            observers=list(biller.observers),
            remind=list(biller.remind),
            escalate=[dict(e) for e in biller.escalate],
            how_to=f"Bill from {biller.name}. Marking it done also presses BillBot's Mark paid.",
            done_by=["button", "nfc", "voice", "auto"],
            enabled=biller.enabled,
            biller=biller.id,
        )

    def login_for(self, duty: Duty) -> Biller | None:
        """The biller whose account someone would log in to for this duty: the bill's
        own biller, or an income biller (rent) that completes it."""
        if duty.biller:
            biller = self.billers.get(duty.biller)
            return biller if biller and (biller.login_url or biller.login_note) else None
        for biller in self.billers.values():
            if biller.enabled and duty.id in biller.completes and (biller.login_url or biller.login_note):
                return biller
        return None

    def login_lines(self, duty: Duty) -> list[str]:
        biller = self.login_for(duty)
        if biller is None:
            return []
        return [line for line in (
            f"Log in: {biller.login_url}" if biller.login_url else "",
            biller.login_note,
        ) if line]

    def add_biller(self, biller: Biller, today: date) -> None:
        self.billers[biller.id] = biller
        self.biller_since.setdefault(biller.id, today.isoformat())
        duty = self.biller_duty(biller)
        if duty is None:
            return
        if duty.id in self.duties:
            self.update_duty(duty, today)
        else:
            self.add_duty(duty, today)

    def _seen(self, biller_id: str, day: str) -> None:
        if day > self.biller_seen.get(biller_id, ""):
            self.biller_seen[biller_id] = day

    def apply_bill_state(self, biller_id: str, payload: dict[str, Any], now: datetime) -> TickResult:
        """Apply one BillBot state message (billbot/<biller>/state). Idempotent: a
        retained message replayed after a restart changes nothing."""
        result = TickResult()
        biller = self.billers.get(biller_id)
        if biller is None or not biller.enabled:
            return result
        self.bill_states[biller_id] = {
            k: payload.get(k) for k in BILL_STATE_KEYS if payload.get(k) is not None
        }
        today = now.date()
        status = payload.get("status")
        if biller.kind == "income":
            return self._income_state(biller, payload, today, result)
        duty = self.duties.get(self.biller_duty_id(biller.id))
        due_text = payload.get("due_date")
        if duty is None or not due_text or status not in ("due", "overdue", "autopay", "paid"):
            return result
        if payload.get("arrived"):
            self._seen(biller.id, payload["arrived"])
        due = date.fromisoformat(due_text)
        occ = self.occurrences.get(duty.id)
        if status in ("due", "overdue"):
            if any(h.duty_id == duty.id and h.occurrence_due == due for h in self.history):
                return result
            meta = {
                k: payload[k] for k in ("amount", "arrived", "autopay") if payload.get(k) is not None
            }
            if occ is not None and occ.due == due:
                occ.meta.update(meta)
                return result
            if occ is not None:
                self._advance(duty, occ, today, "skipped", None, "auto", "superseded", result)
            self.occurrences[duty.id] = Occurrence(
                duty_id=duty.id, due=due, opens=min(today, due), meta=meta
            )
        elif occ is not None and occ.due == due:
            note = "autopay" if status == "autopay" else f"paid {payload.get('paid') or ''}".strip()
            self._advance(duty, occ, today, "done", None, "auto", note, result)
        return result

    def _income_state(
        self, biller: Biller, payload: dict[str, Any], today: date, result: TickResult
    ) -> TickResult:
        if payload.get("status") != "paid":
            return result
        paid = payload.get("paid") or payload.get("due_date")
        if not paid or paid <= self.biller_seen.get(biller.id, ""):
            return result
        self._seen(biller.id, paid)
        self._complete_targets(
            biller.completes,
            today,
            f"income:{biller.id}",
            result,
            paid_on=date.fromisoformat(paid),
        )
        return result

    def mark_biller_seen(self, biller_id: str, day: date) -> None:
        self._seen(biller_id, day.isoformat())

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

    def project(self, duty_id: str, until: date, limit: int = 60) -> list[date]:
        """Future due dates of a duty up to `until`, assuming each is done on time."""
        occ = self.occurrences.get(duty_id)
        duty = self.duties.get(duty_id)
        if occ is None or duty is None:
            return []
        out: list[date] = []
        due = occ.due
        while due <= until and len(out) < limit:
            out.append(due)
            window = sch.next_window(duty.schedule, due, due)
            if window is None:
                break
            window = sch.shift_into_season(window, duty.season)
            if window[1] <= due:
                break
            due = window[1]
        return out

    # ------------------------------------------------------------ reports
    def health(self, today: date | None = None) -> list[str]:
        problems = []
        for duty in self.duties.values():
            if duty.enabled and not self.effective_owners(duty):
                problems.append(f"no_owner:{duty.id}")
        if today is not None:
            for b in self.billers.values():
                if not b.enabled or not b.cadence_days:
                    continue
                last = self.biller_seen.get(b.id) or self.biller_since.get(b.id)
                if last and (today - date.fromisoformat(last)).days > b.cadence_days + b.grace_days:
                    problems.append(f"biller_silent:{b.id}")
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
            "billers": {k: b.to_dict() for k, b in self.billers.items()},
            "biller_seen": dict(self.biller_seen),
            "biller_since": dict(self.biller_since),
            "bill_states": {k: dict(v) for k, v in self.bill_states.items()},
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
        eng.billers = {k: Biller.from_dict(v) for k, v in data.get("billers", {}).items()}
        eng.biller_seen = dict(data.get("biller_seen", {}))
        eng.biller_since = dict(data.get("biller_since", {}))
        eng.bill_states = {k: dict(v) for k, v in data.get("bill_states", {}).items()}
        return eng
