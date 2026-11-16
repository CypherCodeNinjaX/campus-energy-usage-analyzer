"""Flat-tariff electricity cost estimation (Indian rupees).

Cost (Rs) = Energy (kWh) x Tariff (Rs/kWh)

Fixed charges, demand charges, taxes and time-of-day adjustments are NOT
modelled, so results are estimates and not reproductions of real bills.
"""
from __future__ import annotations

import math

import pandas as pd

from .analytics import daily_energy, total_energy


def validate_tariff(tariff: float) -> float:
    """Return the tariff as float, or raise ValueError if it is invalid."""
    try:
        value = float(tariff)
    except (TypeError, ValueError):
        raise ValueError("Tariff must be a number.") from None
    if not math.isfinite(value):
        raise ValueError("Tariff must be a finite number.")
    if value < 0:
        raise ValueError("Tariff must not be negative.")
    return value


def energy_cost(energy_kwh: float, tariff: float) -> float:
    """Estimated cost in rupees, rounded to paise (2 decimals)."""
    tariff = validate_tariff(tariff)
    if energy_kwh < 0:
        raise ValueError("Energy must not be negative.")
    return round(energy_kwh * tariff, 2)


def campus_cost(df: pd.DataFrame, tariff: float) -> float:
    return energy_cost(total_energy(df), tariff)


def building_costs(df: pd.DataFrame, tariff: float) -> pd.DataFrame:
    tariff = validate_tariff(tariff)
    g = df.groupby(["building_id", "building_name"], as_index=False)["energy_kwh"].sum()
    g["cost_inr"] = (g["energy_kwh"] * tariff).round(2)
    return g.sort_values("cost_inr", ascending=False).reset_index(drop=True)


def daily_costs(df: pd.DataFrame, tariff: float) -> pd.Series:
    tariff = validate_tariff(tariff)
    return (daily_energy(df) * tariff).round(2).rename("cost_inr")


def monthly_costs(df: pd.DataFrame, tariff: float) -> pd.DataFrame:
    tariff = validate_tariff(tariff)
    if df.empty:
        return pd.DataFrame(columns=["month", "energy_kwh", "cost_inr"])
    g = df.groupby(df["timestamp"].dt.to_period("M"))["energy_kwh"].sum().reset_index()
    g.columns = ["month", "energy_kwh"]
    g["month"] = g["month"].astype(str)
    g["cost_inr"] = (g["energy_kwh"] * tariff).round(2)
    return g
