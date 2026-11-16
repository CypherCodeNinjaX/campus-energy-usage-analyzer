"""Matplotlib chart functions.

Every function draws onto a ``matplotlib.figure.Figure`` that it clears
first, so the same functions are used by the Tkinter dashboard (embedded
canvas), the PDF report and the documentation scripts. No pyplot state is
used, which keeps embedding in Tkinter safe.
"""
from __future__ import annotations

import matplotlib.dates as mdates
import numpy as np
import pandas as pd
from matplotlib.figure import Figure

from . import analytics as an
from .config import COLORS, SERIES_COLORS

TITLE_SIZE = 11
LABEL_SIZE = 9


def color_map(names) -> dict:
    return {n: SERIES_COLORS[i % len(SERIES_COLORS)] for i, n in enumerate(names)}


def _ax(fig: Figure, title: str, xlabel: str = "", ylabel: str = ""):
    fig.clear()
    fig.set_facecolor("white")
    ax = fig.add_subplot(111)
    ax.set_title(title, fontsize=TITLE_SIZE, fontweight="bold", color=COLORS["text"], loc="left")
    ax.set_xlabel(xlabel, fontsize=LABEL_SIZE)
    ax.set_ylabel(ylabel, fontsize=LABEL_SIZE)
    ax.tick_params(labelsize=8)
    ax.grid(True, alpha=0.3)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    return ax


def _date_axis(ax):
    loc = mdates.AutoDateLocator(minticks=4, maxticks=10)
    ax.xaxis.set_major_locator(loc)
    ax.xaxis.set_major_formatter(mdates.ConciseDateFormatter(loc))


def empty(fig: Figure, title: str, message: str = "No data for the current selection.") -> None:
    ax = _ax(fig, title)
    ax.set_xticks([])
    ax.set_yticks([])
    ax.grid(False)
    ax.text(0.5, 0.5, message, ha="center", va="center", fontsize=10, color=COLORS["muted"],
            transform=ax.transAxes)
    _layout(fig)


def _layout(fig):
    """Use tight_layout unless the figure already re-lays itself out (constrained)."""
    if fig.get_layout_engine() is None:
        fig.tight_layout()


def _done(fig, ax=None, legend=True):
    if ax is not None and legend and ax.get_legend_handles_labels()[0]:
        ax.legend(fontsize=8, frameon=False)
    _layout(fig)


# ------------------------------------------------------------------ charts
def plot_daily(fig: Figure, df: pd.DataFrame, window: int = 7) -> None:
    """Chart 1: daily energy consumption with optional moving average."""
    title = "Daily Energy Consumption"
    daily = an.daily_energy(df)
    if daily.empty:
        return empty(fig, title)
    ax = _ax(fig, title, "Date", "Energy (kWh/day)")
    ax.plot(daily.index, daily.values, marker="o", ms=3, lw=1.6, color=COLORS["cyan"], label="Daily energy")
    ma = an.moving_average(daily.values, window)
    if ma.size:
        ax.plot(daily.index[window - 1:], ma, lw=2, ls="--", color=COLORS["amber"],
                label=f"{window}-day moving average")
    ax.set_ylim(bottom=0)
    _date_axis(ax)
    _done(fig, ax)


def plot_building_energy(fig: Figure, summary: pd.DataFrame, colors: dict | None = None) -> None:
    """Chart 2: building-wise total energy (horizontal bars, zero baseline)."""
    title = "Building-Wise Energy Comparison"
    if summary.empty:
        return empty(fig, title)
    s = summary.sort_values("energy_kwh")
    ax = _ax(fig, title, "Total energy (kWh)", "")
    cols = [(colors or {}).get(n, COLORS["teal"]) for n in s["building_name"]]
    bars = ax.barh(range(len(s)), s["energy_kwh"], color=cols, label="Total energy")
    ax.set_yticks(range(len(s)))
    ax.set_yticklabels([n.replace(" ", "\n", 1) for n in s["building_name"]], fontsize=8)
    for bar, v, share in zip(bars, s["energy_kwh"], s["share_pct"]):
        ax.text(bar.get_width(), bar.get_y() + bar.get_height() / 2,
                f" {v:,.0f} kWh ({share:.1f}%)", va="center", fontsize=8)
    ax.set_xlim(0, s["energy_kwh"].max() * 1.55)
    ax.grid(axis="y", alpha=0)
    _done(fig, ax, legend=False)


def plot_hourly_profile(fig: Figure, df: pd.DataFrame, colors: dict | None = None) -> None:
    """Chart 3: average energy for each hour of the day per building."""
    title = "Hourly Consumption Profile (average per hour)"
    prof = an.hourly_profile(df)
    if prof.empty:
        return empty(fig, title)
    ax = _ax(fig, title, "Hour of day", "Average energy per hour (kWh)")
    for name in prof.columns:
        ax.plot(prof.index, prof[name], marker=".", lw=1.6, label=name, color=(colors or {}).get(name))
    ax.set_xticks(range(0, 24, 2))
    ax.set_xlim(0, 23)
    ax.set_ylim(bottom=0)
    _done(fig, ax)


