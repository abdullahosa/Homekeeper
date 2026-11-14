"""Match a spoken phrase to a duty. Pure Python; the Assist glue lives in ../voice.py."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

from .core import Engine
from .models import Duty

_STOP = {
    "the", "a", "an", "my", "our", "to", "of", "please", "task", "duty", "as", "is", "are",
    "ال", "في", "من",
}
_WORD = re.compile(r"[\w]+", re.UNICODE)


def tokens(text: str) -> list[str]:
    return [w for w in _WORD.findall((text or "").casefold()) if w not in _STOP]


def _stem(word: str) -> str:
    """Cheap English stemming so 'mowing' / 'mowed' / 'mow' line up."""
    for suffix in ("ing", "ed", "es", "s"):
        if len(word) > len(suffix) + 2 and word.endswith(suffix):
            return word[: -len(suffix)]
    return word


def _bag(text: str) -> set[str]:
    return {_stem(w) for w in tokens(text)}


@dataclass
class Match:
    duty: Duty | None
    candidates: list[Duty]  # filled when the phrase was ambiguous


def match_duty(
    engine: Engine, phrase: str, today: date, language: str = "en", min_score: float = 0.5
) -> Match:
    """Best duty with an open occurrence for `phrase`, or the tied candidates.

    A duty scores the share of the spoken words found in its title (any language),
    so "filters" or "replace filters" both find "Replace HVAC filters". Duties that
    are due or overdue win ties over ones merely upcoming."""
    spoken = _bag(phrase)
    if not spoken:
        return Match(None, [])
    scored: list[tuple[float, Duty]] = []
    for duty_id, occ in engine.occurrences.items():
        duty = engine.duties[duty_id]
        best = 0.0
        for title in {duty.title.get(language), duty.title.get("en"), *duty.title.values()}:
            if not title:
                continue
            bag = _bag(title)
            if not bag:
                continue
            overlap = len(spoken & bag)
            score = overlap / len(spoken)
            # prefer titles that are also mostly covered by what was said
            score += 0.1 * (overlap / len(bag))
            best = max(best, score)
        if best >= min_score:
            urgent = occ.opens is not None and occ.opens <= today and occ.due <= today
            scored.append((best + (0.05 if urgent else 0.0), duty))
    if not scored:
        return Match(None, [])
    scored.sort(key=lambda s: (-s[0], s[1].id))
    top = scored[0][0]
    tied = [d for s, d in scored if top - s < 0.05]
    if len(tied) == 1:
        return Match(tied[0], [])
    return Match(None, tied)

