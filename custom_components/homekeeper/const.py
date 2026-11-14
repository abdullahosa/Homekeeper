"""Constants for Homekeeper."""

DOMAIN = "homekeeper"

STORAGE_KEY = "homekeeper.state"
STORAGE_VERSION = 1

SUBENTRY_PERSON = "person"
SUBENTRY_MODULE = "module"
SUBENTRY_DUTY = "duty"
SUBENTRY_BILLER = "biller"

CONF_CONDITIONS = "conditions"  # "key=sensor.entity, key2=sensor.other"
TICK_INTERVAL_MINUTES = 5

EVENT_PREFIX = "homekeeper_"
ACTION_PREFIX = "HK|"  # mobile-app action id: HK|<verb>|<duty_id>|<person_id>

PLATFORMS = ["todo", "calendar", "sensor", "binary_sensor"]

SIGNAL_UPDATE = "homekeeper_update_{entry_id}"

EVENT_CHANGED = "homekeeper_changed"  # fired whenever the card should refresh
STATIC_URL = "/homekeeper_static"
CARD_FILE = "homekeeper-card.js"
