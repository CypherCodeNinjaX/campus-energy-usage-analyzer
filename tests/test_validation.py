import pandas as pd
import pytest

from campus_energy.data_loader import export_validation_summary, load_csv
from campus_energy.validation import ValidationError, validate_dataframe

HEADER = "timestamp,building_id,building_name,interval_hours,average_power_kw,energy_kwh\n"
GOOD = "2026-10-01 09:00:00,B001,Academic Block,1,12.5,12.5\n"


def _csv(tmp_path, body, header=HEADER):
    p = tmp_path / "in.csv"
    p.write_text(header + body, encoding="utf-8")
    return p


def test_valid_rows_accepted(tmp_path):
    r = load_csv(_csv(tmp_path, GOOD + "2026-10-01 10:00:00,B001,Academic Block,1,13.2,13.2\n"))
    assert (r.total_rows, r.accepted_rows, r.rejected_rows) == (2, 2, 0)
    assert r.accepted["timestamp"].iloc[1] == pd.Timestamp("2026-10-01 10:00:00")


@pytest.mark.parametrize("row,reason", [
    ("2026-10-01 09:00:00,B001,Academic Block,1,-5,-5\n", "negative power value"),
    ("2026-10-01 09:00:00,B001,Academic Block,1,5,-5\n", "negative energy consumption"),
    (",B001,Academic Block,1,5,5\n", "missing timestamp"),
    ("01/31/2026 9am,B001,Academic Block,1,5,5\n", "invalid date format"),
    ("2026-10-01 09:00:00,,Academic Block,1,5,5\n", "missing building identifier"),
    ("2026-10-01 09:00:00,B001,Academic Block,1,abc,5\n", "invalid numerical value in average_power_kw"),
    ("2026-10-01 09:00:00,B001,Academic Block,1,inf,inf\n", "infinite value in average_power_kw"),
    ("2026-10-01 09:00:00,B001,Academic Block,0,5,5\n", "invalid interval duration"),
    ("2026-10-01 09:00:00,B001,Academic Block,1,5,9\n", "inconsistent power and energy"),
    ("2026-10-01 09:00:00,B001,Academic Block,1,,5\n", "missing average_power_kw"),
])
def test_invalid_rows_rejected(tmp_path, row, reason):
    r = load_csv(_csv(tmp_path, row))
    assert r.accepted_rows == 0 and r.rejected_rows == 1
    assert reason in r.rejected["rejection_reason"].iloc[0]


def test_missing_value_not_replaced_by_zero(tmp_path):
    r = load_csv(_csv(tmp_path, GOOD + "2026-10-01 10:00:00,B001,Academic Block,1,,\n"))
    assert r.accepted_rows == 1
    assert r.rejected["average_power_kw"].iloc[0] == ""      # original value preserved
    assert r.rejected["csv_line"].iloc[0] == 3


def test_duplicates_detected(tmp_path):
    r = load_csv(_csv(tmp_path, GOOD + GOOD))
    assert r.accepted_rows == 1 and r.rejected_rows == 1
    assert "duplicate" in r.rejected["rejection_reason"].iloc[0]


def test_id_name_conflict(tmp_path):
    r = load_csv(_csv(tmp_path, GOOD + "2026-10-01 10:00:00,B001,Library,1,5,5\n"))
    assert r.rejected_rows == 1


def test_missing_columns_rejected(tmp_path):
    with pytest.raises(ValidationError, match="energy_kwh"):
        load_csv(_csv(tmp_path, "2026-10-01 09:00:00,B001,A,1,5\n",
                      header="timestamp,building_id,building_name,interval_hours,average_power_kw\n"))


def test_empty_and_missing_file(tmp_path):
    p = tmp_path / "empty.csv"
    p.write_text("")
    with pytest.raises(ValidationError):
        load_csv(p)
    with pytest.raises(ValidationError):
        load_csv(tmp_path / "nope.csv")


def test_validation_summary_export(tmp_path):
    r = load_csv(_csv(tmp_path, GOOD + GOOD))
    text = export_validation_summary(r, tmp_path / "s.csv").read_text()
    assert "Rejected rows,1" in text and "duplicate" in text


def test_sample_file_fully_valid():
    from campus_energy.data_loader import load_sample
    r = load_sample()
    assert r is not None and r.accepted_rows == 3600 and r.rejected_rows == 0


def test_invalid_examples_file():
    from campus_energy.config import DATA_DIR
    r = load_csv(DATA_DIR / "sample_invalid_rows.csv")
    assert r.rejected_rows > 0 and r.accepted_rows > 0
    assert r.total_rows == r.accepted_rows + r.rejected_rows


def test_validate_dataframe_directly():
    raw = pd.DataFrame({"timestamp": ["2026-10-01 00:00:00"], "building_id": ["B9"],
                        "building_name": ["X"], "interval_hours": ["0.5"],
                        "average_power_kw": ["10"], "energy_kwh": ["5"]})
    assert validate_dataframe(raw).accepted_rows == 1
