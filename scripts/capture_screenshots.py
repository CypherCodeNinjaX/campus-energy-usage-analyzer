"""Capture real screenshots of the running application (Linux + X11/Xvfb).

Usage:  xvfb-run -a -s "-screen 0 1320x840x24" python scripts/capture_screenshots.py
Requires ImageMagick's `import` command. Saves PNGs into screenshots/.
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from campus_energy.dashboard import EnergyApp  # noqa: E402

SHOTS = [("Overview", "Dashboard_Overview.png"), ("Building Comparison", "Building_Comparison.png"),
         ("Energy Analysis", "Energy_Analysis.png"), ("Anomaly Detection", "Anomaly_Detection.png"),
         ("Cost Calculator", "Cost_Analysis.png"), ("Data Management", "Data_Management.png"),
         ("Peak Demand", "Peak_Demand.png")]


def snap(app, name):
    app.update()
    app.after(400)
    app.update()
    out = ROOT / "screenshots" / name
    subprocess.run(["import", "-window", "root", "-crop", "1320x840+0+0", str(out)], check=True)
    print("saved", out)


if __name__ == "__main__":
    app = EnergyApp()
    app.geometry("1320x840+0+0")
    for v, d in zip(app.cmp_vars, ["2026-10-01", "2026-10-15", "2026-10-16", "2026-10-30"]):
        v.set(d)
    for page, name in SHOTS:
        app.show_page(page)
        if page == "Cost Calculator":
            app.on_compare_periods()
        if page == "Data Management":
            app.import_csv(ROOT / "data" / "sample_invalid_rows.csv")
            app.show_page(page)
        snap(app, name)
        if page == "Data Management":
            app.load_default_dataset()
    app.destroy()
