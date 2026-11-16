"""Energy-consumption calculations (pure functions, no GUI code).

Units: power in kW, energy in kWh, time in hours.

Definitions used throughout the project
---------------------------------------
* Observed days     = calendar dates that contain at least one valid reading
                      (days with valid observations, NOT calendar span).
* Campus demand     = sum of building interval-average power at the same
                      timestamp, using only timestamps where EVERY selected
                      building has a reading ("complete timestamps").
* Average power     = total energy / total observed duration on the campus
                      demand series = mean(campus demand)   [kWh / h = kW]
* Peak demand       = max interval-average (1-hour) campus demand. This is
                      not an instantaneous peak and not a utility billing
                      demand (often a 15/30-minute maximum).
* Load factor (%)   = average power / peak demand x 100, only when intervals
                      are uniform and at least 24 complete timestamps exist.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

MIN_LOAD_FACTOR_SAMPLES = 24


def filter_data(df: pd.DataFrame, building_ids=None, start=None, end=None) -> pd.DataFrame:
    """Filter by building IDs and an inclusive date range (dates or strings)."""
    out = df
    if building_ids:
        out = out[out["building_id"].isin(list(building_ids))]
    if start is not None:
        out = out[out["timestamp"] >= pd.Timestamp(start)]
    if end is not None:
        # inclusive end date: keep everything before the next midnight
        out = out[out["timestamp"] < pd.Timestamp(end).normalize() + pd.Timedelta(days=1)]
    return out.copy()


def total_energy(df: pd.DataFrame) -> float:
    """E_total = sum(E_i) in kWh."""
    return float(df["energy_kwh"].sum()) if not df.empty else 0.0


def observed_days(df: pd.DataFrame) -> int:
    return int(df["timestamp"].dt.normalize().nunique()) if not df.empty else 0


def average_daily_energy(df: pd.DataFrame) -> float | None:
    days = observed_days(df)
    return total_energy(df) / days if days else None


def campus_demand_series(df: pd.DataFrame) -> pd.Series:
    """Summed kW per timestamp over complete timestamps only."""
    if df.empty:
        return pd.Series(dtype=float)
    n_buildings = df["building_id"].nunique()
    g = df.groupby("timestamp").agg(kw=("average_power_kw", "sum"), n=("building_id", "nunique"))
    return g.loc[g["n"] == n_buildings, "kw"].sort_index()


def uniform_interval(df: pd.DataFrame) -> float | None:
    vals = df["interval_hours"].unique() if not df.empty else []
    return float(vals[0]) if len(vals) == 1 else None


def average_power(df: pd.DataFrame) -> float | None:
    """Total energy / total observed duration (kW)."""
    if df.empty:
        return None
    if uniform_interval(df) is None:
        # Mixed intervals: duration-weighted average per building, summed
        per_b = df.groupby("building_id").apply(
            lambda g: g["energy_kwh"].sum() / g["interval_hours"].sum(), include_groups=False)
        return float(per_b.sum())
    series = campus_demand_series(df)
    return float(series.mean()) if len(series) else None


def peak_demand(df: pd.DataFrame) -> tuple[float, pd.Timestamp] | None:
    """(kW, timestamp) of the maximum interval-average campus demand."""
    series = campus_demand_series(df)
    if series.empty:
        return None
    return float(series.max()), series.idxmax()


def load_factor(df: pd.DataFrame) -> float | None:
    """Load factor in percent, or None when not computable."""
    if df.empty or uniform_interval(df) is None:
        return None
    series = campus_demand_series(df)
    if len(series) < MIN_LOAD_FACTOR_SAMPLES or series.max() <= 0:
        return None
    return float(series.mean() / series.max() * 100.0)


def percentage_change(current: float, previous: float) -> float | None:
    """((current - previous) / previous) x 100; None if previous is 0."""
    if previous == 0:
        return None
    return (current - previous) / previous * 100.0


def building_summary(df: pd.DataFrame, tariff: float) -> pd.DataFrame:
    """One row per building with energy, share, power and cost figures."""
    cols = ["building_id", "building_name", "records", "energy_kwh", "share_pct",
            "avg_power_kw", "peak_kw", "load_factor_pct", "cost_inr"]
    if df.empty:
        return pd.DataFrame(columns=cols)
    total = total_energy(df)
    rows = []
    for (bid, name), g in df.groupby(["building_id", "building_name"]):
        e = float(g["energy_kwh"].sum())
        rows.append({
            "building_id": bid, "building_name": name, "records": len(g),
            "energy_kwh": e,
            "share_pct": e / total * 100.0 if total > 0 else None,
            "avg_power_kw": e / float(g["interval_hours"].sum()),
            "peak_kw": float(g["average_power_kw"].max()),
            "load_factor_pct": load_factor(g),
            "cost_inr": round(e * tariff, 2),
        })
    return pd.DataFrame(rows, columns=cols).sort_values("energy_kwh", ascending=False).reset_index(drop=True)


def daily_energy(df: pd.DataFrame) -> pd.Series:
    if df.empty:
        return pd.Series(dtype=float, name="energy_kwh")
    return df.groupby(df["timestamp"].dt.normalize())["energy_kwh"].sum().rename("energy_kwh")


def daily_energy_by_building(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    return df.pivot_table(index=df["timestamp"].dt.normalize(), columns="building_name",
                          values="energy_kwh", aggfunc="sum")


def moving_average(values, window: int = 7) -> np.ndarray:
    """Trailing moving average using NumPy convolution (length n-window+1)."""
    arr = np.asarray(values, dtype=float)
    if window < 1 or len(arr) < window:
        return np.array([])
    return np.convolve(arr, np.ones(window) / window, mode="valid")


def hourly_profile(df: pd.DataFrame) -> pd.DataFrame:
    """Mean energy (kWh) for each hour of day, one column per building."""
    if df.empty:
        return pd.DataFrame()
    return df.pivot_table(index=df["timestamp"].dt.hour, columns="building_name",
                          values="energy_kwh", aggfunc="mean")


def heatmap_matrix(df: pd.DataFrame) -> pd.DataFrame:
    """Rows = date, columns = hour (0-23), values = total kWh (NaN if no data)."""
    if df.empty:
        return pd.DataFrame()
    m = df.pivot_table(index=df["timestamp"].dt.date, columns=df["timestamp"].dt.hour,
                       values="energy_kwh", aggfunc="sum")
    return m.reindex(columns=range(24))


def weekday_weekend(df: pd.DataFrame) -> pd.DataFrame:
    """Average daily energy per building on weekdays vs weekends."""
    if df.empty:
        return pd.DataFrame(columns=["Weekday", "Weekend"])
    d = df.assign(date=df["timestamp"].dt.normalize())
    daily = d.groupby(["building_name", "date"])["energy_kwh"].sum().reset_index()
    daily["day_type"] = np.where(daily["date"].dt.day_of_week >= 5, "Weekend", "Weekday")
    out = daily.pivot_table(index="building_name", columns="day_type", values="energy_kwh", aggfunc="mean")
    return out.reindex(columns=["Weekday", "Weekend"])


def top_peaks(df: pd.DataFrame, n: int = 10) -> pd.DataFrame:
    cols = ["timestamp", "building_id", "building_name", "average_power_kw", "energy_kwh"]
    return df.nlargest(n, "average_power_kw")[cols].reset_index(drop=True)


def data_completeness(df: pd.DataFrame) -> pd.DataFrame:
    """Readings per building per day vs expected (24 / interval)."""
    if df.empty:
        return pd.DataFrame(columns=["building_id", "date", "readings", "expected", "complete"])
    d = df.assign(date=df["timestamp"].dt.normalize())
    g = d.groupby(["building_id", "date"]).agg(readings=("energy_kwh", "size"),
                                               interval=("interval_hours", "median")).reset_index()
    g["expected"] = (24 / g["interval"]).round().astype(int)
    g["complete"] = g["readings"] >= g["expected"]
    return g.drop(columns="interval")


def monthly_summary(df: pd.DataFrame, tariff: float) -> list[dict]:
    """Month x building summary used for JSON export."""
    out = []
    if df.empty:
        return out
    for (month, bid, name), g in df.groupby([df["timestamp"].dt.to_period("M").astype(str),
                                             "building_id", "building_name"]):
        e = float(g["energy_kwh"].sum())
        out.append({"month": month, "building_id": bid, "building_name": name,
                    "records": int(len(g)), "energy_kwh": round(e, 3),
                    "peak_kw": round(float(g["average_power_kw"].max()), 3),
                    "estimated_cost_inr": round(e * tariff, 2)})
    return out


def compare_periods(df: pd.DataFrame, p1: tuple, p2: tuple, tariff: float) -> dict:
    """Compare energy and cost of period 2 (current) against period 1 (previous)."""
    a = filter_data(df, start=p1[0], end=p1[1])
    b = filter_data(df, start=p2[0], end=p2[1])
    ea, eb = total_energy(a), total_energy(b)
    da, db = observed_days(a), observed_days(b)
    return {
        "previous_kwh": ea, "current_kwh": eb,
        "previous_cost": round(ea * tariff, 2), "current_cost": round(eb * tariff, 2),
        "previous_days": da, "current_days": db,
        "change_pct": percentage_change(eb, ea),
        "daily_change_pct": percentage_change(eb / db, ea / da) if da and db else None,
    }


def kpis(df: pd.DataFrame, tariff: float, anomaly_count: int | None) -> dict:
    """All dashboard KPI values. None means 'not available' (never invented)."""
    if df.empty:
        return {k: None for k in ["total_kwh", "total_cost", "avg_daily_kwh", "peak_kw",
                                  "peak_time", "buildings", "anomalies", "top_building",
                                  "cost_per_building", "load_factor", "observed_days"]}
    peak = peak_demand(df)
    summary = building_summary(df, tariff)
    e = total_energy(df)
    return {
        "total_kwh": e,
        "total_cost": round(e * tariff, 2),
        "avg_daily_kwh": average_daily_energy(df),
        "peak_kw": peak[0] if peak else None,
        "peak_time": peak[1] if peak else None,
        "buildings": int(df["building_id"].nunique()),
        "anomalies": anomaly_count,
        "top_building": summary.iloc[0]["building_name"],
        "cost_per_building": round(e * tariff / df["building_id"].nunique(), 2),
        "load_factor": load_factor(df),
        "observed_days": observed_days(df),
    }
