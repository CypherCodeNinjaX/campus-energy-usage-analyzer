"""Transparent IQR-based anomaly detection.

IQR = Q3 - Q1,  lower = Q1 - k*IQR,  upper = Q3 + k*IQR   (k = 1.5 default)

Quartiles use NumPy's default linear interpolation (np.percentile).
Readings are compared on interval-average power (kW) so that records with
different interval lengths stay comparable.

Comparable groups (avoid one global campus threshold):
    building  x  day type (Weekday / Weekend)  x  hour of day
    e.g. "Academic Block | Weekday | 14:00" compares 14:00 on every weekday.
Fallback chain for small groups (fewer than MIN_GROUP_SIZE readings):
    building x day type x hour  ->  building x day type  ->  whole building
If even the whole building has fewer than MIN_IQR_SAMPLES readings, its
readings are not evaluated (not enough data for quartiles).

Noise floor: in very steady groups (e.g. night standby load) the IQR can be
tiny, so +/-5 % meter noise would be flagged. The IQR used for the limits is
therefore at least MIN_IQR_FRACTION (10 %) of the group median. Set it to 0
in Settings to use the textbook rule exactly.
The operating period ("Weekday occupied" = Mon-Fri 08:00-17:59, "Weekday
off-hours", "Weekend") is used only to name the anomaly category.

A statistical anomaly is NOT proof of equipment failure, energy theft or
malfunction - it only says a reading is unusual relative to its group.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .analytics import data_completeness
from .config import (ANOMALY_DISCLAIMER, DEFAULT_IQR_MULTIPLIER, MIN_GROUP_SIZE,
                     MIN_IQR_FRACTION, MIN_IQR_SAMPLES, OCCUPIED_END_HOUR, OCCUPIED_START_HOUR)

ANOMALY_COLUMNS = ["timestamp", "building_id", "building_name", "average_power_kw", "energy_kwh",
                   "lower_bound_kw", "upper_bound_kw", "expected_range", "category",
                   "group", "method", "day_complete"]
CATEGORIES = ("High consumption", "Unexpected off-hours consumption",
              "Sudden demand increase", "Unusually low reading")


def iqr_bounds(values, k: float = DEFAULT_IQR_MULTIPLIER, min_iqr_fraction: float = 0.0) -> dict:
    """Return Q1, Q3, IQR and the lower/upper limits for a 1-D sample.

    min_iqr_fraction > 0 applies a noise floor: the IQR used for the limits
    is at least ``min_iqr_fraction x median``. With 0 (default) this is the
    textbook rule.
    """
    arr = np.asarray(values, dtype=float)
    arr = arr[np.isfinite(arr)]
    if arr.size == 0:
        raise ValueError("No finite values supplied.")
    q1, q3 = np.percentile(arr, [25, 75])
    iqr = q3 - q1
    used = max(iqr, min_iqr_fraction * float(np.median(arr)))
    return {"q1": float(q1), "q3": float(q3), "iqr": float(iqr), "iqr_used": float(used),
            "lower": float(q1 - k * used), "upper": float(q3 + k * used)}


def iqr_outlier_mask(values, k: float = DEFAULT_IQR_MULTIPLIER) -> np.ndarray:
    b = iqr_bounds(values, k)
    arr = np.asarray(values, dtype=float)
    return (arr < b["lower"]) | (arr > b["upper"])


def operating_period(ts: pd.Series) -> pd.Series:
    weekend = ts.dt.day_of_week >= 5
    occupied = (ts.dt.hour >= OCCUPIED_START_HOUR) & (ts.dt.hour < OCCUPIED_END_HOUR)
    return pd.Series(np.where(weekend, "Weekend",
                              np.where(occupied, "Weekday occupied", "Weekday off-hours")),
                     index=ts.index)


def detect_anomalies(df: pd.DataFrame, k: float = DEFAULT_IQR_MULTIPLIER,
                     min_group_size: int = MIN_GROUP_SIZE, grouping: str = "building_period",
                     min_iqr_fraction: float = MIN_IQR_FRACTION) -> pd.DataFrame:
    """Flag readings outside IQR limits.

    grouping: "building_period" (default), "building", or "global" (campus-wide,
    used only for comparison/evaluation).
    """
    if df.empty:
        return pd.DataFrame(columns=ANOMALY_COLUMNS)
    d = df.sort_values(["building_id", "timestamp"]).copy()
    d["period"] = operating_period(d["timestamp"])
    d["prev_kw"] = d.groupby("building_id")["average_power_kw"].shift(1)

    if grouping == "global":
        d["group_key"] = "Campus (all buildings)"
    elif grouping == "building":
        d["group_key"] = d["building_name"]
    else:
        day_type = np.where(d["timestamp"].dt.day_of_week >= 5, "Weekend", "Weekday")
        d["group_key"] = (d["building_name"] + " | " + day_type + " | "
                          + d["timestamp"].dt.hour.map("{:02d}:00".format))
        for fallback in (d["building_name"] + " | " + day_type + " (fallback)",
                         d["building_name"] + " | all readings (fallback)"):
            sizes = d.groupby("group_key")["average_power_kw"].transform("size")
            small = sizes < min_group_size
            d.loc[small, "group_key"] = fallback[small]

    complete = data_completeness(df)
    complete_map = {(r.building_id, r.date): bool(r.complete) for r in complete.itertuples()}

    found = []
    for key, g in d.groupby("group_key"):
        if len(g) < MIN_IQR_SAMPLES:
            continue                                    # insufficient data: not evaluated
        b = iqr_bounds(g["average_power_kw"], k, min_iqr_fraction)
        method = (f"IQR, k={k:g}, n={len(g)}, Q1={b['q1']:.2f}, Q3={b['q3']:.2f}, "
                  f"IQR used={b['iqr_used']:.2f} kW")
        out = g[(g["average_power_kw"] < b["lower"]) | (g["average_power_kw"] > b["upper"])]
        for r in out.itertuples():
            if r.average_power_kw < b["lower"]:
                cat = "Unusually low reading"
            elif r.period != "Weekday occupied":
                cat = "Unexpected off-hours consumption"
            elif not pd.isna(r.prev_kw) and r.average_power_kw > 1.5 * r.prev_kw + 1:
                cat = "Sudden demand increase"      # > 50 % jump from previous reading
            else:
                cat = "High consumption"
            found.append({
                "timestamp": r.timestamp, "building_id": r.building_id,
                "building_name": r.building_name, "average_power_kw": r.average_power_kw,
                "energy_kwh": r.energy_kwh, "lower_bound_kw": round(max(b["lower"], 0.0), 3),
                "upper_bound_kw": round(b["upper"], 3),
                "expected_range": f"{max(b['lower'], 0.0):.2f} - {b['upper']:.2f} kW",
                "category": cat, "group": key, "method": method,
                "day_complete": complete_map.get((r.building_id, r.timestamp.normalize()), False),
            })
    res = pd.DataFrame(found, columns=ANOMALY_COLUMNS)
    return res.sort_values(["timestamp", "building_id"]).reset_index(drop=True)


def evaluate_against_injected(df: pd.DataFrame, k: float = DEFAULT_IQR_MULTIPLIER,
                              min_iqr_fraction: float = MIN_IQR_FRACTION) -> pd.DataFrame:
    """Compare grouping strategies on a synthetic dataset with known injected anomalies.

    Returns flags raised, how many injected anomalies were found, and how many
    flags were NOT injected (these may still be legitimately unusual readings).
    """
    if "injected_anomaly" not in df.columns:
        return pd.DataFrame()
    truth = df[df["injected_anomaly"].fillna("") != ""]
    truth_keys = set(zip(truth["building_id"], truth["timestamp"]))
    rows = []
    for label, grouping in [("Global campus threshold", "global"),
                            ("Building-specific", "building"),
                            ("Building x day type x hour", "building_period")]:
        a = detect_anomalies(df, k=k, grouping=grouping, min_iqr_fraction=min_iqr_fraction)
        keys = set(zip(a["building_id"], a["timestamp"]))
        hit = len(keys & truth_keys)
        rows.append({"method": label, "flags": len(keys), "injected": len(truth_keys),
                     "injected_detected": hit, "other_flags": len(keys) - hit})
    return pd.DataFrame(rows)


def disclaimer() -> str:
    return ANOMALY_DISCLAIMER
