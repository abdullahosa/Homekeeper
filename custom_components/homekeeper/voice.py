"""Assist voice: complete or snooze a duty, and ask what is overdue.

Sentences are registered as conversation triggers. A matched trigger always answers
the request, so every sentence below is distinctive on purpose ("mark ... as done")
rather than a bare wildcard that would swallow ordinary speech.

The Arabic sentences are a first draft and should be read by a native speaker."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import TYPE_CHECKING, Any

from homeassistant.components.conversation import ConversationInput
from homeassistant.components.conversation.agent_manager import get_agent_manager
from homeassistant.util import dt as dt_util

from .engine.voice import match_duty

if TYPE_CHECKING:
    from .runtime import Runtime

_LOGGER = logging.getLogger(__name__)

DONE = [
    "mark {duty} as (done|finished|complete|completed)",
    "mark {duty} (done|finished|complete|completed)",
    "أنجزت {duty}",
]
SNOOZE = [
    "snooze {duty} until tomorrow",
    "snooze {duty} for (a|one) day",
    "أجل {duty} ليوم",
]
QUERY = [
    "what (is|are) (overdue|due)",
    "what (chores|tasks|duties) are (due|overdue)",
    "what (chores|tasks|duties) (do we|do I) have",
    "ما هي المهام المتأخرة",
]

SAY = {
    "done": {"en": "Marked {title} as done.", "ar": "تم تسجيل {title} كمنجزة."},
    "snoozed": {"en": "Snoozed {title} until tomorrow.", "ar": "تم تأجيل {title} إلى الغد."},
    "again": {"en": "{title} was just marked done.", "ar": "{title} سُجلت للتو كمنجزة."},
    "none": {"en": "I couldn't find a task called {phrase}.", "ar": "لم أجد مهمة باسم {phrase}."},
    "which": {"en": "Which one: {names}?", "ar": "أي واحدة: {names}؟"},
    "clear": {"en": "Nothing is due or overdue.", "ar": "لا توجد مهام مستحقة أو متأخرة."},
    "list": {"en": "Needs doing: {names}.", "ar": "المطلوب: {names}."},
    "failed": {"en": "I couldn't do that: {why}", "ar": "تعذر ذلك: {why}"},
}


def _lang(user_input: ConversationInput) -> str:
    return "ar" if (user_input.language or "en").lower().startswith("ar") else "en"


def _say(key: str, lang: str, **kw: str) -> str:
    return SAY[key][lang].format(**kw)


def _phrase(result: Any) -> str:
    entity = result.entities.get("duty")
    if entity is None:
        return ""
    return str(getattr(entity, "text", None) or getattr(entity, "value", "") or "")


def register(runtime: Runtime) -> list:
    """Register the sentences; returns the unregister callbacks."""
    manager = get_agent_manager(runtime.hass)

    async def done(user_input: ConversationInput, result: Any) -> str:
        return await _act(runtime, user_input, _phrase(result), snooze=False)

    async def snooze(user_input: ConversationInput, result: Any) -> str:
        return await _act(runtime, user_input, _phrase(result), snooze=True)

    async def query(user_input: ConversationInput, result: Any) -> str:
        lang = _lang(user_input)
        today = dt_util.now().date()
        items = runtime.engine.open_items(today)
        names = [d.display_title(lang) for d, _, s in items if s in ("due", "overdue")]
        if not names:
            return _say("clear", lang)
        extra = f" (+{len(names) - 5})" if len(names) > 5 else ""
        return _say("list", lang, names=", ".join(names[:5]) + extra)

    return [
        manager.register_trigger(DONE, done),
        manager.register_trigger(SNOOZE, snooze),
        manager.register_trigger(QUERY, query),
    ]


async def _act(
    runtime: Runtime, user_input: ConversationInput, phrase: str, snooze: bool
) -> str:
    lang = _lang(user_input)
    now = dt_util.now()
    match = match_duty(runtime.engine, phrase, now.date(), lang)
    if match.duty is None:
        if match.candidates:
            names = " / ".join(d.display_title(lang) for d in match.candidates[:3])
            return _say("which", lang, names=names)
        return _say("none", lang, phrase=phrase or "?")
    duty = match.duty
    title = duty.display_title(lang)
    if snooze:
        runtime.engine.snooze(duty.id, now.date() + timedelta(days=1), now.date())
        runtime.schedule_save()
        runtime.notify_entities()
        return _say("snoozed", lang, title=title)
    if runtime.recently_done(duty.id, now):
        return _say("again", lang, title=title)
    try:
        result = runtime.engine.complete(duty.id, None, now, "voice")
    except ValueError as err:
        return _say("failed", lang, why=str(err))
    await runtime._dispatch(result, now)
    return _say("done", lang, title=title)
