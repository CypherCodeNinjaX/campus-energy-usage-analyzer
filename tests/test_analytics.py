import numpy as np
import pytest

from campus_energy import analytics as a
from conftest import make_df

ROWS = [("2026-10-01 00:00", "B1", "A", 10.0), ("2026-10-01 01:00", "B1", "A", 30.0),
        ("2026-10-01 00:00", "B2", "L", 5.0), ("2026-10-01 01:00", "B2", "L", 15.0),
        ("2026-10-02 00:00", "B1", "A", 20.0), ("2026-10-02 00:00", "B2", "L", 20.0)]


@pytest.fixture
def df():
    return make_df(ROWS)


def test_total_energy(df):
    assert a.total_energy(df) == pytest.approx(100.0)


def test_average_daily_energy_uses_observed_days(df):
    assert a.observed_days(df) == 2
    assert a.average_daily_energy(df) == pytest.approx(50.0)


def test_campus_demand_and_peak(df):
    s = a.campus_demand_series(df)
    assert list(s) == [15.0, 45.0, 40.0]
    kw, ts = a.peak_demand(df)
    assert kw == 45.0 and ts.hour == 1


def test_average_power(df):
    assert a.average_power(df) == pytest.approx(100.0 / 3)   # kWh / h


def test_incomplete_timestamps_excluded():
    d = make_df(ROWS + [("2026-10-03 00:00", "B1", "A", 99.0)])
    assert len(a.campus_demand_series(d)) == 3


def test_load_factor_needs_enough_samples(df):
    assert a.load_factor(df) is None
    rows = [(f"2026-10-01 {h:02d}:00", "B1", "A", 10.0 + (h == 5) * 10) for h in range(24)]
    lf = a.load_factor(make_df(rows))
    assert lf == pytest.approx((250 / 24) / 20 * 100)


def test_building_summary_and_shares(df):
    s = a.building_summary(df, tariff=8)
    assert s["share_pct"].sum() == pytest.approx(100.0)
    a_row = s[s.building_id == "B1"].iloc[0]
    assert a_row.energy_kwh == 60 and a_row.share_pct == pytest.approx(60)
    assert a_row.peak_kw == 30 and a_row.cost_inr == 480
    assert a_row.avg_power_kw == pytest.approx(20)


def test_percentage_change():
    assert a.percentage_change(120, 100) == pytest.approx(20)
    assert a.percentage_change(80, 100) == pytest.approx(-20)
    assert a.percentage_change(5, 0) is None


def test_filter_inclusive_end(df):
    assert len(a.filter_data(df, end="2026-10-01")) == 4
    assert len(a.filter_data(df, building_ids=["B2"])) == 3
    assert len(a.filter_data(df, start="2026-10-02")) == 2


def test_moving_average():
    assert np.allclose(a.moving_average([1, 2, 3, 4], 2), [1.5, 2.5, 3.5])
    assert a.moving_average([1, 2], 7).size == 0


def test_daily_and_weekday(sim_df):
    assert a.daily_energy(sim_df).sum() == pytest.approx(sim_df["energy_kwh"].sum())
    ww = a.weekday_weekend(sim_df)
    assert (ww["Weekday"] > ww["Weekend"]).all()


def test_completeness_and_compare(df, sim_df):
    c = a.data_completeness(df)
    assert not c["complete"].any()
    res = a.compare_periods(sim_df, ("2026-10-01", "2026-10-15"), ("2026-10-16", "2026-10-30"), 8)
    assert res["previous_days"] == res["current_days"] == 15
    assert res["previous_kwh"] + res["current_kwh"] == pytest.approx(sim_df["energy_kwh"].sum())


def test_kpis_empty_has_no_invented_values(df):
    k = a.kpis(df.iloc[0:0], 8, None)
    assert all(v is None for v in k.values())


def test_monthly_summary(sim_df):
    m = a.monthly_summary(sim_df, 8)
    assert len(m) == 5 and all(r["month"] == "2026-10" for r in m)
