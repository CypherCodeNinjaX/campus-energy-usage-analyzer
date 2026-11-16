"""Data models: Building, MeterRecord, BuildingRegistry and EnergyDataset.

`EnergyDataset` is a small container class that wraps a Pandas DataFrame and
implements the special methods ``__len__``, ``__iter__`` and ``__getitem__``
so that a dataset can be used like a normal Python sequence:

    len(dataset)        -> number of accepted records
    for rec in dataset  -> yields MeterRecord objects
    dataset[0]          -> first MeterRecord

This keeps tabular speed (Pandas) while still offering a clear
object-oriented view of a single reading (MeterRecord).
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Iterator

import pandas as pd

from .config import DEFAULT_BUILDINGS, TIMESTAMP_FORMAT


@dataclass
class Building:
    """A campus building whose electricity use is analysed."""

    building_id: str
    name: str
    category: str = "general"

    def __post_init__(self) -> None:
        self.building_id = str(self.building_id).strip()
        self.name = str(self.name).strip()
        if not self.building_id:
            raise ValueError("Building ID must not be empty.")
        if not self.name:
            raise ValueError("Building name must not be empty.")


@dataclass
class MeterRecord:
    """One interval reading of one building.

    energy_kwh = average_power_kw x interval_hours
    """

    timestamp: datetime
    building_id: str
    building_name: str
    interval_hours: float
    average_power_kw: float
    energy_kwh: float
    data_source: str = "synthetic"
    estimated_cost_inr: float | None = None

    def is_physically_valid(self, rel_tol: float = 0.01, abs_tol: float = 0.01) -> bool:
        """Return True if values are finite, non-negative and consistent."""
        values = (self.interval_hours, self.average_power_kw, self.energy_kwh)
        if any(not math.isfinite(v) for v in values):
            return False
        if self.interval_hours <= 0 or self.average_power_kw < 0 or self.energy_kwh < 0:
            return False
        expected = self.average_power_kw * self.interval_hours
        return abs(expected - self.energy_kwh) <= max(abs_tol, rel_tol * abs(expected))

    def to_dict(self) -> dict:
        data = asdict(self)
        data["timestamp"] = self.timestamp.strftime(TIMESTAMP_FORMAT)
        return data


class BuildingRegistry:
    """Dictionary-based store of buildings keyed by building ID."""

    def __init__(self, buildings: list[Building] | None = None) -> None:
        self._buildings: dict[str, Building] = {}
        for b in buildings or []:
            self.add(b)

    @classmethod
    def default(cls) -> "BuildingRegistry":
        return cls([Building(**b) for b in DEFAULT_BUILDINGS])

    def __len__(self) -> int:
        return len(self._buildings)

    def __iter__(self) -> Iterator[Building]:
        return iter(self._buildings.values())

    def __contains__(self, building_id: str) -> bool:
        return building_id in self._buildings

    def get(self, building_id: str) -> Building | None:
        return self._buildings.get(building_id)

    def add(self, building: Building) -> None:
        if building.building_id in self._buildings:
            raise ValueError(f"Building ID '{building.building_id}' already exists.")
        if any(b.name.lower() == building.name.lower() for b in self._buildings.values()):
            raise ValueError(f"Building name '{building.name}' already exists.")
        self._buildings[building.building_id] = building

    def edit(self, building_id: str, name: str | None = None, category: str | None = None) -> Building:
        b = self._buildings.get(building_id)
        if b is None:
            raise KeyError(f"Unknown building ID '{building_id}'.")
        if name is not None:
            name = name.strip()
            if not name:
                raise ValueError("Building name must not be empty.")
            if any(o.name.lower() == name.lower() and o.building_id != building_id
                   for o in self._buildings.values()):
                raise ValueError(f"Building name '{name}' already exists.")
            b.name = name
        if category is not None:
            b.category = category
        return b

    def remove(self, building_id: str) -> Building:
        if building_id not in self._buildings:
            raise KeyError(f"Unknown building ID '{building_id}'.")
        return self._buildings.pop(building_id)

    def ids(self) -> list[str]:
        return list(self._buildings)

    def names(self) -> list[str]:
        return [b.name for b in self._buildings.values()]

    def name_to_id(self, name: str) -> str | None:
        for b in self._buildings.values():
            if b.name == name:
                return b.building_id
        return None

    @classmethod
    def from_dataframe(cls, df: pd.DataFrame, known: "BuildingRegistry | None" = None) -> "BuildingRegistry":
        """Build a registry from the unique (id, name) pairs of a dataset."""
        reg = cls()
        pairs = df[["building_id", "building_name"]].drop_duplicates("building_id")
        for bid, name in pairs.itertuples(index=False):
            category = "general"
            if known is not None and known.get(bid) is not None:
                category = known.get(bid).category
            reg.add(Building(bid, name, category))
        return reg


@dataclass
class EnergyDataset:
    """Validated readings plus a description of where they came from."""

    frame: pd.DataFrame
    source: str = "synthetic"
    description: str = ""
    meta: dict = field(default_factory=dict)

    def __len__(self) -> int:
        return len(self.frame)

    def __getitem__(self, index: int) -> MeterRecord:
        row = self.frame.iloc[index]
        return self._row_to_record(row)

    def __iter__(self) -> Iterator[MeterRecord]:
        for _, row in self.frame.iterrows():
            yield self._row_to_record(row)

    @staticmethod
    def _row_to_record(row: pd.Series) -> MeterRecord:
        cost = row.get("estimated_cost_inr")
        return MeterRecord(
            timestamp=pd.Timestamp(row["timestamp"]).to_pydatetime(),
            building_id=str(row["building_id"]),
            building_name=str(row["building_name"]),
            interval_hours=float(row["interval_hours"]),
            average_power_kw=float(row["average_power_kw"]),
            energy_kwh=float(row["energy_kwh"]),
            data_source=str(row.get("data_source", "unknown")),
            estimated_cost_inr=None if cost is None or pd.isna(cost) else float(cost),
        )
