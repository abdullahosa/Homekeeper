"""Constants for Homekeeper."""

DOMAIN = "homekeeper"

STATES = ("upcoming", "due", "overdue", "done", "skipped")
SCHEDULE_TYPES = (
    "interval",
    "after_completion",
    "day_of_month",
    "yearly_window",
    "condition",
    "signal",
)
DONE_BY = ("button", "nfc", "voice", "auto")
ROLES = ("owner", "observer", "admin")
LANGUAGES = ("en", "ar")
