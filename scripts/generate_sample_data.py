"""Regenerate data/sample_energy_data.csv (deterministic, seed 42).

Usage (from the repository root):
    python scripts/generate_sample_data.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from campus_energy.config import SAMPLE_DATA_FILE  # noqa: E402
from campus_energy.data_loader import export_csv  # noqa: E402
from campus_energy.simulator import generate_dataset  # noqa: E402

if __name__ == "__main__":
    df = generate_dataset()
    export_csv(df, SAMPLE_DATA_FILE)
    print(f"Wrote {len(df)} synthetic records to {SAMPLE_DATA_FILE}")