def plot_cost(fig: Figure, summary: pd.DataFrame, tariff: float, colors: dict | None = None) -> None:
    """Chart 4: estimated cost by building."""
    title = f"Estimated Energy Cost by Building (flat ₹{tariff:g}/kWh)"
    if summary.empty:
        return empty(fig, title)
    s = summary.sort_values("cost_inr", ascending=False)
    ax = _ax(fig, title, "", "Estimated cost (₹)")
    cols = [(colors or {}).get(n, COLORS["teal"]) for n in s["building_name"]]
    bars = ax.bar(range(len(s)), s["cost_inr"], color=cols)
    ax.set_xticks(range(len(s)))
    ax.set_xticklabels([n.replace(" ", "\n", 1) for n in s["building_name"]], fontsize=8)
    for bar, v in zip(bars, s["cost_inr"]):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height(), f"₹{v:,.0f}",
                ha="center", va="bottom", fontsize=8)
    ax.set_ylim(0, s["cost_inr"].max() * 1.15)
    ax.yaxis.set_major_formatter(lambda v, _: f"{v:,.0f}")
    ax.grid(axis="x", alpha=0)
    _done(fig, ax, legend=False)


def plot_heatmap(fig: Figure, df: pd.DataFrame) -> None:
    """Chart 5: energy by date (rows) and hour (columns)."""
    title = "Energy Consumption Heatmap (selected buildings)"
    m = an.heatmap_matrix(df)
    if m.empty:
        return empty(fig, title)
    ax = _ax(fig, title, "Hour of day", "Date")
    ax.grid(False)
    img = ax.imshow(np.ma.masked_invalid(m.to_numpy(dtype=float)), aspect="auto", cmap="viridis",
                    interpolation="nearest", vmin=0)
    ax.set_xticks(range(0, 24, 2))
    step = max(1, len(m) // 12)
    ax.set_yticks(range(0, len(m), step))
    ax.set_yticklabels([pd.Timestamp(d).strftime("%d %b") for d in m.index[::step]], fontsize=7)
    cb = fig.colorbar(img, ax=ax, pad=0.01)
    cb.set_label("Energy (kWh)", fontsize=LABEL_SIZE)
    cb.ax.tick_params(labelsize=7)
    _layout(fig)


def plot_peak_demand(fig: Figure, df: pd.DataFrame, top_n: int = 10) -> None:
    """Chart 6: campus interval-average demand with the highest readings marked."""
    title = "Peak Demand Analysis (1-hour interval-average demand)"
    s = an.campus_demand_series(df)
    if s.empty:
        return empty(fig, title, "No complete timestamps for the current selection.")
    ax = _ax(fig, title, "Date", "Demand (kW)")
    ax.plot(s.index, s.values, lw=0.9, color=COLORS["slate_light"], label="Interval-average demand")
    top = s.nlargest(min(top_n, len(s)))
    ax.scatter(top.index, top.values, color=COLORS["red"], zorder=3, s=28, label=f"Top {len(top)} readings")
    ax.axhline(s.mean(), color=COLORS["teal"], ls="--", lw=1.4, label=f"Average power {s.mean():.1f} kW")
    pk = top.index[0]
    ax.annotate(f"Max {top.iloc[0]:.1f} kW\n{pk:%d %b %H:%M}", (pk, top.iloc[0]),
                textcoords="offset points", xytext=(10, -28), fontsize=8,
                arrowprops={"arrowstyle": "->", "color": COLORS["muted"]})
    ax.set_ylim(0, s.max() * 1.12)
    _date_axis(ax)
    _done(fig, ax)


MARKERS = {"High consumption": ("^", "#D55E00"),
           "Unexpected off-hours consumption": ("D", "#CC79A7"),
           "Sudden demand increase": ("*", "#B91C1C"),
           "Unusually low reading": ("v", "#0072B2")}


def plot_anomalies(fig: Figure, df: pd.DataFrame, anomalies: pd.DataFrame, colors: dict | None = None) -> None:
    """Chart 7: power readings with anomalies shown by category-specific markers."""
    title = "Anomaly Visualization (IQR rule, building x day type x hour)"
    if df.empty:
        return empty(fig, title)
    ax = _ax(fig, title, "Date", "Interval-average power (kW)")
    for (bid, name), g in df.groupby(["building_id", "building_name"]):
        ax.plot(g["timestamp"], g["average_power_kw"], lw=0.7, alpha=0.55,
                color=(colors or {}).get(name), label=name)
    for cat, g in anomalies.groupby("category"):
        mk, col = MARKERS.get(cat, ("o", COLORS["amber"]))
        ax.scatter(g["timestamp"], g["average_power_kw"], marker=mk, s=70, color=col,
                   edgecolor="black", linewidth=0.6, zorder=4, label=f"{cat} ({len(g)})")
    _date_axis(ax)
    if ax.get_legend_handles_labels()[0]:
        ax.legend(fontsize=7, frameon=False, ncol=3, loc="upper left")
    ax.set_ylim(0, df["average_power_kw"].max() * 1.45)
    _layout(fig)


def plot_weekday_weekend(fig: Figure, ww: pd.DataFrame) -> None:
    """Chart 8: average daily energy on weekdays vs weekends per building."""
    title = "Weekday vs Weekend: Average Daily Energy"
    if ww.empty or ww.isna().all().all():
        return empty(fig, title)
    ax = _ax(fig, title, "", "Average energy per day (kWh/day)")
    x = np.arange(len(ww))
    w = 0.38
    ax.bar(x - w / 2, ww["Weekday"].fillna(0), w, label="Weekday (Mon-Fri)", color=COLORS["cyan"])
    ax.bar(x + w / 2, ww["Weekend"].fillna(0), w, label="Weekend (Sat-Sun)", color=COLORS["amber"])
    ax.set_xticks(x)
    ax.set_xticklabels([n.replace(" ", "\n", 1) for n in ww.index], fontsize=8)
    ax.set_ylim(bottom=0)
    ax.grid(axis="x", alpha=0)
    _done(fig, ax)
