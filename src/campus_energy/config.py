"""Central configuration: constants, default buildings, colours and paths.

All values that a user may want to change (tariff, anomaly multiplier, ...)
have defaults here and can be edited at run time from the Settings page.
"""
from __future__ import annotations

from pathlib import Path

APP_TITLE = "Campus Energy Usage Analyzer"
APP_SUBTITLE = "Electricity Consumption Monitoring & Analytics"
APP_VERSION = "1.0.0"

# ---------------------------------------------------------------- paths
PACKAGE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGE_DIR.parents[1]          # repo root (src/campus_energy -> root)
DATA_DIR = PROJECT_ROOT / "data"
SAMPLE_DATA_FILE = DATA_DIR / "sample_energy_data.csv"
LOG_FILE = Path.home() / ".campus_energy_analyzer.log"   # portable, per-user

# ---------------------------------------------------------- data schema
REQUIRED_COLUMNS = [
    "timestamp",
    "building_id",
    "building_name",
    "interval_hours",
    "average_power_kw",
    "energy_kwh",
]
OPTIONAL_COLUMNS = ["estimated_cost_inr", "data_source"]
TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S"

# ------------------------------------------------------ analysis defaults
# Illustrative, user-configurable flat tariff. NOT an official tariff.
DEFAULT_TARIFF_INR_PER_KWH = 8.0
DEFAULT_SEED = 42
DEFAULT_DAYS = 30
DEFAULT_START_DATE = "2026-10-01"
DEFAULT_IQR_MULTIPLIER = 1.5
MIN_GROUP_SIZE = 8           # below this, a comparable group falls back to a broader group
MIN_IQR_FRACTION = 0.10      # IQR noise floor as a fraction of group median (0 = textbook IQR)
MIN_IQR_SAMPLES = 4          # below this, quartiles are not meaningful -> not evaluated
# Relative tolerance for "energy = power x interval" consistency check
ENERGY_TOLERANCE_REL = 0.01
ENERGY_TOLERANCE_ABS = 0.01  # kWh
MAX_INTERVAL_HOURS = 24.0

# Occupied (working) hours used to form comparable operating periods
OCCUPIED_START_HOUR = 8      # inclusive
OCCUPIED_END_HOUR = 18       # exclusive

ANOMALY_DISCLAIMER = (
    "A statistical anomaly is not proof of electrical equipment failure, "
    "energy theft, or malfunction."
)
TARIFF_NOTE = (
    "Estimated cost = energy x flat tariff. The default Rs 8/kWh is an "
    "illustrative, user-configurable value, not an official tariff. Real "
    "institutional bills may also include fixed charges, demand charges, "
    "taxes and time-of-day adjustments, which are not modelled."
)
SYNTHETIC_NOTE = (
    "Default records are SYNTHETIC (simulated). They are not real campus "
    "meter measurements; the application has no hardware or live meter link."
)

# ------------------------------------------------------ default buildings
# category selects the simulation load profile (see simulator.PROFILES)
DEFAULT_BUILDINGS = [
    {"building_id": "B001", "name": "Academic Block", "category": "academic"},
    {"building_id": "B002", "name": "Electronics Laboratory", "category": "electronics_lab"},
    {"building_id": "B003", "name": "Computer Laboratory", "category": "computer_lab"},
    {"building_id": "B004", "name": "Central Library", "category": "library"},
    {"building_id": "B005", "name": "Administrative Building", "category": "administrative"},
]
BUILDING_CATEGORIES = [
    "academic", "electronics_lab", "computer_lab", "library", "administrative", "general",
]

# --------------------------------------------------------------- colours
COLORS = {
    "navy": "#0F1B2D",
    "sidebar": "#13233A",
    "sidebar_active": "#1D3557",
    "slate": "#334155",
    "slate_light": "#64748B",
    "bg": "#EEF2F6",
    "card": "#FFFFFF",
    "text": "#0F172A",
    "muted": "#475569",
    "white": "#FFFFFF",
    "teal": "#0E9F9A",
    "cyan": "#0891B2",
    "green": "#15803D",
    "amber": "#B45309",
    "amber_bg": "#FEF3C7",
    "red": "#B91C1C",
    "border": "#CBD5E1",
}
# Distinct, colour-blind-friendly series colours (Okabe-Ito based)
SERIES_COLORS = ["#0072B2", "#E69F00", "#009E73", "#CC79A7", "#56B4E9", "#D55E00", "#F0E442", "#000000"]
