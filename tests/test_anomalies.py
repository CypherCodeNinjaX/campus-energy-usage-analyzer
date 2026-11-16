import numpy as np
import pandas as pd
import pytest

from campus_energy import anomaly_detection as ad
from conftest import make_df

FORBIDDEN = ("failure", "theft", "fault", "malfunction", "broken", "defect")


def test_quartiles_match_numpy():
    vals = [1, 2, 3, 4, 5, 6, 7, 8]
    b = ad.iqr_bounds(vals)
    assert b["q1"] == pytest.approx(2.75) and b["q3"] == pytest.approx(6.25)
    assert b["iqr"] == pytest.approx(3.5)
    assert b["lower"] == pytest.approx(2.75 - 5.25) and b["upper"] == pytest.approx(6.25 + 5.25)


def test_outlier_identification():
    mask = ad.iqr_outlier_mask([10, 11, 12, 11, 10, 12, 11, 50, -20])
    assert mask.tolist() == [False] * 7 + [True, True]


def test_noise_floor():
    b = ad.iqr_bounds([10] * 7 + [10.5], min_iqr_fraction=0.1)
    assert b["iqr"] == 0 and b["iqr_used"] == pytest.approx(1.0)


def test_constant_values_not_flagged():
    df = make_df([(f"2026-10-01 {h:02d}:00", "B1", "A", 7.0) for h in range(24)])
    assert ad.detect_anomalies(df).empty
    assert ad.detect_anomalies(df, min_iqr_fraction=0).empty


def test_small_groups_use_fallback_or_skip():
    rows = [(f"2026-10-01 {h:02d}:00", "B1", "A", 10.0 + h % 3) for h in range(10)]
    rows.append(("2026-10-01 10:00", "B1", "A", 80.0))
    res = ad.detect_anomalies(make_df(rows))
    assert len(res) == 1 and "fallback" in res["group"].iloc[0]
    tiny = make_df([("2026-10-01 00:00", "B1", "A", 1.0), ("2026-10-01 01:00", "B1", "A", 99.0)])
    assert ad.detect_anomalies(tiny).empty          # < 4 samples: not evaluated


def test_detects_all_injected(sim_df):
    ev = ad.evaluate_against_injected(sim_df).set_index("method")
    assert ev.loc["Building x day type x hour", "injected_detected"] == 8
    # building-aware grouping beats one global campus threshold
    assert ev.loc["Building x day type x hour", "injected_detected"] > ev.loc["Global campus threshold", "injected_detected"]


def test_output_columns_and_no_fault_claims(sim_df):
    res = ad.detect_anomalies(sim_df)
    assert list(res.columns) == ad.ANOMALY_COLUMNS
    assert set(res["category"]) <= set(ad.CATEGORIES)
    text = " ".join(res[["category", "method", "group"]].astype(str).agg(" ".join, axis=1)).lower()
    assert not any(w in text for w in FORBIDDEN)
    assert "not proof" in ad.disclaimer()


def test_empty_input():
    assert ad.detect_anomalies(pd.DataFrame(columns=["timestamp"])).empty
    with pytest.raises(ValueError):
        ad.iqr_bounds([np.nan])
