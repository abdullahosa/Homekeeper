from datetime import date

from engine import Duty, Engine, Module, Person
from engine.voice import match_duty

TODAY = date(2026, 12, 1)


def make(*titles):
    e = Engine()
    e.add_person(Person("a", "A"))
    e.add_module(Module("home", {"en": "Home"}, owners=["a"]))
    for i, t in enumerate(titles):
        title = t if isinstance(t, dict) else {"en": t}
        e.add_duty(
            Duty(id=f"d{i}", module="home", title=title,
                 schedule={"type": "after_completion", "every": "3m", "first_due": "2026-12-01"}),
            date(2026, 11, 1),
        )
    return e


def test_exact_partial_and_stemmed_matches():
    e = make("Replace HVAC filters", "Mow the lawn", "Test smoke detectors")
    assert match_duty(e, "replace hvac filters", TODAY).duty.id == "d0"
    assert match_duty(e, "the filters", TODAY).duty.id == "d0"
    assert match_duty(e, "mowing the lawn", TODAY).duty.id == "d1"
    assert match_duty(e, "smoke detector", TODAY).duty.id == "d2"


def test_no_match_and_empty():
    e = make("Replace HVAC filters")
    assert match_duty(e, "wash the car", TODAY).duty is None
    assert match_duty(e, "the", TODAY) .duty is None
    assert match_duty(e, "", TODAY).candidates == []


def test_ambiguous_returns_candidates():
    e = make("Replace HVAC filters", "Replace water filter")
    m = match_duty(e, "replace filter", TODAY)
    assert m.duty is None and {d.id for d in m.candidates} == {"d0", "d1"}
    assert match_duty(e, "hvac filters", TODAY).duty.id == "d0"  # more specific words resolve it


def test_arabic_title_matches_arabic_phrase():
    e = make({"en": "Replace filters", "ar": "تغيير الفلاتر"})
    assert match_duty(e, "الفلاتر", TODAY, "ar").duty.id == "d0"
    assert match_duty(e, "تغيير الفلاتر", TODAY, "ar").duty.id == "d0"


def test_only_duties_with_an_open_occurrence_are_considered():
    e = make("Replace filters")
    e.set_enabled("d0", False, TODAY)
    assert match_duty(e, "replace filters", TODAY).duty is None
