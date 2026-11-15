"""Test setup.

The pure helper modules are imported directly, without Home Assistant. The
tests in tests/ha need the Home Assistant test harness and are skipped when
it is not installed.
"""
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "custom_components" / "canal_de_isabel_ii"))
sys.path.insert(0, str(ROOT))

collect_ignore = []
if importlib.util.find_spec("pytest_homeassistant_custom_component") is None:
    collect_ignore.append("ha")
