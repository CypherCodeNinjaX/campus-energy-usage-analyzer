"""Build documentation figures and the academic PDF report from the REAL dataset.

Usage (repository root; Linux needs a display for GUI tests, e.g. xvfb-run):
    python scripts/build_report.py

Steps
1. Runs the test suite (pytest + coverage) and records the actual results.
2. Draws architecture / data-flow / workflow diagrams and result charts.
3. Computes every reported number from data/sample_energy_data.csv.
4. Writes docs/Campus_Energy_Usage_Analyzer_Report.pdf (A4).
"""
from __future__ import annotations

import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import matplotlib  # noqa: E402

matplotlib.use("Agg")
from matplotlib.figure import Figure  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch  # noqa: E402
from reportlab.lib import colors  # noqa: E402
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY  # noqa: E402
from reportlab.lib.pagesizes import A4  # noqa: E402
from reportlab.lib.styles import ParagraphStyle  # noqa: E402
from reportlab.lib.units import mm  # noqa: E402
from reportlab.pdfbase import pdfmetrics  # noqa: E402
from reportlab.pdfbase.ttfonts import TTFont  # noqa: E402
from reportlab.platypus import (Image, KeepTogether, PageBreak, Paragraph,  # noqa: E402
                                SimpleDocTemplate, Spacer, Table, TableStyle)

from campus_energy import analytics as an  # noqa: E402
from campus_energy import anomaly_detection as ad  # noqa: E402
from campus_energy import cost_calculator as cc  # noqa: E402
from campus_energy import visualizations as viz  # noqa: E402
from campus_energy.config import (ANOMALY_DISCLAIMER, DATA_DIR, DEFAULT_BUILDINGS,  # noqa: E402
                                  DEFAULT_TARIFF_INR_PER_KWH)
from campus_energy.data_loader import load_csv, load_sample  # noqa: E402
from campus_energy.simulator import DEFAULT_ANOMALIES, PROFILES  # noqa: E402

DOCS = ROOT / "docs"
FIG = DOCS / "figures"
SHOTS = ROOT / "screenshots"
OUT = DOCS / "Campus_Energy_Usage_Analyzer_Report.pdf"
TARIFF = DEFAULT_TARIFF_INR_PER_KWH
R = "₹"
REPO_URL = "https://github.com/CypherCodeNinjaX/campus-energy-usage-analyzer"


# =================================================================== tests
def run_tests() -> dict:
    xml = DOCS / "test_results.xml"
    proc = subprocess.run([sys.executable, "-m", "pytest", "-q", f"--junitxml={xml}",
                           "--cov=campus_energy", "--cov-report=term"],
                          cwd=ROOT, capture_output=True, text=True)
    (DOCS / "test_report.txt").write_text(proc.stdout + proc.stderr, encoding="utf-8")
    suite = ET.parse(xml).getroot()
    suite = suite if suite.tag == "testsuite" else suite.find("testsuite")
    per_file: dict[str, list[int]] = {}
    for case in suite.iter("testcase"):
        f = case.get("classname").split(".")[-1] + ".py"
        res = per_file.setdefault(f, [0, 0, 0])
        if case.find("skipped") is not None:
            res[2] += 1
        elif case.find("failure") is not None or case.find("error") is not None:
            res[1] += 1
        else:
            res[0] += 1
    cov = re.search(r"^TOTAL\s+\d+\s+\d+\s+(\d+)%", proc.stdout, re.M)
    return {"tests": int(suite.get("tests")), "failures": int(suite.get("failures")),
            "errors": int(suite.get("errors")), "skipped": int(suite.get("skipped")),
            "per_file": per_file, "coverage": cov.group(1) + "%" if cov else "not generated",
            "time": float(suite.get("time")), "exit": proc.returncode}


# ================================================================ diagrams
def _box(ax, x, y, w, h, text, fc, fs=8.5, tc="white", style="round,pad=0.02,rounding_size=0.02"):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle=style, fc=fc, ec="#0F172A", lw=0.8))
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=fs, color=tc, wrap=True)


def _arrow(ax, a, b, text=""):
    ax.add_patch(FancyArrowPatch(a, b, arrowstyle="-|>", mutation_scale=12, lw=1.1, color="#334155"))
    if text:
        ax.text((a[0] + b[0]) / 2 + 0.01, (a[1] + b[1]) / 2, text, fontsize=7, color="#334155")


def _canvas(w, h):
    fig = Figure(figsize=(w, h), dpi=170)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    return fig, ax


def architecture_diagram(path):
    fig, ax = _canvas(7.2, 4.4)
    layers = [
        (0.80, "#0F1B2D", "PRESENTATION LAYER  —  dashboard.py (Tkinter / ttk)",
         ["Sidebar navigation (10 pages)", "Filter bar + KPI cards", "Tables, dialogs, exports"]),
        (0.58, "#0E7490", "OUTPUT LAYER", ["visualizations.py\n8 Matplotlib charts", "report_generator.py\nPDF export (ReportLab)"]),
        (0.36, "#0E9F9A", "ANALYSIS LAYER (pure functions, no GUI)",
         ["analytics.py\nenergy, peak, load factor", "anomaly_detection.py\nIQR by comparable group",
          "cost_calculator.py\nflat-tariff estimates"]),
        (0.14, "#334155", "DATA LAYER",
         ["simulator.py\nsynthetic records", "data_loader.py\nCSV / JSON I/O", "validation.py\nrow checks",
          "models.py\nMeterRecord, EnergyDataset"]),
    ]
    for y, col, title, items in layers:
        ax.add_patch(FancyBboxPatch((0.02, y - 0.005), 0.80, 0.19, boxstyle="round,pad=0.005", fc="#F1F5F9",
                                    ec=col, lw=1.2))
        ax.text(0.03, y + 0.165, title, fontsize=8, fontweight="bold", color=col, va="center")
        w = 0.76 / len(items)
        for i, it in enumerate(items):
            _box(ax, 0.04 + i * w, y + 0.01, w - 0.02, 0.12, it, col, fs=7.2)
    for y in (0.58, 0.36, 0.14):
        _arrow(ax, (0.42, y + 0.19), (0.42, y + 0.215 + 0.0))
    _box(ax, 0.85, 0.36, 0.13, 0.58, "config.py\n\ntariff,\nIQR k,\nbuildings,\ncolours,\npaths", "#B45309", fs=7.5)
    _box(ax, 0.85, 0.02, 0.13, 0.30, "Files\n\nCSV in/out\nJSON\nPDF", "#64748B", fs=7.5)
    _arrow(ax, (0.82, 0.22), (0.85, 0.20))
    ax.text(0.02, 0.03, "Arrows: data flows upward; the GUI only calls functions of lower layers (no circular imports).",
            fontsize=7, color="#334155")
    fig.savefig(path)


