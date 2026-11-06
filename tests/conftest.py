import pandas as pd
import pytest

from campus_energy.simulator import generate_dataset


@pytest.fixture(scope="session")
def sim_df():
    return generate_dataset()


def make_df(rows):
    """rows: list of (timestamp, building_id, name, kw) with 1-hour intervals."""
    df = pd.DataFrame(rows, columns=["timestamp", "building_id", "building_name", "average_power_kw"])
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df["interval_hours"] = 1.0
    df["energy_kwh"] = df["average_power_kw"]
    df["data_source"] = "test"
    return df
