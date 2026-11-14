import sys
from pathlib import Path

# Import the engine as a top-level package so engine tests never import Home Assistant.
# Appended (not inserted first) so calendar.py in the integration cannot shadow the stdlib.
sys.path.append(str(Path(__file__).resolve().parents[1] / "custom_components" / "homekeeper"))

collect_ignore: list[str] = []
try:
    import homeassistant  # noqa: F401
except ImportError:  # engine tests still run on a plain Python
    collect_ignore.append("ha")
