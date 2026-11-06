import pytest

from campus_energy import cost_calculator as c
from conftest import make_df


def test_tariff_multiplication():
    assert c.energy_cost(250, 8) == 2000.0


def test_zero_consumption():
    assert c.energy_cost(0, 8) == 0.0


@pytest.mark.parametrize("bad", [-1, "abc", float("nan"), float("inf"), None])
def test_invalid_tariffs(bad):
    with pytest.raises(ValueError):
        c.validate_tariff(bad)


def test_negative_energy():
    with pytest.raises(ValueError):
        c.energy_cost(-1, 8)


def test_tariff_change():
    df = make_df([("2026-10-01 00:00", "B1", "A", 10.0), ("2026-10-01 01:00", "B2", "L", 5.0)])
    assert c.campus_cost(df, 8) == 120.0
    assert c.campus_cost(df, 9.5) == 142.5
    b = c.building_costs(df, 10)
    assert list(b["cost_inr"]) == [100.0, 50.0]


def test_floating_point_precision():
    assert c.energy_cost(0.1 + 0.2, 3) == pytest.approx(0.9)
    assert c.energy_cost(33.333, 7.77) == 259.0


def test_daily_monthly(sim_df):
    total = sim_df["energy_kwh"].sum() * 8
    assert c.daily_costs(sim_df, 8).sum() == pytest.approx(total, abs=0.5)
    m = c.monthly_costs(sim_df, 8)
    assert m["cost_inr"].iloc[0] == pytest.approx(total, abs=0.01)
