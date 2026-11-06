"""GUI tests. Skipped automatically when no display is available.

On Linux CI run them with:  xvfb-run -a python -m pytest
"""
import tkinter as tk

import pandas as pd
import pytest

pytestmark = pytest.mark.gui


@pytest.fixture(scope="module")
def app():
    try:
        root = tk.Tk()
        root.destroy()
    except tk.TclError:
        pytest.skip("No display available for Tkinter")
    from campus_energy.dashboard import PAGES, EnergyApp
    a = EnergyApp()
    a.messages = []
    a.show_error = lambda t, m: a.messages.append(("error", t, m))
    a.show_info = lambda t, m: a.messages.append(("info", t, m))
    a.ask_yes_no = lambda t, m: True
    a.update()
    yield a
    a.destroy()


def test_startup_loads_sample(app):
    assert len(app.data) == 3600
    assert app.kpi["Total consumption"].value.cget("text").endswith("kWh")
    assert app.kpi["Buildings monitored"].value.cget("text") == "5"


def test_navigation_all_pages(app):
    from campus_energy.dashboard import PAGES
    for p in PAGES:
        app.show_page(p)
        app.update()
        assert app.current_page == p
    assert not [m for m in app.messages if m[0] == "error"]


def test_filter_updates_kpis_and_charts(app):
    app.show_page("Overview")
    before = app.kpi["Total consumption"].value.cget("text")
    app.building_var.set("Central Library")
    app.start_var.set("2026-10-05")
    app.end_var.set("2026-10-11")
    assert app.apply_filters()
    app.update()
    assert set(app.filtered["building_id"]) == {"B004"}
    assert app.filtered["timestamp"].dt.normalize().nunique() == 7
    assert app.kpi["Total consumption"].value.cget("text") != before
    assert app.ov_daily.figure.axes[0].get_title(loc="left") == "Daily Energy Consumption"
    app.reset_filters()
    assert len(app.filtered) == 3600


def test_invalid_date_shows_error(app):
    app.messages.clear()
    app.start_var.set("31/10/2026")
    assert app.apply_filters() is False
    assert app.messages and app.messages[0][1] == "Invalid date"
    app.start_var.set("")
    app.apply_filters()


def test_empty_selection_no_invented_values(app):
    app.start_var.set("2030-01-01")
    app.end_var.set("2030-01-31")
    app.apply_filters()
    app.show_page("Overview")
    app.update()
    assert app.kpi["Total consumption"].value.cget("text") == "—"
    app.reset_filters()


def test_exports(app, tmp_path):
    app.export_filtered(tmp_path / "f.csv")
    assert len(pd.read_csv(tmp_path / "f.csv")) == 3600
    app.export_summary(tmp_path / "s.csv")
    app.export_anomalies(tmp_path / "a.csv")
    app.export_monthly_json(tmp_path / "m.json")
    app.export_pdf(tmp_path / "r.pdf")
    assert (tmp_path / "r.pdf").read_bytes()[:4] == b"%PDF"
    assert len(pd.read_csv(tmp_path / "a.csv")) == len(app.anomalies)


def test_tariff_change_updates_cost(app):
    app.set_tariff(10)
    assert app.settings["tariff"] == 10
    total = app.filtered["energy_kwh"].sum()
    app.show_page("Overview")
    app.update()
    assert f"{total * 10:,.2f}" in app.kpi["Total estimated cost"].value.cget("text")
    with pytest.raises(ValueError):
        app.set_tariff(-1)
    app.set_tariff(8)


def test_import_csv_with_errors(app):
    from campus_energy.config import DATA_DIR
    res = app.import_csv(DATA_DIR / "sample_invalid_rows.csv")
    assert app.validation is res and res.rejected_rows > 0
    assert len(app.data) == res.accepted_rows
    app.show_page("Data Management")
    app.update()
    assert app.val_table.tree.get_children()
    app.load_default_dataset()
    assert len(app.data) == 3600


def test_building_add_edit_remove(app):
    app.add_building("B006", "Hostel Block", "general")
    assert "Hostel Block" in app.building_cb["values"]
    app.edit_building("B006", "Boys Hostel", "general")
    assert "Boys Hostel" in app.building_cb["values"]
    with pytest.raises(ValueError):
        app.add_building("B007", "Central Library")       # duplicate name
    app.regenerate_dataset()
    assert len(app.data) == 6 * 720
    removed = app.remove_building("B006")
    assert removed == 720 and len(app.data) == 3600
    app.edit_building("B001", "Main Academic Block", "academic")
    assert (app.data.loc[app.data.building_id == "B001", "building_name"] == "Main Academic Block").all()
    app.edit_building("B001", "Academic Block", "academic")


def test_compare_periods_and_settings(app):
    r = app.compare_periods("2026-10-01", "2026-10-15", "2026-10-16", "2026-10-30")
    assert r["previous_days"] == 15
    with pytest.raises(ValueError):
        app.compare_periods("2026-10-15", "2026-10-01", "2026-10-16", "2026-10-30")
    with pytest.raises(ValueError):
        app.update_settings({"k": "abc"})
    app.update_settings({"k": 3.0})
    n3 = len(app.anomalies_all)
    app.update_settings({"k": 1.5})
    assert len(app.anomalies_all) >= n3
    assert "kWh" in app.written_summary()
