"""Record validation.

Handling rules (one row can collect several reasons):

* Missing any required column            -> whole file rejected (ValidationError)
* Blank / unparseable timestamp          -> row rejected
* Blank building_id or building_name     -> row rejected
* Non-numeric / blank numeric value      -> row rejected (never replaced by 0)
* Infinite numeric value                 -> row rejected
* Negative power or energy               -> row rejected
* interval_hours <= 0 or > 24            -> row rejected
* |energy - power x interval| > tolerance-> row rejected ("inconsistent")
* Same building_id with a different name -> row rejected (first name wins)
* Duplicate (building_id, timestamp)     -> first kept, later copies rejected

Rejected rows keep their ORIGINAL text values together with the CSV line
number and the reason, so the source data is preserved.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .config import (ENERGY_TOLERANCE_ABS, ENERGY_TOLERANCE_REL,
                     MAX_INTERVAL_HOURS, REQUIRED_COLUMNS)

NUMERIC_COLUMNS = ["interval_hours", "average_power_kw", "energy_kwh"]


class ValidationError(Exception):
    """Raised when a file cannot be processed at all (e.g. missing columns)."""


@dataclass
class ValidationResult:
    accepted: pd.DataFrame
    rejected: pd.DataFrame
    total_rows: int
    reason_counts: dict = field(default_factory=dict)

    @property
    def accepted_rows(self) -> int:
        return len(self.accepted)

    @property
    def rejected_rows(self) -> int:
        return len(self.rejected)

    def summary_frame(self) -> pd.DataFrame:
        rows = [("Total imported rows", self.total_rows),
                ("Accepted rows", self.accepted_rows),
                ("Rejected rows", self.rejected_rows)]
        rows += [(f"Reason: {k}", v) for k, v in sorted(self.reason_counts.items())]
        return pd.DataFrame(rows, columns=["item", "count"])


def _is_blank(series: pd.Series) -> pd.Series:
    return series.isna() | series.astype(str).str.strip().eq("")


def validate_dataframe(raw: pd.DataFrame) -> ValidationResult:
    """Validate raw records (any dtype) and split them into accepted/rejected."""
    missing = [c for c in REQUIRED_COLUMNS if c not in raw.columns]
    if missing:
        raise ValidationError("Missing required column(s): " + ", ".join(missing)
                              + ". Required: " + ", ".join(REQUIRED_COLUMNS))

    raw = raw.reset_index(drop=True)
    n = len(raw)
    reasons: list[list[str]] = [[] for _ in range(n)]

    def flag(mask: pd.Series, text: str) -> None:
        for i in np.flatnonzero(mask.to_numpy()):
            reasons[i].append(text)

    # --- timestamps
    ts_blank = _is_blank(raw["timestamp"])
    ts = pd.to_datetime(raw["timestamp"].astype(str).str.strip(), errors="coerce", format="ISO8601")
    flag(ts_blank, "missing timestamp")
    flag(~ts_blank & ts.isna(), "invalid date format")

    # --- identifiers
    bid = raw["building_id"].astype(str).str.strip()
    bname = raw["building_name"].astype(str).str.strip()
    flag(_is_blank(raw["building_id"]), "missing building identifier")
    flag(_is_blank(raw["building_name"]), "missing building name")

    # --- numeric values (never silently replaced by zero)
    nums = {}
    for col in NUMERIC_COLUMNS:
        blank = _is_blank(raw[col])
        values = pd.to_numeric(raw[col], errors="coerce").astype(float)
        nums[col] = values
        flag(blank, f"missing {col}")
        flag(~blank & values.isna(), f"invalid numerical value in {col}")
        flag(np.isinf(values), f"infinite value in {col}")

    interval, power, energy = nums["interval_hours"], nums["average_power_kw"], nums["energy_kwh"]
    finite = np.isfinite(interval) & np.isfinite(power) & np.isfinite(energy)
    flag(np.isfinite(power) & (power < 0), "negative power value")
    flag(np.isfinite(energy) & (energy < 0), "negative energy consumption")
    flag(np.isfinite(interval) & ((interval <= 0) | (interval > MAX_INTERVAL_HOURS)),
         "invalid interval duration")
    expected = power * interval
    tol = np.maximum(ENERGY_TOLERANCE_ABS, ENERGY_TOLERANCE_REL * expected.abs())
    flag(finite & (interval > 0) & ((energy - expected).abs() > tol),
         "inconsistent power and energy (energy != power x interval)")

    ok = pd.Series([not r for r in reasons])

    # --- id/name consistency (first accepted name per id wins)
    first_name: dict[str, str] = {}
    for i in np.flatnonzero(ok.to_numpy()):
        known = first_name.setdefault(bid[i], bname[i])
        if known != bname[i]:
            reasons[i].append(f"building ID {bid[i]} already used for '{known}'")
    ok = pd.Series([not r for r in reasons])

    # --- duplicates among otherwise-valid rows
    keys = pd.DataFrame({"bid": bid, "ts": ts})
    dup = keys[ok].duplicated(keep="first")
    for i in dup[dup].index:
        reasons[i].append("duplicate building-timestamp combination")
    ok = pd.Series([not r for r in reasons])

    accepted = pd.DataFrame({
        "timestamp": ts[ok],
        "building_id": bid[ok],
        "building_name": bname[ok],
        "interval_hours": interval[ok],
        "average_power_kw": power[ok],
        "energy_kwh": energy[ok],
    })
    if "data_source" in raw.columns:
        src = raw.loc[ok, "data_source"].astype(str).str.strip()
        accepted["data_source"] = src.where(src != "", "imported")
    else:
        accepted["data_source"] = "imported"
    if "injected_anomaly" in raw.columns:
        accepted["injected_anomaly"] = raw.loc[ok, "injected_anomaly"].fillna("").astype(str)
    accepted = accepted.sort_values(["building_id", "timestamp"]).reset_index(drop=True)

    bad = ~ok
    rejected = raw[bad].copy()
    rejected.insert(0, "csv_line", rejected.index + 2)   # +1 header, +1 one-based
    rejected["rejection_reason"] = ["; ".join(reasons[i]) for i in rejected.index]
    rejected = rejected.reset_index(drop=True)

    counts: dict[str, int] = {}
    for r in reasons:
        for text in r:
            key = text.split(" already used")[0] if text.startswith("building ID") else text
            key = "building ID mapped to two names" if key.startswith("building ID") else key
            counts[key] = counts.get(key, 0) + 1
    return ValidationResult(accepted, rejected, n, counts)
