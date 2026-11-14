import pytest
from homeassistant.config_entries import ConfigSubentryData
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.homekeeper.const import DOMAIN


@pytest.fixture(autouse=True)
def _enable(enable_custom_integrations):
    yield


def sub(kind, ident, data, title=None):
    return ConfigSubentryData(
        data={"id": ident, **data},
        subentry_type=kind,
        title=title or ident,
        unique_id=f"{kind}:{ident}",
    )


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
