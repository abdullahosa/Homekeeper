"""Notification text. English and Arabic.

The Arabic strings are first drafts and should be read by a native speaker
before go-live."""

from __future__ import annotations

from .engine.collected import translate as translate_collected

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
    "moved": {  # detail: the new event day, e.g. the new pickup date
        "en": "Moved to {detail}: {title}",
        "ar": "تغيّر الموعد إلى {detail}: {title}",
    },
}

def collected(text: str, language: str) -> str:
    """'Garbage + Recycling' (as the engine tidied it) in the reader's language."""
    return translate_collected(text, language)

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
