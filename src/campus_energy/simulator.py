"""Deterministic synthetic electricity-consumption generator.

Every record is labelled ``data_source = "synthetic"``. The values are
plausible *simulated* loads, NOT real campus measurements.

Model for one building, one hour:
    P = base_kw + (peak_kw - base_kw) * activity(hour, weekday)
    P = P * noise,  noise ~ Normal(1, sigma)   (clipped so P > 0)
    E = P * interval_hours
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .config import (DEFAULT_BUILDINGS, DEFAULT_DAYS, DEFAULT_SEED,
                     DEFAULT_START_DATE, DEFAULT_TARIFF_INR_PER_KWH)


@dataclass(frozen=True)
class LoadProfile:
    """Simulation parameters for a building category (kW)."""

    base_kw: float            # standby / night load
    peak_kw: float            # typical full-activity load
    active_hours: tuple       # (start, end) hours of main activity, end exclusive
    weekend_factor: float     # activity multiplier on Saturday/Sunday
    sigma: float = 0.06       # relative random variation
    shoulder: float = 0.35    # activity level in the hour before/after active hours


PROFILES = {
    "academic": LoadProfile(8.0, 55.0, (9, 17), 0.15),
    "electronics_lab": LoadProfile(5.0, 42.0, (10, 17), 0.10, sigma=0.08),
    "computer_lab": LoadProfile(12.0, 48.0, (9, 18), 0.25),      # moderate standby (servers, idle PCs)
    "library": LoadProfile(6.0, 30.0, (8, 21), 0.60, sigma=0.04),  # stable daytime, open weekends
    "administrative": LoadProfile(4.0, 26.0, (9, 17), 0.08),
    "general": LoadProfile(5.0, 25.0, (9, 17), 0.30),
}

# (building_id, day offset, hour, multiplier on profile peak, label)
# Multipliers are applied to the building's *peak_kw* so the effect is visible.
DEFAULT_ANOMALIES = [
    ("B001", 4, 2, 0.55, "night_usage"),        # unexpected night-time consumption
    ("B001", 18, 23, 0.50, "night_usage"),
    ("B002", 9, 14, 1.90, "high_lab_usage"),    # abnormally high laboratory usage
    ("B002", 22, 11, 1.80, "high_lab_usage"),
    ("B003", 12, 3, 1.20, "demand_spike"),      # sudden increase in demand (night)
    ("B003", 25, 15, 1.75, "demand_spike"),
    ("B004", 15, 12, 0.03, "low_reading"),      # unusually low reading during opening hours
    ("B005", 7, 11, 0.02, "low_reading"),
]


def _activity(hour: int, weekend: bool, profile: LoadProfile) -> float:
    """Return activity level between 0 and 1 for a given hour."""
    start, end = profile.active_hours
    if start <= hour < end:
        level = 1.0
        if hour == 13:              # lunch-time dip
            level = 0.8
    elif hour in (start - 1, end):
        level = profile.shoulder
    else:
        level = 0.0
    return level * (profile.weekend_factor if weekend else 1.0)


def generate_dataset(
    start_date: str = DEFAULT_START_DATE,
    days: int = DEFAULT_DAYS,
    buildings: list[dict] | None = None,
    seed: int = DEFAULT_SEED,
    tariff: float = DEFAULT_TARIFF_INR_PER_KWH,
    include_anomalies: bool = True,
    anomalies: list[tuple] | None = None,
) -> pd.DataFrame:
    """Generate hourly synthetic readings.

    Returns a DataFrame with the standard schema plus ``injected_anomaly``
    (ground-truth label of injected anomalies, empty string otherwise).
    """
    if days < 1:
        raise ValueError("days must be at least 1")
    if tariff < 0:
        raise ValueError("tariff must not be negative")
    buildings = buildings if buildings is not None else DEFAULT_BUILDINGS
    rng = np.random.default_rng(seed)
    timestamps = pd.date_range(pd.Timestamp(start_date), periods=days * 24, freq="h")
    start = timestamps[0].normalize()

    anomaly_map = {}
    if include_anomalies:
        for bid, day, hour, mult, label in (anomalies if anomalies is not None else DEFAULT_ANOMALIES):
            if 0 <= day < days:
                anomaly_map[(bid, start + pd.Timedelta(days=day, hours=hour))] = (mult, label)

    frames = []
    for b in buildings:
        profile = PROFILES.get(b.get("category", "general"), PROFILES["general"])
        hours = np.asarray(timestamps.hour)
        weekend = np.asarray(timestamps.day_of_week >= 5)
        activity = np.array([_activity(h, w, profile) for h, w in zip(hours, weekend)])
        power = profile.base_kw + (profile.peak_kw - profile.base_kw) * activity
        noise = rng.normal(1.0, profile.sigma, size=len(power))
        power = power * np.clip(noise, 0.7, 1.3)           # never negative
        labels = np.array([""] * len(power), dtype=object)
        for i, ts in enumerate(timestamps):
            hit = anomaly_map.get((b["building_id"], ts))
            if hit:
                power[i] = profile.peak_kw * hit[0]
                labels[i] = hit[1]
        power = np.round(np.maximum(power, 0.0), 3)
        frames.append(pd.DataFrame({
            "timestamp": timestamps,
            "building_id": b["building_id"],
            "building_name": b["name"],
            "interval_hours": 1.0,
            "average_power_kw": power,
        }).assign(injected_anomaly=labels))

    df = pd.concat(frames, ignore_index=True)
    df["energy_kwh"] = np.round(df["average_power_kw"] * df["interval_hours"], 3)
    df["estimated_cost_inr"] = np.round(df["energy_kwh"] * tariff, 2)
    df["data_source"] = "synthetic"
    cols = ["timestamp", "building_id", "building_name", "interval_hours", "average_power_kw",
            "energy_kwh", "estimated_cost_inr", "data_source", "injected_anomaly"]
    return df[cols].sort_values(["building_id", "timestamp"]).reset_index(drop=True)
