import pytest
from helpers import sub
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.homekeeper.const import DOMAIN


@pytest.fixture(autouse=True)
def _enable(enable_custom_integrations):
    yield


@pytest.fixture
def entry_factory(hass):
    def make(extra=()):
        entry = MockConfigEntry(
            domain=DOMAIN,
            data={},
            subentries_data=[
                sub("person", "adm", {"name": "Admin", "role": "admin", "language": "en", "notify": "notify.mobile_adm"}),
                sub("person", "a", {"name": "Alex", "role": "owner", "language": "en", "notify": "notify.mobile_a"}),
                sub("person", "b", {"name": "Basil", "role": "owner", "language": "ar", "notify": "notify.mobile_b"}),
                sub("module", "home", {"title": {"en": "Home"}, "owners": ["b", "a"]}),
                sub(
                    "duty",
                    "filters",
                    {
                        "module": "home",
                        "title": {"en": "Replace filters", "ar": "تغيير الفلاتر"},
                        "schedule": {"type": "after_completion", "every": "3m", "first_due": "2026-12-01"},
                        "remind": ["0d"],
                        "escalate": [{"after": "2d", "notify": ["admin"]}],
                        "done_by": ["button", "nfc"],
                    },
                    "Replace filters",
                ),
                *extra,
            ],
        )
        entry.add_to_hass(hass)
        return entry

    return make


@pytest.fixture
def notify_calls(hass):
    calls = []

    async def handler(call):
        calls.append(call)

    for name in ("mobile_adm", "mobile_a", "mobile_b"):
        hass.services.async_register("notify", name, handler)
    return calls


@pytest.fixture
def bill_entry(hass, entry_factory):
    """The standard entry plus a Bills module and two billers (one bill, one income)."""
    def make():
        return entry_factory(
            extra=(
                sub("module", "bills", {"title": {"en": "Bills"}, "owners": ["a"]}),
                sub("module", "rental", {"title": {"en": "Rental"}, "owners": ["a"]}),
                sub(
                    "biller",
                    "duke",
                    {
                        "name": "Duke Energy",
                        "kind": "bill",
                        "module": "bills",
                        "sender_domains": ["duke-energy.com", "dukeenergy.com"],
                        "owners": ["b"],
                        "cadence_days": 31,
                        "grace_days": 7,
                        "remind": ["-3d", "0d"],
                        "escalate": [{"after": "2d", "notify": ["admin"]}],
                    },
                    "Duke Energy",
                ),
                sub(
                    "biller",
                    "rent",
                    {
                        "name": "Rent payments",
                        "kind": "income",
                        "module": "rental",
                        "sender_domains": ["zillow.com"],
                        "completes": ["rent-check"],
                        "cadence_days": 15,
                    },
                    "Rent payments",
                ),
                sub(
                    "duty",
                    "rent-check",
                    {
                        "module": "rental",
                        "title": {"en": "Confirm rent received"},
                        "schedule": {"type": "day_of_month", "days": [1, 15]},
                        "done_by": ["button", "auto"],
                    },
                    "Confirm rent received",
                ),
            )
        )

    return make