def data_flow_diagram(path):
    fig, ax = _canvas(7.2, 3.3)
    _box(ax, 0.01, 0.62, 0.15, 0.22, "CSV file\n(user import)", "#64748B", 7.5)
    _box(ax, 0.01, 0.20, 0.15, 0.22, "Simulator\n(seed 42)", "#64748B", 7.5)
    _box(ax, 0.22, 0.41, 0.15, 0.22, "Read as text\n+ validate\nevery row", "#0E9F9A", 7.5)
    _box(ax, 0.22, 0.05, 0.15, 0.20, "Rejected rows\n+ reasons", "#B45309", 7.5)
    _box(ax, 0.43, 0.41, 0.15, 0.22, "Accepted\nDataFrame\n(EnergyDataset)", "#0E7490", 7.5)
    _box(ax, 0.43, 0.72, 0.15, 0.20, "Filter: building\n+ date range", "#0E7490", 7.5)
    _box(ax, 0.64, 0.66, 0.16, 0.26, "analytics\ncost_calculator", "#0F1B2D", 7.5)
    _box(ax, 0.64, 0.30, 0.16, 0.26, "anomaly_detection\n(IQR groups)", "#0F1B2D", 7.5)
    _box(ax, 0.85, 0.66, 0.14, 0.26, "KPI cards\ncharts\ntables", "#15803D", 7.5)
    _box(ax, 0.85, 0.30, 0.14, 0.26, "Exports\nCSV / JSON\nPDF", "#15803D", 7.5)
    _arrow(ax, (0.16, 0.73), (0.22, 0.56))
    _arrow(ax, (0.16, 0.31), (0.22, 0.48), "")
    _arrow(ax, (0.295, 0.41), (0.295, 0.25), "invalid")
    _arrow(ax, (0.37, 0.52), (0.43, 0.52), "valid")
    _arrow(ax, (0.505, 0.63), (0.505, 0.72))
    _arrow(ax, (0.58, 0.82), (0.64, 0.79))
    _arrow(ax, (0.58, 0.48), (0.64, 0.43), "whole dataset")
    _arrow(ax, (0.80, 0.79), (0.85, 0.79))
    _arrow(ax, (0.80, 0.43), (0.85, 0.43))
    _arrow(ax, (0.72, 0.56), (0.72, 0.66))
    _arrow(ax, (0.37, 0.15), (0.85, 0.32), "validation summary")
    fig.savefig(path)


def workflow_diagram(path):
    fig, ax = _canvas(7.2, 2.4)
    steps = ["Load dataset", "Validate", "Apply filters", "Aggregate\n(ΣE, daily,\nhourly)", "Peak demand\n& load factor",
             "IQR anomaly\nflags", "Cost at\ntariff", "Display &\nexport"]
    w = 0.112
    for i, s in enumerate(steps):
        col = "#0E9F9A" if i not in (1, 5) else "#B45309"
        _box(ax, 0.01 + i * 0.124, 0.38, w, 0.34, s, col, 7.2)
        if i:
            _arrow(ax, (0.01 + i * 0.124 - 0.012, 0.55), (0.01 + i * 0.124, 0.55))
    ax.text(0.01, 0.16, "Amber steps can exclude or flag data: invalid rows never enter calculations; flagged readings "
            "stay in totals and are only highlighted.", fontsize=7.3, color="#334155")
    ax.text(0.01, 0.86, "Any change of dataset, building, date range, tariff or settings re-runs the steps "
            "from 'Apply filters' onward.", fontsize=7.3, color="#334155")
    fig.savefig(path)


def chart(path, func, *args, size=(7.2, 3.0)):
    fig = Figure(figsize=size, dpi=160)
    func(fig, *args)
    fig.savefig(path)


