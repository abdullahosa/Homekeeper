"""Notification text. English and Arabic.

The Arabic strings are first drafts and should be read by a native speaker
before go-live."""

from __future__ import annotations

MESSAGES: dict[str, dict[str, str]] = {
    "opened": {"en": "New task: {title}", "ar": "مهمة جديدة: {title}"},
    "reminder": {
        "en": "Reminder: {title} (due {due})",
        "ar": "تذكير: {title} (الموعد {due})",
    },
    "overdue": {"en": "Overdue: {title}", "ar": "متأخرة: {title}"},
    "escalation": {
        "en": "Still not done: {title} (due {due})",
        "ar": "لم تتم بعد: {title} (الموعد {due})",
    },
    "not_mine": {
        "en": "{by} can't do this one: {title}",
        "ar": "{by} لا يستطيع القيام بهذه المهمة: {title}",
    },
}

BUTTONS: dict[str, dict[str, str]] = {
    "done": {"en": "Done", "ar": "تم"},
    "snooze": {"en": "Snooze 1 day", "ar": "تأجيل يوم"},
    "not_mine": {"en": "Not mine", "ar": "ليست لي"},
}

APP_TITLE = {"en": "Homekeeper", "ar": "مدبّر المنزل"}


def text(kind: str, language: str, **kwargs: str) -> str:
    table = MESSAGES.get(kind, MESSAGES["reminder"])
    return table.get(language, table["en"]).format(**kwargs)


def button(verb: str, language: str) -> str:
    return BUTTONS[verb].get(language, BUTTONS[verb]["en"])
