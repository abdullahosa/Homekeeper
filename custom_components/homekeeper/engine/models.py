"""Data models. Plain dataclasses with dict (de)serialisation for HA storage."""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from datetime import date
from typing import Any


def _d(value: date | None) -> str | None:
    return value.isoformat() if value else None


def _pd(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None


@dataclass
class Person:
    id: str
    name: str
    role: str = "owner"  # owner | observer | admin
    language: str = "en"  # en | ar
    notify: str | None = None
    ha_user: str | None = None
    quiet_hours: list[str] | None = None  # ["22:00", "07:00"]

    def to_dict(self) -> dict[str, Any]:
        return {f.name: getattr(self, f.name) for f in fields(self)}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Person:
        return cls(**{f.name: data[f.name] for f in fields(cls) if f.name in data})


@dataclass
class Module:
    id: str
    title: dict[str, str] = field(default_factory=dict)
    owners: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "title": self.title, "owners": list(self.owners)}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Module:
        return cls(data["id"], data.get("title", {}), list(data.get("owners", [])))


@dataclass
class Duty:
    id: str
    module: str
    title: dict[str, str]
    schedule: dict[str, Any] = field(default_factory=dict)
    owners: list[str] = field(default_factory=list)
    observers: list[str] = field(default_factory=list)
    remind: list[str] = field(default_factory=list)
    escalate: list[dict[str, Any]] = field(default_factory=list)
    how_to: str = ""
    done_by: list[str] = field(default_factory=lambda: ["button"])
    enabled: bool = True
    season: list[int] | None = None

    def display_title(self, language: str = "en") -> str:
        return self.title.get(language) or self.title.get("en") or self.id

    def to_dict(self) -> dict[str, Any]:
        return {f.name: getattr(self, f.name) for f in fields(self)}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Duty:
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in known})


@dataclass
class Occurrence:
    """One concrete due instance of a duty."""

    duty_id: str
    due: date
    opens: date | None  # None: waiting for a condition to become true
    snoozed_until: date | None = None
    reminders_sent: list[str] = field(default_factory=list)
    escalations_sent: list[int] = field(default_factory=list)
    opened_notified: bool = False
    overdue_notified: bool = False
    last_state: str = "upcoming"

    @property
    def id(self) -> str:
        return f"{self.duty_id}:{self.due.isoformat()}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "duty_id": self.duty_id,
            "due": _d(self.due),
            "opens": _d(self.opens),
            "snoozed_until": _d(self.snoozed_until),
            "reminders_sent": list(self.reminders_sent),
            "escalations_sent": list(self.escalations_sent),
            "opened_notified": self.opened_notified,
            "overdue_notified": self.overdue_notified,
            "last_state": self.last_state,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Occurrence:
        return cls(
            duty_id=data["duty_id"],
            due=_pd(data["due"]),  # type: ignore[arg-type]
            opens=_pd(data.get("opens")),
            snoozed_until=_pd(data.get("snoozed_until")),
            reminders_sent=list(data.get("reminders_sent", [])),
            escalations_sent=list(data.get("escalations_sent", [])),
            opened_notified=data.get("opened_notified", False),
            overdue_notified=data.get("overdue_notified", False),
            last_state=data.get("last_state", "upcoming"),
        )


@dataclass
class HistoryEntry:
    duty_id: str
    occurrence_due: date
    kind: str  # done | skipped
    on: date
    by: str | None = None
    method: str = "button"
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "duty_id": self.duty_id,
            "occurrence_due": _d(self.occurrence_due),
            "kind": self.kind,
            "on": _d(self.on),
            "by": self.by,
            "method": self.method,
            "note": self.note,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> HistoryEntry:
        return cls(
            duty_id=data["duty_id"],
            occurrence_due=_pd(data["occurrence_due"]),  # type: ignore[arg-type]
            kind=data["kind"],
            on=_pd(data["on"]),  # type: ignore[arg-type]
            by=data.get("by"),
            method=data.get("method", "button"),
            note=data.get("note", ""),
        )
