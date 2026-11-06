import pandas as pd

from campus_energy.config import DEFAULT_BUILDINGS
from campus_energy.models import EnergyDataset, MeterRecord
from campus_energy.simulator import generate_dataset


def test_record_count(sim_df):
    assert len(sim_df) == 5 * 30 * 24 == 3600


def test_reproducible_with_seed():
    a, b = generate_dataset(seed=7), generate_dataset(seed=7)
    pd.testing.assert_frame_equal(a, b)
    assert not generate_dataset(seed=8)["average_power_kw"].equals(a["average_power_kw"])


def test_no_negative_values(sim_df):
    assert (sim_df["energy_kwh"] >= 0).all()
    assert (sim_df["average_power_kw"] >= 0).all()


def test_energy_equals_power_times_interval(sim_df):
    diff = (sim_df["energy_kwh"] - sim_df["average_power_kw"] * sim_df["interval_hours"]).abs()
    assert diff.max() < 1e-9


def test_timestamps_hourly_and_unique(sim_df):
    for _, g in sim_df.groupby("building_id"):
        ts = g["timestamp"].sort_values()
        assert ts.iloc[0] == pd.Timestamp("2026-10-01 00:00:00")
        assert ts.iloc[-1] == pd.Timestamp("2026-10-30 23:00:00")
        assert (ts.diff().dropna() == pd.Timedelta(hours=1)).all()


def test_building_identifiers(sim_df):
    expected = {b["building_id"]: b["name"] for b in DEFAULT_BUILDINGS}
    pairs = dict(sim_df[["building_id", "building_name"]].drop_duplicates().values)
    assert pairs == expected


def test_labelled_synthetic(sim_df):
    assert set(sim_df["data_source"]) == {"synthetic"}


def test_injected_anomalies_present(sim_df):
    assert (sim_df["injected_anomaly"] != "").sum() == 8
    assert generate_dataset(include_anomalies=False)["injected_anomaly"].eq("").all()


def test_weekend_lower_for_academic(sim_df):
    a = sim_df[sim_df["building_id"] == "B001"]
    weekend = a["timestamp"].dt.day_of_week >= 5
    noon = a["timestamp"].dt.hour == 11
    assert a[weekend & noon]["energy_kwh"].mean() < a[~weekend & noon]["energy_kwh"].mean()


def test_dataset_special_methods(sim_df):
    ds = EnergyDataset(sim_df.head(5))
    assert len(ds) == 5
    assert isinstance(ds[0], MeterRecord)
    assert [r.building_id for r in ds] == ["B001"] * 5
    assert ds[0].is_physically_valid()
