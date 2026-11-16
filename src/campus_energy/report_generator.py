"""PDF analysis report exported from the application (ReportLab).

Contains the current selection's KPIs, building summary, top anomalies and
two charts. All numbers are computed from the data passed in.
"""
from __future__ import annotations

import io
from datetime import datetime
from pathlib import Path

import matplotlib
import pandas as pd
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (Image, Paragraph, SimpleDocTemplate, Spacer, Table,
                                TableStyle)

from . import analytics as an
from . import visualizations as viz
from .config import ANOMALY_DISCLAIMER, APP_TITLE, SYNTHETIC_NOTE, TARIFF_NOTE

_FONT = "Helvetica"
_FONT_BOLD = "Helvetica-Bold"


def register_fonts() -> tuple[str, str]:
    """Register DejaVu Sans (bundled with Matplotlib) so that the rupee sign renders."""
    global _FONT, _FONT_BOLD
    if _FONT == "DejaVu":
        return _FONT, _FONT_BOLD
    ttf = Path(matplotlib.get_data_path()) / "fonts" / "ttf"
    try:
        pdfmetrics.registerFont(TTFont("DejaVu", str(ttf / "DejaVuSans.ttf")))
        pdfmetrics.registerFont(TTFont("DejaVu-Bold", str(ttf / "DejaVuSans-Bold.ttf")))
        _FONT, _FONT_BOLD = "DejaVu", "DejaVu-Bold"
    except Exception:  # pragma: no cover - fallback keeps export working
        pass
    return _FONT, _FONT_BOLD


def fig_to_image(draw, width_mm: float, height_mm: float, *args) -> Image:
    fig = Figure(figsize=(width_mm / 25.4, height_mm / 25.4), dpi=150)
    FigureCanvasAgg(fig)
    draw(fig, *args)
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150)
    buf.seek(0)
    return Image(buf, width=width_mm * mm, height=height_mm * mm)


def fmt(v, spec=",.2f", unit="") -> str:
    return "n/a" if v is None or (isinstance(v, float) and pd.isna(v)) else f"{v:{spec}}{unit}"


def generate_analysis_report(df: pd.DataFrame, anomalies: pd.DataFrame, tariff: float,
                             path: str | Path, selection: str = "All buildings, full period",
                             source: str = "synthetic", colors_map: dict | None = None) -> Path:
    font, bold = register_fonts()
    path = Path(path)
    ss = getSampleStyleSheet()
    body = ParagraphStyle("b", parent=ss["Normal"], fontName=font, fontSize=9, leading=12)
    h1 = ParagraphStyle("h1", parent=body, fontName=bold, fontSize=16, leading=20)
    h2 = ParagraphStyle("h2", parent=body, fontName=bold, fontSize=11.5, leading=15, spaceBefore=8)
    note = ParagraphStyle("n", parent=body, fontSize=8, textColor=colors.HexColor("#92400E"))

    k = an.kpis(df, tariff, len(anomalies))
    story = [Paragraph(f"{APP_TITLE} — Analysis Report", h1),
             Paragraph(f"Generated {datetime.now():%Y-%m-%d %H:%M} | Data source: {source} | "
                       f"Selection: {selection}", body), Spacer(1, 4)]
    if source.lower().startswith("synthetic") or "synthetic" in source.lower():
        story.append(Paragraph(SYNTHETIC_NOTE, note))
    if df.empty:
        story.append(Paragraph("No records match the current selection.", body))
    else:
        rows = [["Indicator", "Value"],
                ["Total electricity consumption", fmt(k["total_kwh"], ",.1f", " kWh")],
                ["Total estimated cost", "₹ " + fmt(k["total_cost"], ",.2f")],
                ["Observed days", str(k["observed_days"])],
                ["Average daily consumption", fmt(k["avg_daily_kwh"], ",.1f", " kWh/day")],
                ["Maximum recorded demand (1-h interval average)",
                 fmt(k["peak_kw"], ",.1f", " kW") + (f" at {k['peak_time']:%Y-%m-%d %H:%M}" if k["peak_time"] is not None else "")],
                ["Load factor", fmt(k["load_factor"], ".1f", " %")],
                ["Buildings", str(k["buildings"])],
                ["Highest-consuming building", str(k["top_building"])],
                ["Anomalous readings (statistical)", str(k["anomalies"])]]
        story += [Paragraph("Key indicators", h2), _table(rows, [95 * mm, 75 * mm], font, bold)]

        summ = an.building_summary(df, tariff)
        rows = [["Building", "kWh", "Share", "Avg kW", "Peak kW", "Load factor", "Cost (₹)"]]
        for r in summ.itertuples():
            rows.append([r.building_name, f"{r.energy_kwh:,.1f}", fmt(r.share_pct, ".1f", "%"),
                         f"{r.avg_power_kw:.2f}", f"{r.peak_kw:.2f}", fmt(r.load_factor_pct, ".1f", "%"),
                         f"{r.cost_inr:,.2f}"])
        story += [Paragraph("Building summary", h2),
                  _table(rows, [50 * mm, 22 * mm, 16 * mm, 17 * mm, 18 * mm, 22 * mm, 25 * mm], font, bold)]
        story += [Paragraph("Charts", h2),
                  fig_to_image(viz.plot_daily, 170, 62, df),
                  fig_to_image(viz.plot_building_energy, 170, 62, summ, colors_map)]

        story.append(Paragraph(f"Statistical anomalies (first 15 of {len(anomalies)})", h2))
        if anomalies.empty:
            story.append(Paragraph("No readings were outside the IQR limits.", body))
        else:
            rows = [["Timestamp", "Building", "kW", "Expected range", "Category"]]
            for r in anomalies.head(15).itertuples():
                rows.append([f"{r.timestamp:%Y-%m-%d %H:%M}", r.building_name, f"{r.average_power_kw:.2f}",
                             r.expected_range, r.category])
            story.append(_table(rows, [30 * mm, 40 * mm, 15 * mm, 32 * mm, 53 * mm], font, bold, 7.5))
        story.append(Spacer(1, 4))
        story.append(Paragraph(ANOMALY_DISCLAIMER, note))
    story += [Spacer(1, 4), Paragraph(TARIFF_NOTE, note)]

    doc = SimpleDocTemplate(str(path), pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm,
                            topMargin=16 * mm, bottomMargin=16 * mm, title=f"{APP_TITLE} Analysis Report")

    def footer(canvas, d):
        canvas.setFont(font, 8)
        canvas.drawRightString(A4[0] - 18 * mm, 10 * mm, f"Page {d.page}")
        canvas.drawString(18 * mm, 10 * mm, APP_TITLE)

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return path


def _table(rows, widths, font, bold, size=8.5):
    t = Table(rows, colWidths=widths, repeatRows=1)
    t.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, -1), font, size),
        ("FONT", (0, 0), (-1, 0), bold, size),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0F1B2D")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F1F5F9")]),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#CBD5E1")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (1, 1), (-1, -1), "RIGHT") if len(rows[0]) > 2 and rows[0][1] == "kWh" else ("ALIGN", (0, 0), (0, 0), "LEFT"),
    ]))
    return t
