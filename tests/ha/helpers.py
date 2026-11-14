from homeassistant.config_entries import ConfigSubentryData


def sub(kind, ident, data, title=None):
    return ConfigSubentryData(
        data={"id": ident, **data},
        subentry_type=kind,
        title=title or ident,
        unique_id=f"{kind}:{ident}",
    )
