import sys
from pathlib import Path

# Import the engine as a top-level package so tests never import Home Assistant.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components" / "homekeeper"))
