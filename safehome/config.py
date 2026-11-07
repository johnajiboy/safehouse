import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

DATA_DIR = ROOT / "data"
WEB_DIR = ROOT / "web"
DB_PATH = Path(os.environ.get("SAFEHOME_DB", ROOT / "safehome.db"))

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
MODEL = os.environ.get("SAFEHOME_MODEL", "claude-sonnet-5-5")

# Demo mode adds a passwordless "Continue as demo officer" sign-in. Never turn it on for real data.
DEMO_MODE = os.environ.get("DEMO_MODE", "false").strip().lower() in ("1", "true", "yes", "on")

# Each inspector can make this many visits in a working day.
VISITS_PER_INSPECTOR = 3
DEFAULT_INSPECTORS = 2

# Reports from the same building within this many days can be linked.
PATTERN_WINDOW_DAYS = 30
PATTERN_MIN_REPORTS = 3
