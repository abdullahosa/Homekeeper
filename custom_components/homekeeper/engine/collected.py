"""Turn what a trash calendar says into the carts to put out. Pure Python.

ReCollect (CARTology) titles read like "Loose leaf - wednesday week - day 3, yard waste -
concord, bulky waste - concord, recycling - concord, and garbage - concord". This keeps
the carts ("Garbage + Recycling + Yard waste + Bulky waste") and drops the rest (leaf
vacuum days, drop-off events, the area name). A calendar whose words it does not know
is shown as written.
"""

from __future__ import annotations

import re

# Canonical name, then the words that mean it. Display order follows this list.
STREAMS: list[tuple[str, tuple[str, ...]]] = [
    ("Garbage", ("garbage", "trash", "refuse", "solid waste")),
    ("Recycling", ("recycling", "recyclables", "recycle")),
    ("Yard waste", ("yard waste", "yard debris", "green waste", "yard")),
    ("Bulky waste", ("bulky waste", "bulky items", "bulky")),
    ("Compost", ("compost", "organics", "food waste")),
    ("Glass", ("glass",)),
]

ARABIC = {
    "Garbage": "النفايات",
    "Recycling": "إعادة التدوير",
    "Yard waste": "مخلفات الحديقة",
    "Bulky waste": "الأغراض الكبيرة",
    "Compost": "السماد",
    "Glass": "الزجاج",
}

_SPLIT = re.compile(r",|\+|&|\band\b|/", re.IGNORECASE)


def _canonical(name: str) -> str | None:
    low = name.lower()
    for canon, words in STREAMS:
        if any(re.search(rf"\b{re.escape(w)}\b", low) for w in words):
            return canon
    return None


def tidy(summaries: list[str]) -> list[str]:
    """The carts named in one day's events, in a fixed order."""
    names: list[str] = []
    for summary in summaries:
        for piece in _SPLIT.split(summary or ""):
            name = piece.split(" - ")[0].strip()  # "yard waste - concord" -> "yard waste"
            if name:
                names.append(name)
    known = {c for n in names if (c := _canonical(n))}
    if known:
        return [canon for canon, _ in STREAMS if canon in known]
    out: list[str] = []
    for name in names:
        shown = name[:1].upper() + name[1:]
        if shown not in out:
            out.append(shown)
    return out


def translate(text: str, language: str) -> str:
    """'Garbage + Recycling' in the reader's language."""
    parts = [p.strip() for p in (text or "").split(" + ") if p.strip()]
    if language == "ar":
        parts = [ARABIC.get(p, p) for p in parts]
    return " + ".join(parts)