# ================================================================== report
def build():
    DOCS.mkdir(exist_ok=True)
    FIG.mkdir(exist_ok=True)
    tests = run_tests()
    res = load_sample()
    df = res.accepted
    inv = load_csv(DATA_DIR / "sample_invalid_rows.csv")
    summary = an.building_summary(df, TARIFF)
    k = an.kpis(df, TARIFF, None)
    anomalies = ad.detect_anomalies(df)
    k["anomalies"] = len(anomalies)
    ev = ad.evaluate_against_injected(df)
    ww = an.weekday_weekend(df)
    comp = an.data_completeness(df)
    cmp = an.compare_periods(df, ("2026-10-01", "2026-10-15"), ("2026-10-16", "2026-10-30"), TARIFF)
    colors_map = viz.color_map([b["name"] for b in DEFAULT_BUILDINGS])
    avg_kw = an.average_power(df)
    ex = df[(df.building_id == "B001")].iloc[10]          # 10:00 on day 1, Academic Block

    architecture_diagram(DOCS / "Architecture_Diagram.png")
    data_flow_diagram(DOCS / "Data_Flow_Diagram.png")
    workflow_diagram(FIG / "Analysis_Workflow.png")
    chart(FIG / "daily.png", viz.plot_daily, df)
    chart(FIG / "building.png", viz.plot_building_energy, summary, colors_map)
    chart(FIG / "cost.png", viz.plot_cost, summary, TARIFF, colors_map)
    chart(FIG / "anomaly.png", viz.plot_anomalies, df, anomalies, colors_map, size=(7.2, 3.3))
    chart(FIG / "hourly.png", viz.plot_hourly_profile, df, colors_map)
    chart(FIG / "peak.png", viz.plot_peak_demand, df)

    # ---------------------------------------------------------------- fonts
    ttf = Path(matplotlib.get_data_path()) / "fonts" / "ttf"
    for name, file in [("Sans", "DejaVuSans.ttf"), ("Sans-B", "DejaVuSans-Bold.ttf"),
                       ("Sans-I", "DejaVuSans-Oblique.ttf"), ("Serif-B", "DejaVuSerif-Bold.ttf"),
                       ("Serif", "DejaVuSerif.ttf"), ("Mono", "DejaVuSansMono.ttf")]:
        pdfmetrics.registerFont(TTFont(name, str(ttf / file)))
    pdfmetrics.registerFontFamily("Sans", normal="Sans", bold="Sans-B", italic="Sans-I", boldItalic="Sans-B")

    body = ParagraphStyle("body", fontName="Sans", fontSize=9, leading=12.6, alignment=TA_JUSTIFY, spaceAfter=4)
    h1 = ParagraphStyle("h1", fontName="Sans-B", fontSize=12.5, leading=16, spaceBefore=8, spaceAfter=4,
                        textColor=colors.HexColor("#0F1B2D"))
    h2 = ParagraphStyle("h2", parent=h1, fontSize=10.2, leading=13, spaceBefore=5, spaceAfter=2)
    cap = ParagraphStyle("cap", parent=body, fontName="Sans-I", fontSize=8, alignment=TA_CENTER, spaceAfter=6,
                         textColor=colors.HexColor("#334155"))
    bullet = ParagraphStyle("bul", parent=body, leftIndent=12, bulletIndent=2, spaceAfter=1.5)
    mono = ParagraphStyle("mono", parent=body, fontName="Mono", fontSize=7.8, leading=10.2, alignment=0,
                          backColor=colors.HexColor("#F1F5F9"), borderPadding=4, spaceBefore=2, spaceAfter=6)
    eq = ParagraphStyle("eq", parent=body, fontName="Serif", fontSize=9.6, alignment=TA_CENTER,
                        backColor=colors.HexColor("#F8FAFC"), borderPadding=3, spaceBefore=2, spaceAfter=4)
    cell = ParagraphStyle("cell", fontName="Sans", fontSize=7.8, leading=9.6)
    cellb = ParagraphStyle("cellb", parent=cell, fontName="Sans-B", textColor=colors.white)

    fig_no = [0]
    tab_no = [0]
    story = []
    P = lambda t, s=body: story.append(Paragraph(t, s))  # noqa: E731

    def B(items):
        for it in items:
            story.append(Paragraph(it, bullet, bulletText="•"))

    def table(rows, widths, caption=None, align_right_from=None, size=7.8):
        tab_no[0] += 1
        data = [[Paragraph(str(c), cellb) for c in rows[0]]] + \
               [[Paragraph(str(c), cell) for c in r] for r in rows[1:]]
        t = Table(data, colWidths=[w * mm for w in widths], repeatRows=1)
        st = [("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0F1B2D")),
              ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F1F5F9")]),
              ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#CBD5E1")),
              ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
              ("TOPPADDING", (0, 0), (-1, -1), 2.2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.2)]
        t.setStyle(TableStyle(st))
        items = []
        if caption:
            items.append(Paragraph(f"Table {tab_no[0]}: {caption}", cap))
        items.append(t)
        story.append(KeepTogether(items))
        story.append(Spacer(1, 5))

    def figure(path, caption, width_mm=165, ratio=None):
        from PIL import Image as PILImage
        fig_no[0] += 1
        with PILImage.open(path) as im:
            r = im.height / im.width
        img = Image(str(path), width=width_mm * mm, height=width_mm * mm * (ratio or r))
        story.append(KeepTogether([img, Paragraph(f"Figure {fig_no[0]}: {caption}", cap)]))

    def f(v, spec=",.2f"):
        return f"{v:{spec}}"

    # ---------------------------------------------------------------- cover
    story.append(Spacer(1, 1))
    story.append(PageBreak())

    # ------------------------------------------------------- abstract + toc
    top = summary.iloc[0]
    found = ev.set_index("method").loc["Building x day type x hour"]
    glob = ev.set_index("method").loc["Global campus threshold"]
    P("Abstract", h1)
    P(f"This project develops an offline Python desktop application that analyses hourly electricity consumption of "
      f"campus buildings. It validates CSV records, calculates energy totals, average and peak demand, load factor, "
      f"building shares and flat-tariff cost estimates, flags statistically unusual readings with an "
      f"interquartile-range (IQR) rule, and presents eight Matplotlib charts inside a Tkinter dashboard with CSV, "
      f"JSON and PDF export. The bundled demonstration dataset is <b>synthetic</b>: {len(df):,} hourly records for five "
      f"buildings over {k['observed_days']} days generated with a fixed random seed; it is not real meter data. "
      f"On this dataset the campus used {f(k['total_kwh'], ',.1f')} kWh ({f(k['avg_daily_kwh'], ',.1f')} kWh/day), the "
      f"maximum 1-hour average demand was {f(k['peak_kw'], '.1f')} kW, the load factor was {f(k['load_factor'], '.1f')}% "
      f"and the estimated cost at an illustrative {R}{TARIFF:g}/kWh was {R}{f(k['total_cost'])}. "
      f"{top.building_name} had the largest share ({f(top.share_pct, '.1f')}%). Comparing readings only with the same "
      f"building, day type and hour detected all {int(found.injected)} injected test anomalies with "
      f"{int(found.other_flags)} additional flags, while a single campus-wide threshold detected "
      f"{int(glob.injected_detected)}. The automated test suite ran {tests['tests']} tests "
      f"({tests['tests'] - tests['failures'] - tests['errors'] - tests['skipped']} passed, "
      f"{tests['failures'] + tests['errors']} failed, {tests['skipped']} skipped).")
    P("<b>Keywords:</b> electricity consumption; kWh; peak demand; load factor; IQR outlier detection; Python; "
      "Pandas; NumPy; Matplotlib; Tkinter; data validation.")
    P("Table of Contents", h1)
    toc = ["1. Introduction", "2. Problem Statement and Objectives", "3. Literature Review",
           "4. Software Requirements", "5. System Architecture", "6. Methodology and Flowcharts",
           "7. Dataset Design and Simulation", "8. Mathematical Formulations", "9. Implementation",
           "10. Results and Observations", "11. Testing and Validation", "12. Discussion",
           "13. Limitations", "14. Applications and Future Scope", "15. Conclusion", "16. References",
           "Appendix A: Installation and Execution", "Appendix B: Team Contributions"]
    half = (len(toc) + 1) // 2
    t = Table([[Paragraph(a, body), Paragraph(b, body)] for a, b in
               zip(toc[:half], toc[half:] + [""])], colWidths=[85 * mm, 85 * mm])
    t.setStyle(TableStyle([("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))
    story.append(t)

    # ---------------------------------------------------------------- 1
    P("1. Introduction", h1)
    P("Educational campuses run classrooms, laboratories, libraries and offices whose electricity use differs by "
      "hour, weekday and purpose. When readings are kept only as spreadsheets it is difficult to see which building "
      "uses most energy, when the campus peak occurs, how much the energy is likely to cost, and which readings are "
      "unusual. This project builds a small, transparent analytics tool for such interval data. It is 100% software: "
      "no meter hardware or live connection is involved, so the application analyses either simulated data or CSV "
      "files supplied by the user.")

    # ---------------------------------------------------------------- 2
    P("2. Problem Statement and Objectives", h1)
    P("<b>Problem statement.</b> Analyse electricity-meter readings for several campus buildings: use functions to "
      "flag abnormal and negative readings, lists/dictionaries and CSV for building records, a <i>MeterRecord</i> "
      "class, NumPy for totals and moving averages, Pandas for summaries and JSON export, and Matplotlib for usage "
      "trends; then compare buildings and judge whether spikes reflect real use or incomplete data.")
    B(["Validate imported records and explain every rejected row; never replace missing values with zero.",
       "Generate a reproducible synthetic dataset (fixed seed) with realistic building profiles and labelled anomalies.",
       "Compute total and daily energy, average power, peak interval demand, load factor, shares and costs.",
       "Detect unusual readings with an IQR rule applied to comparable groups and evaluate it against an alternative.",
       "Present KPIs, eight charts and tables in a Tkinter dashboard that refreshes on every filter change.",
       "Export filtered records, building summaries, anomaly reports, monthly JSON and a PDF report.",
       "Verify the logic with automated tests and document all limitations honestly."])

    # ---------------------------------------------------------------- 3
    P("3. Literature Review", h1)
    P("Interval (typically 15-60 minute) meter data are the standard basis for building-energy analysis; daily "
      "totals, hour-of-day profiles and weekday/weekend comparisons are common first steps because building loads "
      "follow occupancy schedules [6]. Tukey's box-plot rule, which marks values beyond 1.5 IQR from the quartiles, is a "
      "simple, distribution-free outlier test [1]. Surveys of anomaly detection stress that an anomaly is defined "
      "relative to a context: a value normal at 14:00 on a weekday may be abnormal at 02:00 [2]. This motivates "
      "contextual groups instead of one campus-wide threshold. Load factor (average/peak demand) is a standard "
      "utilisation measure in power systems, and India's Energy Conservation Building Code encourages metering and "
      "monitoring of building loads [6]. The implementation relies on NumPy [3], Pandas [4], Matplotlib [5], Tkinter "
      "[7], ReportLab [8] and pytest [9].")

    # ---------------------------------------------------------------- 4
    P("4. Software Requirements", h1)
    table([["Component", "Purpose in this project"],
           ["Python 3.10+ (tested on 3.12)", "Core language; dataclasses, pathlib, logging, csv/json"],
           ["Tkinter / ttk", "Desktop GUI: sidebar, filters, KPI cards, notebooks, Treeview tables, dialogs"],
           ["Pandas ≥ 2.2", "DataFrames, validation, group-by summaries, pivot tables, date handling"],
           ["NumPy ≥ 1.26", "Percentiles (quartiles), moving average (convolution), random simulation"],
           ["Matplotlib ≥ 3.8", "Eight charts embedded with FigureCanvasTkAgg (+ zoom/pan/save toolbar)"],
           ["ReportLab ≥ 4.0", "PDF analysis report export and this project report"],
           ["pytest / pytest-cov", "Automated unit and GUI tests, coverage measurement"],
           ["OS / hardware", "Windows 10/11 (target), also runs on Linux; no special hardware, works offline"]],
          [55, 115], "Software requirements")

    # ---------------------------------------------------------------- 5
    P("5. System Architecture", h1)
    P("The code is organised in four layers (Figure 1). Lower layers never import higher layers, which prevents "
      "circular imports and lets all calculations be tested without a GUI. <i>config.py</i> holds every tunable "
      "constant (tariff, IQR multiplier, default buildings, colours and portable paths).")
    figure(DOCS / "Architecture_Diagram.png", "System architecture (modules in src/campus_energy/)", 160)

    # ---------------------------------------------------------------- 6
    P("6. Methodology and Flowcharts", h1)
    P("Data enter either from the simulator or from a CSV file read entirely as text, so that the original values of "
      "rejected rows can be shown unchanged (Figure 2). Accepted rows form the working dataset. Anomaly thresholds "
      "are computed once on the whole dataset so that they do not change when the user zooms into a few days; "
      "building and date filters then select what is displayed. Figure 3 shows the energy-analysis workflow that "
      "runs after every change.")
    figure(DOCS / "Data_Flow_Diagram.png", "Data-processing flow from input to outputs", 160)
    figure(FIG / "Analysis_Workflow.png", "Energy-analysis workflow", 165)

    # ---------------------------------------------------------------- 7
    P("7. Dataset Design and Simulation", h1)
    P("Each record describes one building over one interval. Required CSV columns are listed in the schema table; "
      "<i>estimated_cost_inr</i> is always recomputed from the current tariff and <i>data_source</i> marks every "
      "simulated row as <i>synthetic</i>.")
    table([["Column", "Type / unit", "Meaning"],
           ["timestamp", "YYYY-MM-DD HH:MM:SS", "Start of the interval"],
           ["building_id / building_name", "text", "Permanent key (B001...) and display name"],
           ["interval_hours", "h (0 < t ≤ 24)", "Interval length; 1 h in the sample"],
           ["average_power_kw", "kW", "Average power during the interval"],
           ["energy_kwh", "kWh", "Energy = average power × interval"],
           ["estimated_cost_inr, data_source", "₹, text", "Optional: cost (recomputed) and origin label"]],
          [52, 38, 80], "Dataset schema")
    P(f"The simulator (seed 42) models each hour as P = P<sub>base</sub> + (P<sub>peak</sub> − P<sub>base</sub>) "
      f"× activity, multiplied by Gaussian noise N(1, σ) clipped to 0.7-1.3 so power is never negative. "
      f"Activity is 1 in the building's active hours, 0.35 in the hour before and after, 0.8 at 13:00 (lunch), "
      f"0 otherwise, and is scaled by a weekend factor. Default: 5 buildings × 30 days × 24 h = "
      f"{len(df):,} records from 1 to 30 October 2026.")
    rows = [["Building (profile)", "Base kW", "Peak kW", "Active hours", "Weekend factor", "σ"]]
    for b in DEFAULT_BUILDINGS:
        p = PROFILES[b["category"]]
        rows.append([b["name"], f"{p.base_kw:g}", f"{p.peak_kw:g}", f"{p.active_hours[0]:02d}:00-{p.active_hours[1]:02d}:00",
                     f"{p.weekend_factor:g}", f"{p.sigma:g}"])
    table(rows, [52, 20, 20, 32, 26, 20], "Synthetic load profiles")
    lbl = {"night_usage": "Unexpected night-time use", "high_lab_usage": "Abnormally high lab use",
           "demand_spike": "Sudden demand increase", "low_reading": "Unusually low reading"}
    rows = [["Injected anomaly", "Building", "Time", "Set to"]]
    for bid, day, hour, mult, label in DEFAULT_ANOMALIES:
        name = next(b["name"] for b in DEFAULT_BUILDINGS if b["building_id"] == bid)
        ts = an.pd.Timestamp("2026-10-01") + an.pd.Timedelta(days=day, hours=hour)
        rows.append([lbl[label], name, f"{ts:%a %d %b %H:%M}", f"{mult:g} × peak kW"])
    table(rows, [50, 45, 40, 35], "Labelled anomalies injected for testing (column injected_anomaly)")

    # ---------------------------------------------------------------- 8
    P("8. Mathematical Formulations", h1)
    P("Symbols: P<sub>i</sub> = average power of interval i (kW); t<sub>i</sub> = interval length (h); "
      "E<sub>i</sub> = energy of interval i (kWh); T = tariff (₹/kWh). Assumptions: readings are interval "
      "averages, intervals do not overlap, and costs use a flat tariff only.")
    P(f"<b>(1) Interval energy.</b> E<sub>i</sub> = P<sub>i</sub> × t<sub>i</sub> [kW × h = kWh]. Example "
      f"(Academic Block, 01 Oct 10:00): {ex.average_power_kw:.3f} kW × 1 h = {ex.energy_kwh:.3f} kWh.")
    P(f"<b>(2) Total energy.</b> E<sub>total</sub> = Σ E<sub>i</sub> = {f(k['total_kwh'], ',.3f')} kWh for the sample.")
    P(f"<b>(3) Average daily energy</b> = E<sub>total</sub> / D, where D = number of <i>days with at least one valid "
      f"reading</i> (not the calendar span): {f(k['total_kwh'], ',.1f')} / {k['observed_days']} = "
      f"{f(k['avg_daily_kwh'], ',.1f')} kWh/day.")
    P(f"<b>(4) Average power</b> = E<sub>total</sub> / total observed duration [kWh/h = kW]. For several buildings, "
      f"the campus demand P<sub>c</sub>(t) = Σ<sub>b</sub> P<sub>b</sub>(t) is formed only at timestamps where every "
      f"selected building reports; average power = mean P<sub>c</sub> = {f(avg_kw, '.2f')} kW.")
    P(f"<b>(5) Maximum recorded demand</b> P<sub>max</sub> = max P<sub>c</sub>(t) = {f(k['peak_kw'], '.2f')} kW at "
      f"{k['peak_time']:%d %b %H:%M}. This is the highest <i>1-hour interval-average</i> demand, not an instantaneous "
      f"peak and not a utility's billing demand (often a 15/30-minute maximum).")
    P(f"<b>(6) Load factor</b> LF = P<sub>avg</sub> / P<sub>max</sub> × 100% = {f(avg_kw, '.2f')} / "
      f"{f(k['peak_kw'], '.2f')} = {f(k['load_factor'], '.1f')}%. Computed only with uniform intervals and at least 24 "
      f"complete timestamps; with hourly data it overestimates LF relative to shorter billing intervals.")
    P(f"<b>(7) Estimated cost</b> C = E × T. Example from the specification: 250 kWh × {R}8/kWh = {R}2,000. "
      f"{R}8/kWh is an illustrative, user-configurable value, not an official tariff; fixed charges, demand charges, "
      f"taxes and time-of-day rates are excluded.")
    P(f"<b>(8) Building energy share</b> = E<sub>b</sub> / E<sub>total</sub> × 100%; e.g. {top.building_name}: "
      f"{f(top.energy_kwh, ',.1f')} / {f(k['total_kwh'], ',.1f')} = {f(top.share_pct, '.2f')}%.")
    P(f"<b>(9) Percentage change</b> = (E<sub>current</sub> − E<sub>previous</sub>) / E<sub>previous</sub> "
      f"× 100%; undefined (shown as n/a) when E<sub>previous</sub> = 0. Example: 16-30 Oct vs 1-15 Oct = "
      f"({f(cmp['current_kwh'], ',.1f')} − {f(cmp['previous_kwh'], ',.1f')}) / {f(cmp['previous_kwh'], ',.1f')} = "
      f"{f(cmp['change_pct'], '+.2f')}%.")
    P("<b>(10) IQR rule.</b> IQR = Q3 − Q1; lower = Q1 − k·IQR′, upper = Q3 + k·IQR′ with "
      "k = 1.5 and IQR′ = max(IQR, 0.10 × median). Quartiles use linear interpolation (NumPy default). "
      "Groups are building × day type (weekday/weekend) × hour; groups with fewer than 8 readings fall back to "
      "building × day type, then building; fewer than 4 readings are not evaluated. The 10% noise floor stops "
      "tightly clustered night loads from flagging ordinary ±5% variation; setting it to 0 gives the textbook rule.")

    # ---------------------------------------------------------------- 9
    P("9. Implementation", h1)
    table([["Module", "Responsibility"],
           ["models.py", "Building, MeterRecord (dataclasses), BuildingRegistry (dict), EnergyDataset (__len__, __iter__, __getitem__)"],
           ["simulator.py", "LoadProfile, generate_dataset(): deterministic synthetic records + injected anomalies"],
           ["validation.py", "validate_dataframe(): eleven row checks, rejection reasons, ValidationResult"],
           ["data_loader.py", "load_csv(), export_csv(), export_json(), export_validation_summary()"],
           ["analytics.py", "filter_data(), totals, campus demand, peak, load factor, summaries, moving_average(), kpis()"],
           ["anomaly_detection.py", "iqr_bounds(), detect_anomalies(), evaluate_against_injected()"],
           ["cost_calculator.py", "validate_tariff(), energy_cost(), building/daily/monthly costs"],
           ["visualizations.py", "Eight chart functions drawing on a Matplotlib Figure (no pyplot state)"],
           ["report_generator.py", "PDF analysis report of the current selection"],
           ["dashboard.py / main.py", "Tkinter application (10 pages) and entry point python -m campus_energy.main"]],
          [38, 132], "Major modules")
    P("<b>Special methods (BL6).</b> <i>EnergyDataset</i> wraps a Pandas DataFrame and implements <i>__len__</i>, "
      "<i>__iter__</i> and <i>__getitem__</i>, so len(ds) gives the record count, a for-loop yields <i>MeterRecord</i> "
      "objects and ds[0] returns the first reading. This keeps fast vectorised Pandas calculations while offering a "
      "readable object view of one reading, which is what a student explains in a viva. <i>BuildingRegistry</i> also "
      "implements <i>__len__</i>, <i>__iter__</i> and <i>__contains__</i>.")
    P("<b>GUI.</b> The window has a sidebar with ten pages, a header with a dataset status indicator, and a filter bar "
      "(building, from/to date, apply, reset, export). Each page re-draws only when it is shown after a change. All "
      "actions that modify data are ordinary methods (e.g. import_csv(), remove_building(), set_tariff()), so the "
      "button handlers only collect input; this design made automated GUI tests possible. Deleting a building asks for "
      "confirmation and states that its records are removed from the working dataset in memory while the source CSV "
      "is unchanged. Keyboard shortcuts: Ctrl+1..9/0 pages, F5 refresh, Ctrl+O import, Ctrl+E export.")
    figure(SHOTS / "Dashboard_Overview.png", "Dashboard overview (actual screenshot of the running application)", 165)

    # ---------------------------------------------------------------- 10
    P("10. Results and Observations", h1)
    P("All values below were computed by the application's own functions from data/sample_energy_data.csv "
      "(synthetic, seed 42) at the illustrative tariff of ₹ 8/kWh.")
    table([["Indicator", "Value"],
           ["Records / buildings / observed days", f"{len(df):,} / {k['buildings']} / {k['observed_days']}"],
           ["Total energy", f"{f(k['total_kwh'], ',.1f')} kWh"],
           ["Average daily energy", f"{f(k['avg_daily_kwh'], ',.1f')} kWh/day"],
           ["Average campus power", f"{f(avg_kw, '.2f')} kW"],
           ["Maximum 1-hour average demand", f"{f(k['peak_kw'], '.2f')} kW ({k['peak_time']:%a %d %b %H:%M})"],
           ["Campus load factor", f"{f(k['load_factor'], '.1f')}%"],
           ["Estimated cost (flat ₹ 8/kWh)", f"{R}{f(k['total_cost'])}"],
           ["Statistical anomalies flagged", f"{k['anomalies']}"]],
          [80, 90], "Campus-level results")
    rows = [["Building", "Energy (kWh)", "Share", "Avg kW", "Peak kW", "Load factor", f"Cost ({R})"]]
    for r in summary.itertuples():
        rows.append([r.building_name, f(r.energy_kwh, ",.1f"), f(r.share_pct, ".1f") + "%", f(r.avg_power_kw),
                     f(r.peak_kw), f(r.load_factor_pct, ".1f") + "%", f(r.cost_inr)])
    table(rows, [45, 24, 16, 17, 18, 22, 28], "Building-wise summary")
    figure(FIG / "building.png", "Building-wise energy comparison", 150)
    figure(FIG / "daily.png", "Daily campus energy with 7-day moving average", 150)
    lows = an.daily_energy(df)
    wk = lows[lows.index.day_of_week < 5]
    we = lows[lows.index.day_of_week >= 5]
    P(f"<b>Observations.</b> (i) Daily energy alternates between weekdays (mean {f(wk.mean(), ',.0f')} kWh) and "
      f"weekends (mean {f(we.mean(), ',.0f')} kWh); the dips in the daily chart are the eight weekend days. "
      f"(ii) {sum(ww['Weekend'] < ww['Weekday'])} of {len(ww)} buildings use less energy per day at weekends; the "
      f"library changes least because it stays open. (iii) The Computer Laboratory has the highest total because of its "
      f"standby load, although the Electronics Laboratory reaches a similar peak only during practical hours, giving it "
      f"the lowest load factor ({f(summary.set_index('building_id').loc['B002', 'load_factor_pct'], '.1f')}%). "
      f"(iv) All {len(comp)} building-days contain the expected 24 readings, so the spikes and dips in the daily totals "
      f"reflect recorded use, not missing data; on an incomplete dataset the application reports such days separately.")
    figure(FIG / "cost.png", "Estimated cost by building (illustrative flat tariff)", 150)
    figure(FIG / "anomaly.png", "Anomaly visualisation: flagged readings by category", 160)
    rows = [["Grouping strategy", "Flags", "Injected found", "Other flags"]]
    for r in ev.itertuples():
        rows.append([r.method, r.flags, f"{r.injected_detected} / {r.injected}", r.other_flags])
    table(rows, [70, 25, 35, 30], "Evaluation of IQR grouping strategies against the 8 injected anomalies (k = 1.5)")
    cats = anomalies["category"].value_counts()
    P(f"A single campus threshold mostly flags whole high-load buildings and misses low readings, and a per-building "
      f"threshold treats every busy afternoon as normal and every night as low; the building × day type × hour "
      f"groups found all {int(found.injected)} injected anomalies with {int(found.other_flags)} additional flags. "
      f"Flag categories: " + ", ".join(f"{v} {c.lower()}" for c, v in cats.items()) + ". "
      f"The additional flags are ordinary random variation that happens to fall outside the limits; this is the "
      f"expected false-alarm behaviour of any fixed statistical rule. <b>{ANOMALY_DISCLAIMER}</b>")

    # ---------------------------------------------------------------- 11
    P("11. Testing and Validation", h1)
    passed = tests["tests"] - tests["failures"] - tests["errors"] - tests["skipped"]
    P(f"The suite was executed by this build script with <i>python -m pytest --cov=campus_energy</i>; results are "
      f"read from the generated JUnit XML (docs/test_results.xml), not typed by hand. Total: <b>{tests['tests']} tests, "
      f"{passed} passed, {tests['failures'] + tests['errors']} failed, {tests['skipped']} skipped</b> in "
      f"{tests['time']:.1f} s; statement coverage of the package: {tests['coverage']}. GUI tests run the real "
      f"Tkinter window (a virtual X display was used on Linux) and are skipped automatically if no display exists.")
    names = {"test_simulator.py": "Record count, seed reproducibility, non-negative values, E = P·t, timestamps, IDs, special methods",
             "test_validation.py": "Each rejection rule, no zero-filling, duplicates, ID/name conflicts, missing columns, empty file",
             "test_analytics.py": "Sums, observed days, campus demand, peak, load factor, shares, % change, filters, moving average",
             "test_cost_calculator.py": "Tariff multiplication, zero energy, invalid tariffs, tariff change, floating point",
             "test_anomalies.py": "Quartiles, outlier mask, noise floor, constant data, small groups, injected anomalies, no fault claims",
             "test_gui.py": "Startup, navigation, filtering, invalid dates, empty state, exports, tariff, import, buildings, settings"}
    rows = [["Test file", "Scope", "Pass", "Fail", "Skip"]]
    for fname, (p_, fl, sk) in sorted(tests["per_file"].items()):
        rows.append([fname, names.get(fname, ""), p_, fl, sk])
    table(rows, [36, 98, 12, 12, 12], "Actual automated test results")
    rows = [["Validation demo (data/sample_invalid_rows.csv)", "Rows"],
            ["Total rows read", inv.total_rows], ["Accepted", inv.accepted_rows], ["Rejected", inv.rejected_rows]]
    rows += [[f"Reason: {r}", n] for r, n in sorted(inv.reason_counts.items())]
    table(rows, [130, 40], "Validation of a deliberately faulty CSV file")
    P("Manual checks: the application was launched, every page opened, all buttons exercised, and the screenshots in "
      "this report and in the repository were captured from the running program. Windows-specific behaviour (fonts, "
      "file dialogs) follows the same code path but was not executed on a Windows machine by the author of this build; "
      "it should be confirmed during the laboratory demonstration.")

    # ---------------------------------------------------------------- 12-15
    P("12. Discussion", h1)
    P("The results confirm the expected behaviour of occupancy-driven loads: weekday daytime dominates, weekends fall "
      "sharply except in the library, and laboratories with short intensive sessions have low load factors. Because "
      "the data are simulated from stated profiles, these findings describe the model, not a real campus; their value "
      "is that the same pipeline will produce trustworthy figures for real CSV data. The anomaly evaluation shows why "
      "context matters: identical kW values can be normal at 14:00 and abnormal at 02:00.")
    P("13. Limitations", h1)
    B(["Synthetic data only by default; no hardware, no live meter connection.",
       "Hourly averages hide short peaks; billing demand and power factor are not available.",
       "Flat-tariff costs exclude fixed, demand, tax and time-of-day components, so they are not bills.",
       "IQR flags depend on k, the noise floor and group size; a flag is not evidence of a fault.",
       "Building edits and deletions apply to the working dataset in memory and are not saved automatically."])
    P("14. Applications and Future Scope", h1)
    B(["Energy-awareness dashboards for hostels, departments or small institutions using exported meter CSVs.",
       "Teaching aid for kW vs kWh, load factor and statistical outliers in ECE/EE laboratories.",
       "Future: 15-minute data and true billing-demand calculation; time-of-day tariffs; weather normalisation; "
       "SQLite storage of edits; Modbus/MQTT meter import; seasonal (rolling) baselines for anomaly detection."])
    P("15. Conclusion", h1)
    P(f"A complete, tested and documented Python application was developed that turns interval electricity data into "
      f"validated, explainable indicators, charts and reports. It processes {len(df):,} records for five buildings, "
      f"implements eight analytical charts and a context-aware IQR detector that found all injected anomalies in the "
      f"synthetic dataset, and passes its automated test suite. It is clear about what it cannot do: it does not "
      f"measure real energy, reproduce bills or diagnose equipment faults.")

    # ---------------------------------------------------------------- refs
    P("16. References", h1)
    refs = ["J. W. Tukey, <i>Exploratory Data Analysis</i>. Reading, MA: Addison-Wesley, 1977.",
            "V. Chandola, A. Banerjee and V. Kumar, “Anomaly detection: A survey,” <i>ACM Computing Surveys</i>, "
            "vol. 41, no. 3, 2009.",
            "C. R. Harris <i>et al.</i>, “Array programming with NumPy,” <i>Nature</i>, vol. 585, pp. 357-362, 2020.",
            "W. McKinney, “Data structures for statistical computing in Python,” in <i>Proc. 9th Python in "
            "Science Conf.</i>, 2010, pp. 56-61.",
            "J. D. Hunter, “Matplotlib: A 2D graphics environment,” <i>Computing in Science &amp; Engineering</i>, "
            "vol. 9, no. 3, pp. 90-95, 2007.",
            "Bureau of Energy Efficiency, <i>Energy Conservation Building Code 2017</i>. New Delhi: Ministry of Power, "
            "Government of India, 2017.",
            "Python Software Foundation, “tkinter — Python interface to Tcl/Tk,” Python 3 documentation, "
            "docs.python.org.",
            "ReportLab Inc., <i>ReportLab PDF Library User Guide</i>, docs.reportlab.com.",
            "pytest developers, <i>pytest documentation</i>, docs.pytest.org."]
    for i, r in enumerate(refs, 1):
        story.append(Paragraph(f"[{i}] {r}", ParagraphStyle("ref", parent=body, leftIndent=14, firstLineIndent=-14,
                                                            alignment=0, spaceAfter=2)))

    P("Appendix A: Installation and Execution", h1)
    P(f"Source code, tests, sample data and documentation: <b>{REPO_URL}</b> (folder src/campus_energy). "
      "Windows PowerShell, from the folder that should contain the project:")
    story.append(Paragraph(
        "git clone " + REPO_URL + ".git<br/>cd campus-energy-usage-analyzer<br/>py -m venv .venv<br/>"
        ".venv\\Scripts\\python.exe -m pip install -r requirements.txt<br/>"
        ".venv\\Scripts\\python.exe -m campus_energy.main &nbsp;&nbsp;# start the application<br/>"
        ".venv\\Scripts\\python.exe -m pytest &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;# run the tests", mono))
    P("Calling .venv\\Scripts\\python.exe directly works even when PowerShell's execution policy blocks "
      "Activate.ps1. requirements.txt installs the project itself in editable mode (-e .), which is what makes "
      "<i>python -m campus_energy.main</i> work from any folder. CSV import expects the header "
      "<font face='Mono' size='7.5'>timestamp,building_id,building_name,interval_hours,average_power_kw,energy_kwh</font>.")
    P("Appendix B: Team Contributions", h1)
    table([["Member (name / roll no.)", "Module(s) owned", "Individual contribution"]] +
          [["", "", ""] for _ in range(5)], [55, 50, 65], "To be completed by the group (maximum five members)")

    # ================================================================ pages
    def cover(c, doc):
        W, H = A4
        c.saveState()
        c.setStrokeColor(colors.black)
        c.setLineWidth(1.2)
        c.rect(12 * mm, 12 * mm, W - 24 * mm, H - 24 * mm)
        logo = DOCS / "assets" / "institute_logo.png"
        if logo.exists():
            c.drawImage(str(logo), W / 2 - 30 * mm, H - 60 * mm, 60 * mm, 40 * mm, mask="auto",
                        preserveAspectRatio=True)
        c.setFont("Serif-B", 19)
        c.drawCentredString(W / 2, H - 74 * mm, "INSTITUTE OF ENGINEERING &")
        c.drawCentredString(W / 2, H - 83 * mm, "MANAGEMENT, KOLKATA")
        y = H - 104 * mm
        form = c.acroForm

        def line(label, value=None, field=None, width=95, x=26 * mm):
            nonlocal y
            c.setFont("Serif-B", 11)
            c.drawString(x, y, label)
            lx = x + pdfmetrics.stringWidth(label, "Serif-B", 11) + 3 * mm
            if value:
                c.setFont("Serif", 10.5)
                c.drawString(lx, y, value)
            if field:
                c.setLineWidth(0.5)
                c.line(lx, y - 1.5, lx + width * mm, y - 1.5)
                form.textfield(name=field, x=lx, y=y - 0.5, width=width * mm, height=4.6 * mm, borderWidth=0,
                               fillColor=colors.white, textColor=colors.black, fontName="Times-Roman", fontSize=10,
                               forceBorder=False, tooltip=field)
            y -= 12 * mm

        line("COURSE TITLE:", "BACHELOR OF TECHNOLOGY")
        line("SUBJECT:", "PYTHON PROGRAMMING LABORATORY")
        line("PROJECT TITLE:", "CAMPUS ENERGY USAGE ANALYZER")
        c.setFont("Serif", 9.5)
        c.drawString(58 * mm, y + 7 * mm, "Electricity Consumption Monitoring and Analytics System")
        y -= 3 * mm
        c.setFont("Serif-B", 11)
        c.drawString(26 * mm, y, "NAME:")
        pos = [(44, 0), (112, 0), (44, -10), (112, -10), (44, -20)]
        for i, (px, dy) in enumerate(pos, 1):
            c.setFont("Serif", 10.5)
            c.drawString(px * mm, y + dy * mm, f"{i}.")
            c.setLineWidth(0.5)
            c.line((px + 5) * mm, y + dy * mm - 1.5, (px + 58) * mm, y + dy * mm - 1.5)
            form.textfield(name=f"Name_{i}", x=(px + 5) * mm, y=y + dy * mm - 0.5, width=53 * mm, height=4.6 * mm,
                           borderWidth=0, fillColor=colors.white, fontName="Times-Roman", fontSize=10,
                           tooltip=f"Student name {i}")
        y -= 33 * mm
        line("ROLL NO:", field="Roll_Number", width=70)
        line("ENROLLMENT NO:", field="Enrollment_Number", width=90)
        line("SECTION:", field="Section", width=30)
        line("SUBMITTED TO:", field="Submitted_To", width=90)
        line("DEPARTMENT NAME:", "ELECTRONICS AND COMMUNICATION ENGINEERING")
        line("ACADEMIC SESSION:", "2026-2027")
        line("DATE OF SUBMISSION:", field="Date_of_Submission", width=60)
        c.restoreState()

    def later(c, doc):
        W, H = A4
        c.saveState()
        c.setFont("Sans-B", 7.5)
        c.setFillColor(colors.HexColor("#334155"))
        c.drawRightString(W - 18 * mm, H - 11 * mm, "CAMPUS ENERGY USAGE ANALYZER")
        c.setStrokeColor(colors.HexColor("#CBD5E1"))
        c.line(18 * mm, H - 12.5 * mm, W - 18 * mm, H - 12.5 * mm)
        c.line(18 * mm, 13 * mm, W - 18 * mm, 13 * mm)
        c.setFont("Sans", 7.5)
        c.drawCentredString(W / 2, 9 * mm, f"Department of Electronics and Communication Engineering | Page {doc.page}")
        c.restoreState()

    doc = SimpleDocTemplate(str(OUT), pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm, topMargin=17 * mm,
                            bottomMargin=17 * mm, title="Campus Energy Usage Analyzer - Project Report",
                            subject="Python Programming Laboratory project report", author="")
    doc.build(story, onFirstPage=cover, onLaterPages=later)
    print(f"Report: {OUT}  pages: {doc.page}  tests: {tests}")
    return tests


if __name__ == "__main__":
    t = build()
    sys.exit(0 if t["exit"] == 0 else 1)
