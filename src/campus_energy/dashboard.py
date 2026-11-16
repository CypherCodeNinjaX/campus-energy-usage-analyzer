"""Tkinter desktop dashboard.

The GUI only *displays* results: every number comes from analytics.py,
anomaly_detection.py and cost_calculator.py. User actions that change data
are implemented as plain methods (load_dataset, add_building, export_*, ...)
so they can be tested without clicking, and the button handlers only
collect input (file dialogs / entry fields) and call those methods.
"""
from __future__ import annotations

import logging
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from tkinter import font as tkfont

import pandas as pd
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from matplotlib.figure import Figure

from . import analytics as an
from . import anomaly_detection as ad
from . import cost_calculator as cc
from . import data_loader as dl
from . import visualizations as viz
from .config import (ANOMALY_DISCLAIMER, APP_SUBTITLE, APP_TITLE, APP_VERSION,
                     BUILDING_CATEGORIES, COLORS, DEFAULT_DAYS, DEFAULT_IQR_MULTIPLIER,
                     DEFAULT_SEED, DEFAULT_START_DATE, DEFAULT_TARIFF_INR_PER_KWH,
                     MIN_GROUP_SIZE, MIN_IQR_FRACTION, SYNTHETIC_NOTE, TARIFF_NOTE)
from .models import Building, BuildingRegistry
from .report_generator import generate_analysis_report
from .simulator import generate_dataset
from .validation import ValidationError, ValidationResult

log = logging.getLogger(__name__)
ALL = "All buildings"
RUPEE = "₹"

PAGES = ["Overview", "Energy Analysis", "Building Comparison", "Peak Demand", "Anomaly Detection",
         "Cost Calculator", "Data Management", "Reports", "Settings", "About Project"]


def parse_date(text: str, label: str) -> pd.Timestamp | None:
    text = text.strip()
    if not text:
        return None
    try:
        return pd.Timestamp(pd.to_datetime(text, format="%Y-%m-%d"))
    except (ValueError, TypeError):
        raise ValueError(f"{label} must be a date in YYYY-MM-DD format (got '{text}').") from None


def money(v) -> str:
    return "n/a" if v is None else f"{RUPEE}{v:,.2f}"


# ===================================================================== widgets
class ChartPanel(ttk.Frame):
    """A Matplotlib figure embedded in Tkinter with the zoom/pan/save toolbar."""

    def __init__(self, master, width=6.0, height=3.2):
        super().__init__(master, style="Card.TFrame", padding=4)
        self.figure = Figure(figsize=(width, height), dpi=100, layout="constrained")
        self.canvas = FigureCanvasTkAgg(self.figure, master=self)
        toolbar = NavigationToolbar2Tk(self.canvas, self, pack_toolbar=False)
        toolbar.update()
        toolbar.pack(side="bottom", fill="x")
        self.canvas.get_tk_widget().pack(side="top", fill="both", expand=True)

    def draw(self, func, *args) -> None:
        try:
            func(self.figure, *args)
        except Exception as exc:  # never leave a broken chart on screen
            log.exception("Chart failed")
            viz.empty(self.figure, "Chart unavailable", f"Could not draw chart: {exc}")
        self.canvas.draw_idle()


class DataTable(ttk.Frame):
    """Scrollable Treeview table."""

    def __init__(self, master, height=8):
        super().__init__(master, style="Card.TFrame")
        self.tree = ttk.Treeview(self, show="headings", height=height)
        ys = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview)
        xs = ttk.Scrollbar(self, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=ys.set, xscrollcommand=xs.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        ys.grid(row=0, column=1, sticky="ns")
        xs.grid(row=1, column=0, sticky="ew")
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)

    def set_data(self, columns: list[str], rows, widths: dict | None = None) -> None:
        self.tree.delete(*self.tree.get_children())
        self.tree["columns"] = columns
        for c in columns:
            self.tree.heading(c, text=c)
            self.tree.column(c, width=(widths or {}).get(c, 110), anchor="w", stretch=True)
        for r in rows:
            self.tree.insert("", "end", values=[("" if v is None else v) for v in r])

    def selected_index(self) -> int | None:
        sel = self.tree.selection()
        return self.tree.index(sel[0]) if sel else None


class KpiCard(tk.Frame):
    def __init__(self, master, title: str, accent: str):
        super().__init__(master, bg=COLORS["card"], highlightbackground=COLORS["border"],
                         highlightthickness=1, padx=12, pady=8)
        tk.Frame(self, bg=accent, height=3).pack(fill="x", pady=(0, 6))
        tk.Label(self, text=title, bg=COLORS["card"], fg=COLORS["muted"], font=("TkDefaultFont", 9),
                 anchor="w").pack(fill="x")
        self.value = tk.Label(self, text="—", bg=COLORS["card"], fg=COLORS["text"],
                              font=("TkDefaultFont", 15, "bold"), anchor="w")
        self.value.pack(fill="x")
        self.sub = tk.Label(self, text="", bg=COLORS["card"], fg=COLORS["slate_light"],
                            font=("TkDefaultFont", 8), anchor="w")
        self.sub.pack(fill="x")

    def set(self, value: str, sub: str = "") -> None:
        self.value.configure(text=value)
        self.sub.configure(text=sub)


class BuildingDialog(tk.Toplevel):
    """Modal dialog for adding/editing a building."""

    def __init__(self, master, title: str, building: Building | None = None):
        super().__init__(master)
        self.title(title)
        self.resizable(False, False)
        self.result = None
        frm = ttk.Frame(self, padding=14)
        frm.pack(fill="both", expand=True)
        self.id_var = tk.StringVar(value=building.building_id if building else "")
        self.name_var = tk.StringVar(value=building.name if building else "")
        self.cat_var = tk.StringVar(value=building.category if building else "general")
        ttk.Label(frm, text="Building ID").grid(row=0, column=0, sticky="w", pady=3)
        e_id = ttk.Entry(frm, textvariable=self.id_var, width=28)
        e_id.grid(row=0, column=1, pady=3)
        if building:
            e_id.state(["disabled"])        # IDs are permanent keys
        ttk.Label(frm, text="Building name").grid(row=1, column=0, sticky="w", pady=3)
        e_name = ttk.Entry(frm, textvariable=self.name_var, width=28)
        e_name.grid(row=1, column=1, pady=3)
        ttk.Label(frm, text="Load profile").grid(row=2, column=0, sticky="w", pady=3)
        ttk.Combobox(frm, textvariable=self.cat_var, values=BUILDING_CATEGORIES, state="readonly",
                     width=26).grid(row=2, column=1, pady=3)
        btns = ttk.Frame(frm)
        btns.grid(row=3, column=0, columnspan=2, pady=(10, 0), sticky="e")
        ttk.Button(btns, text="Cancel", command=self.destroy).pack(side="right", padx=4)
        ttk.Button(btns, text="Save", style="Accent.TButton", command=self._ok).pack(side="right")
        self.bind("<Return>", lambda _e: self._ok())
        self.bind("<Escape>", lambda _e: self.destroy())
        (e_name if building else e_id).focus_set()
        self.transient(master)
        self.grab_set()

    def _ok(self):
        self.result = (self.id_var.get().strip(), self.name_var.get().strip(), self.cat_var.get())
        self.destroy()


# ======================================================================= app
class EnergyApp(tk.Tk):
    def __init__(self, load_default: bool = True):
        super().__init__()
        self.title(f"{APP_TITLE} — {APP_SUBTITLE}")
        self.geometry("1320x840")
        self.minsize(1200, 750)
        self.configure(bg=COLORS["bg"])
        self.settings = {"tariff": DEFAULT_TARIFF_INR_PER_KWH, "k": DEFAULT_IQR_MULTIPLIER,
                         "min_iqr_fraction": MIN_IQR_FRACTION, "min_group_size": MIN_GROUP_SIZE,
                         "seed": DEFAULT_SEED, "days": DEFAULT_DAYS, "start_date": DEFAULT_START_DATE,
                         "include_anomalies": True}
        self.registry = BuildingRegistry.default()
        self.data = pd.DataFrame()
        self.anomalies_all = pd.DataFrame(columns=ad.ANOMALY_COLUMNS)
        self.filtered = pd.DataFrame()
        self.anomalies = self.anomalies_all
        self.validation: ValidationResult | None = None
        self.source_label = "No dataset loaded"
        self.colors = {}
        self.current_page = None
        self._dirty: set[str] = set(PAGES)
        self._setup_fonts_and_style()
        self._build_layout()
        self._bind_keys()
        if load_default:
            self.load_default_dataset()
        self.show_page("Overview")

    # ------------------------------------------------------------- dialogs
    # (wrapped so automated tests can replace them)
    def show_error(self, title, msg):
        messagebox.showerror(title, msg, parent=self)

    def show_info(self, title, msg):
        messagebox.showinfo(title, msg, parent=self)

    def ask_yes_no(self, title, msg) -> bool:
        return messagebox.askyesno(title, msg, parent=self, icon="warning")

    def ask_save_path(self, default_name: str, ext: str) -> str:
        types = {".csv": [("CSV files", "*.csv")], ".json": [("JSON files", "*.json")],
                 ".pdf": [("PDF files", "*.pdf")]}[ext]
        return filedialog.asksaveasfilename(parent=self, initialfile=default_name, defaultextension=ext,
                                            filetypes=types + [("All files", "*.*")])

    def ask_open_path(self) -> str:
        return filedialog.askopenfilename(parent=self, filetypes=[("CSV files", "*.csv"), ("All files", "*.*")])

    # --------------------------------------------------------------- style
    def _setup_fonts_and_style(self):
        fams = set(tkfont.families(self))
        family = next((f for f in ("Segoe UI", "Inter", "DejaVu Sans", "Helvetica") if f in fams), "TkDefaultFont")
        for name in ("TkDefaultFont", "TkTextFont", "TkHeadingFont", "TkMenuFont"):
            try:
                tkfont.nametofont(name).configure(family=family, size=10)
            except tk.TclError:
                pass
        self.family = family
        st = ttk.Style(self)
        st.theme_use("clam")
        c = COLORS
        st.configure(".", background=c["bg"], foreground=c["text"])
        st.configure("Card.TFrame", background=c["card"])
        st.configure("TFrame", background=c["bg"])
        st.configure("TLabel", background=c["bg"], foreground=c["text"])
        st.configure("Card.TLabel", background=c["card"])
        st.configure("Muted.TLabel", foreground=c["muted"])
        st.configure("H2.TLabel", font=(family, 13, "bold"))
        st.configure("Note.TLabel", background=c["amber_bg"], foreground="#78350F", padding=6)
        st.configure("TButton", padding=(10, 5))
        st.configure("Accent.TButton", background=c["teal"], foreground="white", padding=(10, 5))
        st.map("Accent.TButton", background=[("active", c["cyan"]), ("disabled", c["border"])])
        st.configure("Treeview", rowheight=24, fieldbackground="white", background="white")
        st.configure("Treeview.Heading", background=c["slate"], foreground="white", font=(family, 9, "bold"))
        st.map("Treeview.Heading", background=[("active", c["navy"])])
        st.configure("TNotebook", background=c["bg"])
        st.configure("TNotebook.Tab", padding=(12, 5))
        st.configure("TLabelframe", background=c["bg"])
        st.configure("TLabelframe.Label", background=c["bg"], font=(family, 10, "bold"))
        st.configure("TCheckbutton", background=c["bg"])

    # -------------------------------------------------------------- layout
    def _build_layout(self):
        c = COLORS
        side = tk.Frame(self, bg=c["sidebar"], width=210)
        side.pack(side="left", fill="y")
        side.pack_propagate(False)
        tk.Label(side, text="⚡ Campus Energy", bg=c["sidebar"], fg="white",
                 font=(self.family, 14, "bold")).pack(anchor="w", padx=16, pady=(18, 0))
        tk.Label(side, text="Usage Analyzer", bg=c["sidebar"], fg="#94A3B8",
                 font=(self.family, 10)).pack(anchor="w", padx=16, pady=(0, 16))
        self.nav = {}
        for i, page in enumerate(PAGES):
            b = tk.Button(side, text=f"  {page}", anchor="w", relief="flat", bd=0, padx=14, pady=8,
                          bg=c["sidebar"], fg="#E2E8F0", activebackground=c["sidebar_active"],
                          activeforeground="white", font=(self.family, 10), cursor="hand2",
                          command=lambda p=page: self.show_page(p), takefocus=1)
            b.pack(fill="x")
            self.nav[page] = b
        tk.Label(side, text=f"v{APP_VERSION} • offline • synthetic-ready", bg=c["sidebar"],
                 fg="#64748B", font=(self.family, 8)).pack(side="bottom", pady=10)

        main = tk.Frame(self, bg=c["bg"])
        main.pack(side="left", fill="both", expand=True)
        head = tk.Frame(main, bg=c["navy"], padx=20, pady=10)
        head.pack(fill="x")
        left = tk.Frame(head, bg=c["navy"])
        left.pack(side="left")
        tk.Label(left, text=APP_TITLE, bg=c["navy"], fg="white", font=(self.family, 17, "bold")).pack(anchor="w")
        tk.Label(left, text=APP_SUBTITLE, bg=c["navy"], fg="#5EEAD4", font=(self.family, 10)).pack(anchor="w")
        self.status_dot = tk.Label(head, text="●", bg=c["navy"], fg=c["amber"], font=(self.family, 14))
        self.status_text = tk.Label(head, text="", bg=c["navy"], fg="#CBD5E1", font=(self.family, 9),
                                    justify="right")
        self.status_text.pack(side="right")
        self.status_dot.pack(side="right", padx=(0, 6))

        # filter bar
        fb = ttk.Frame(main, padding=(20, 8))
        fb.pack(fill="x")
        ttk.Label(fb, text="Building").pack(side="left")
        self.building_var = tk.StringVar(value=ALL)
        self.building_cb = ttk.Combobox(fb, textvariable=self.building_var, state="readonly", width=24)
        self.building_cb.pack(side="left", padx=(4, 10))
        self.building_cb.bind("<<ComboboxSelected>>", lambda _e: self.apply_filters())
        ttk.Label(fb, text="From").pack(side="left")
        self.start_var = tk.StringVar()
        ttk.Entry(fb, textvariable=self.start_var, width=11).pack(side="left", padx=(4, 10))
        ttk.Label(fb, text="To").pack(side="left")
        self.end_var = tk.StringVar()
        ttk.Entry(fb, textvariable=self.end_var, width=11).pack(side="left", padx=(4, 10))
        ttk.Button(fb, text="Apply (F5)", style="Accent.TButton",
                   command=self.apply_filters).pack(side="left")
        ttk.Button(fb, text="Reset", command=self.reset_filters).pack(side="left", padx=6)
        ttk.Button(fb, text="Export filtered CSV", command=self.on_export_filtered).pack(side="right")

        self.content = ttk.Frame(main, padding=(20, 4, 20, 12))
        self.content.pack(fill="both", expand=True)
        self.content.rowconfigure(0, weight=1)
        self.content.columnconfigure(0, weight=1)
        self.pages = {}
        builders = {"Overview": self._page_overview, "Energy Analysis": self._page_energy,
                    "Building Comparison": self._page_buildings, "Peak Demand": self._page_peak,
                    "Anomaly Detection": self._page_anomaly, "Cost Calculator": self._page_cost,
                    "Data Management": self._page_data, "Reports": self._page_reports,
                    "Settings": self._page_settings, "About Project": self._page_about}
        for name in PAGES:
            frame = ttk.Frame(self.content)
            frame.grid(row=0, column=0, sticky="nsew")
            self.pages[name] = frame
            builders[name](frame)

    def _bind_keys(self):
        self.bind("<F5>", lambda _e: self.apply_filters())
        self.bind("<Control-o>", lambda _e: self.on_import_csv())
        self.bind("<Control-e>", lambda _e: self.on_export_filtered())
        for i, page in enumerate(PAGES[:9], start=1):
            self.bind(f"<Control-Key-{i}>", lambda _e, p=page: self.show_page(p))
        self.bind("<Control-Key-0>", lambda _e: self.show_page(PAGES[9]))

    def show_page(self, name: str):
        self.current_page = name
        for p, b in self.nav.items():
            b.configure(bg=COLORS["sidebar_active"] if p == name else COLORS["sidebar"],
                        fg="white" if p == name else "#E2E8F0")
        self.pages[name].tkraise()
        if name in self._dirty:
            self._refresh_page(name)
            self._dirty.discard(name)

    # ------------------------------------------------------------- data ops
    def load_default_dataset(self):
        try:
            res = dl.load_sample()
        except ValidationError as exc:
            log.warning("Sample file unusable: %s", exc)
            res = None
        if res is not None and res.accepted_rows:
            self.set_dataset(res.accepted, "Synthetic sample (data/sample_energy_data.csv)", res)
        else:
            self.regenerate_dataset()

    def regenerate_dataset(self):
        s = self.settings
        buildings = [{"building_id": b.building_id, "name": b.name, "category": b.category} for b in self.registry]
        if not buildings:
            raise ValueError("Add at least one building before generating data.")
        df = generate_dataset(start_date=s["start_date"], days=int(s["days"]), buildings=buildings,
                              seed=int(s["seed"]), tariff=s["tariff"], include_anomalies=s["include_anomalies"])
        df = df.drop(columns=["estimated_cost_inr"])
        self.set_dataset(df, f"Synthetic (seed {s['seed']}, {s['days']} days)", None, keep_registry=True)

    def import_csv(self, path) -> ValidationResult:
        res = dl.load_csv(path)
        if res.accepted_rows == 0:
            self.validation = res
            self._dirty |= {"Data Management"}
            raise ValidationError(f"No valid rows found ({res.rejected_rows} rejected). "
                                  "See Data Management for the reasons.")
        self.set_dataset(res.accepted, f"Imported: {Path(path).name}", res)
        return res

    def set_dataset(self, df: pd.DataFrame, label: str, validation: ValidationResult | None,
                    keep_registry: bool = False):
        self.data = df.sort_values(["building_id", "timestamp"]).reset_index(drop=True)
        self.source_label = label
        self.validation = validation
        if not keep_registry:
            self.registry = BuildingRegistry.from_dataframe(self.data, known=self.registry)
        self._recompute_anomalies()
        self._update_building_choices()
        self._fill_date_range()
        self.apply_filters(quiet=True)

    def _fill_date_range(self):
        """Show the dataset's first/last date in the filter boxes (also shows the date format)."""
        if self.data.empty:
            self.start_var.set("")
            self.end_var.set("")
        else:
            self.start_var.set(f"{self.data['timestamp'].min():%Y-%m-%d}")
            self.end_var.set(f"{self.data['timestamp'].max():%Y-%m-%d}")

    def _recompute_anomalies(self):
        s = self.settings
        self.anomalies_all = ad.detect_anomalies(self.data, k=s["k"], min_group_size=int(s["min_group_size"]),
                                                 min_iqr_fraction=s["min_iqr_fraction"])

    def _update_building_choices(self):
        ids = list(dict.fromkeys(list(self.registry.ids()) + (list(self.data["building_id"].unique())
                                                             if not self.data.empty else [])))
        names = [self.registry.get(i).name if self.registry.get(i) else i for i in ids]
        self.colors = viz.color_map(names)
        self.building_cb["values"] = [ALL] + self.registry.names()
        if self.building_var.get() not in self.building_cb["values"]:
            self.building_var.set(ALL)

    def selection_text(self) -> str:
        return (f"{self.building_var.get()}, {self.start_var.get().strip() or 'start'} to "
                f"{self.end_var.get().strip() or 'end'}")

    def apply_filters(self, quiet: bool = False) -> bool:
        try:
            start = parse_date(self.start_var.get(), "From date")
            end = parse_date(self.end_var.get(), "To date")
            if start is not None and end is not None and start > end:
                raise ValueError("From date must not be after To date.")
        except ValueError as exc:
            if not quiet:
                self.show_error("Invalid date", str(exc))
            return False
        name = self.building_var.get()
        ids = None if name == ALL else [self.registry.name_to_id(name)]
        if self.data.empty:
            self.filtered = self.data
            self.anomalies = self.anomalies_all
        else:
            self.filtered = an.filter_data(self.data, ids, start, end)
            a = self.anomalies_all
            if not a.empty:
                a = an.filter_data(a, ids, start, end)
            self.anomalies = a
        self._update_status()
        self._dirty = set(PAGES)
        if self.current_page:
            self.show_page(self.current_page)
        return True

    def reset_filters(self):
        self.building_var.set(ALL)
        self._fill_date_range()
        self.apply_filters()

    def _update_status(self):
        if self.data.empty:
            self.status_dot.configure(fg=COLORS["amber"])
            self.status_text.configure(text="No dataset loaded")
            return
        f = self.filtered
        self.status_dot.configure(fg="#22C55E" if not f.empty else COLORS["amber"])
        rng = (f"{f['timestamp'].min():%d %b %Y} – {f['timestamp'].max():%d %b %Y}" if not f.empty
               else "no records match filter")
        self.status_text.configure(text=f"Dataset: {self.source_label}\n{len(f):,} of {len(self.data):,} "
                                        f"records • {rng} • tariff {RUPEE}{self.settings['tariff']:g}/kWh")

    def records_with_cost(self, df: pd.DataFrame) -> pd.DataFrame:
        out = df.copy()
        out["estimated_cost_inr"] = (out["energy_kwh"] * self.settings["tariff"]).round(2)
        return out

    # --------------------------------------------------------- buildings
    def add_building(self, building_id: str, name: str, category: str = "general") -> Building:
        b = Building(building_id, name, category)
        if not self.data.empty and building_id in set(self.data["building_id"]):
            raise ValueError(f"Building ID '{building_id}' already exists in the dataset.")
        self.registry.add(b)
        self._update_building_choices()
        self._dirty |= set(PAGES)
        self.show_page(self.current_page)
        return b

    def edit_building(self, building_id: str, name: str, category: str) -> None:
        old = self.registry.get(building_id).name if self.registry.get(building_id) else None
        self.registry.edit(building_id, name=name, category=category)
        if not self.data.empty:
            self.data.loc[self.data["building_id"] == building_id, "building_name"] = name
            if not self.anomalies_all.empty:
                self.anomalies_all.loc[self.anomalies_all["building_id"] == building_id, "building_name"] = name
        if self.building_var.get() == old:
            self.building_var.set(name)
        self._update_building_choices()
        self._recompute_anomalies()
        self.apply_filters(quiet=True)

    def remove_building(self, building_id: str) -> int:
        """Remove a building and its records from the working dataset. Returns rows removed."""
        self.registry.remove(building_id)
        removed = 0
        if not self.data.empty:
            mask = self.data["building_id"] == building_id
            removed = int(mask.sum())
            self.data = self.data[~mask].reset_index(drop=True)
        self._recompute_anomalies()
        self._update_building_choices()
        self.apply_filters(quiet=True)
        return removed

    # ------------------------------------------------------------ exports
    def export_filtered(self, path) -> Path:
        return dl.export_csv(self.records_with_cost(self.filtered), path)

    def export_summary(self, path) -> Path:
        return dl.export_csv(an.building_summary(self.filtered, self.settings["tariff"]).round(3), path)

    def export_anomalies(self, path) -> Path:
        out = self.anomalies.copy()
        out["note"] = ANOMALY_DISCLAIMER
        return dl.export_csv(out, path)

    def export_monthly_json(self, path) -> Path:
        payload = {"source": self.source_label, "selection": self.selection_text(),
                   "tariff_inr_per_kwh": self.settings["tariff"], "note": TARIFF_NOTE,
                   "monthly_summary": an.monthly_summary(self.filtered, self.settings["tariff"])}
        return dl.export_json(payload, path)

    def export_pdf(self, path) -> Path:
        return generate_analysis_report(self.filtered, self.anomalies, self.settings["tariff"], path,
                                        selection=self.selection_text(), source=self.source_label,
                                        colors_map=self.colors)

    def _save(self, default_name, ext, func, what):
        if what != "validation summary" and self.filtered.empty:
            self.show_error("Nothing to export", "No records match the current selection.")
            return
        path = self.ask_save_path(default_name, ext)
        if not path:
            return
        try:
            out = func(path)
        except (OSError, ValueError) as exc:
            self.show_error("Export failed", f"Could not write {what}:\n{exc}")
            return
        self.show_info("Export complete", f"Saved {what} to:\n{out}")

    def on_export_filtered(self):
        self._save("filtered_energy_records.csv", ".csv", self.export_filtered, "filtered records")

    # ---------------------------------------------------------- refreshing
    def _refresh_page(self, name):
        fn = getattr(self, "_refresh_" + name.lower().replace(" ", "_"), None)
        if fn:
            try:
                fn()
            except Exception as exc:
                log.exception("Refresh of %s failed", name)
                self.show_error("Display error", f"Could not update '{name}':\n{exc}")

    def _empty_note(self, label: ttk.Label):
        label.configure(text="No records match the current selection. Change the filters or load a dataset."
                        if self.filtered.empty else "")

    # =========================================================== PAGES
    def _header(self, parent, title, text=""):
        ttk.Label(parent, text=title, style="H2.TLabel").pack(anchor="w")
        if text:
            ttk.Label(parent, text=text, style="Muted.TLabel", wraplength=1000).pack(anchor="w", pady=(0, 6))

    # ---- Overview
    def _page_overview(self, p):
        self._header(p, "Overview", SYNTHETIC_NOTE)
        grid = ttk.Frame(p)
        grid.pack(fill="x", pady=(2, 8))
        specs = [("Total consumption", "teal"), ("Total estimated cost", "green"),
                 ("Average daily consumption", "cyan"), ("Maximum recorded demand", "amber"),
                 ("Buildings monitored", "slate_light"), ("Anomalous readings", "amber"),
                 ("Highest-consuming building", "teal"), ("Est. cost per building (avg)", "green")]
        self.kpi = {}
        for i, (t, col) in enumerate(specs):
            card = KpiCard(grid, t, COLORS[col])
            card.grid(row=i // 4, column=i % 4, sticky="nsew", padx=4, pady=4)
            grid.columnconfigure(i % 4, weight=1)
            self.kpi[t] = card
        self.ov_empty = ttk.Label(p, text="", foreground=COLORS["amber"])
        self.ov_empty.pack(anchor="w")
        charts = ttk.Frame(p)
        charts.pack(fill="both", expand=True)
        self.ov_daily = ChartPanel(charts)
        self.ov_build = ChartPanel(charts)
        self.ov_daily.pack(side="left", fill="both", expand=True, padx=(0, 4))
        self.ov_build.pack(side="left", fill="both", expand=True, padx=(4, 0))

    def _refresh_overview(self):
        f, t = self.filtered, self.settings["tariff"]
        k = an.kpis(f, t, len(self.anomalies) if not f.empty else None)
        na = "—"
        self.kpi["Total consumption"].set(f"{k['total_kwh']:,.1f} kWh" if k["total_kwh"] is not None else na,
                                          f"over {k['observed_days']} observed days" if k["observed_days"] else "")
        self.kpi["Total estimated cost"].set(money(k["total_cost"]) if k["total_cost"] is not None else na,
                                             f"flat {RUPEE}{t:g}/kWh (illustrative)")
        self.kpi["Average daily consumption"].set(
            f"{k['avg_daily_kwh']:,.1f} kWh/day" if k["avg_daily_kwh"] is not None else na, "per observed day")
        self.kpi["Maximum recorded demand"].set(
            f"{k['peak_kw']:,.1f} kW" if k["peak_kw"] is not None else na,
            f"1-h avg, {k['peak_time']:%d %b %H:%M}" if k["peak_time"] is not None else "")
        self.kpi["Buildings monitored"].set(str(k["buildings"]) if k["buildings"] is not None else na,
                                            f"{len(self.registry)} in registry")
        self.kpi["Anomalous readings"].set(str(k["anomalies"]) if k["anomalies"] is not None else na,
                                           "statistical (IQR), not faults")
        self.kpi["Highest-consuming building"].set(k["top_building"] or na, "by total kWh")
        self.kpi["Est. cost per building (avg)"].set(
            money(k["cost_per_building"]) if k["cost_per_building"] is not None else na, "see Cost Calculator")
        self._empty_note(self.ov_empty)
        self.ov_daily.draw(viz.plot_daily, f)
        self.ov_build.draw(viz.plot_building_energy, an.building_summary(f, t), self.colors)

    # ---- Energy analysis
    def _page_energy(self, p):
        self._header(p, "Energy Analysis", "Daily trend with 7-day moving average, hourly profile, "
                     "date x hour heatmap and weekday/weekend comparison for the current selection.")
        nb = ttk.Notebook(p)
        nb.pack(fill="both", expand=True)
        self.en_charts = {}
        for name in ("Daily trend", "Hourly profile", "Heatmap", "Weekday vs weekend"):
            panel = ChartPanel(nb, 9, 4.6)
            nb.add(panel, text=name)
            self.en_charts[name] = panel

    def _refresh_energy_analysis(self):
        f = self.filtered
        self.en_charts["Daily trend"].draw(viz.plot_daily, f)
        self.en_charts["Hourly profile"].draw(viz.plot_hourly_profile, f, self.colors)
        self.en_charts["Heatmap"].draw(viz.plot_heatmap, f)
        self.en_charts["Weekday vs weekend"].draw(viz.plot_weekday_weekend, an.weekday_weekend(f))

    # ---- Building comparison
    def _page_buildings(self, p):
        self._header(p, "Building Comparison", "Energy share = building energy / total energy x 100. "
                     "Load factor = average power / maximum 1-hour average power.")
        self.bc_chart = ChartPanel(p, 9, 3.3)
        self.bc_chart.pack(fill="both", expand=True)
        bar = ttk.Frame(p)
        bar.pack(fill="x", pady=4)
        ttk.Button(bar, text="Export building summary (CSV)", command=lambda: self._save(
            "building_summary.csv", ".csv", self.export_summary, "building summary")).pack(side="right")
        self.bc_table = DataTable(p, 6)
        self.bc_table.pack(fill="x")

    def _refresh_building_comparison(self):
        s = an.building_summary(self.filtered, self.settings["tariff"])
        self.bc_chart.draw(viz.plot_building_energy, s, self.colors)
        rows = [(r.building_id, r.building_name, r.records, f"{r.energy_kwh:,.1f}",
                 "n/a" if r.share_pct is None or pd.isna(r.share_pct) else f"{r.share_pct:.1f}",
                 f"{r.avg_power_kw:.2f}", f"{r.peak_kw:.2f}",
                 "n/a" if r.load_factor_pct is None or pd.isna(r.load_factor_pct) else f"{r.load_factor_pct:.1f}",
                 f"{r.cost_inr:,.2f}") for r in s.itertuples()]
        self.bc_table.set_data(["ID", "Building", "Records", "Energy (kWh)", "Share (%)", "Avg power (kW)",
                                "Peak (kW)", "Load factor (%)", f"Est. cost ({RUPEE})"], rows,
                               {"Building": 190, "ID": 60, "Records": 70})

    # ---- Peak demand
    def _page_peak(self, p):
        self._header(p, "Peak Demand", "Maximum recorded demand is the highest 1-hour interval-average "
                     "power of the selected buildings combined (only timestamps where every selected building "
                     "reports). It is not an instantaneous peak and not a utility billing demand.")
        self.pk_info = ttk.Label(p, text="", font=(self.family, 10, "bold"))
        self.pk_info.pack(anchor="w", pady=2)
        self.pk_chart = ChartPanel(p, 9, 3.4)
        self.pk_chart.pack(fill="both", expand=True)
        ttk.Label(p, text="Highest individual building readings", style="Muted.TLabel").pack(anchor="w", pady=(4, 0))
        self.pk_table = DataTable(p, 6)
        self.pk_table.pack(fill="x")

    def _refresh_peak_demand(self):
        f = self.filtered
        pk, lf, avg = an.peak_demand(f), an.load_factor(f), an.average_power(f)
        if pk is None:
            self.pk_info.configure(text="Peak demand: not available for the current selection.")
        else:
            self.pk_info.configure(text=f"Peak: {pk[0]:,.2f} kW at {pk[1]:%Y-%m-%d %H:%M}    |    "
                                        f"Average power: {avg:,.2f} kW    |    Load factor: "
                                        + (f"{lf:.1f} %" if lf is not None else "n/a (needs >= 24 complete, uniform intervals)"))
        self.pk_chart.draw(viz.plot_peak_demand, f)
        t = an.top_peaks(f, 15) if not f.empty else pd.DataFrame()
        self.pk_table.set_data(["Timestamp", "Building", "Avg power (kW)", "Energy (kWh)"],
                               [(f"{r.timestamp:%Y-%m-%d %H:%M}", r.building_name, f"{r.average_power_kw:.2f}",
                                 f"{r.energy_kwh:.2f}") for r in t.itertuples()], {"Building": 220})

    # ---- Anomaly detection
    def _page_anomaly(self, p):
        self._header(p, "Anomaly Detection")
        ttk.Label(p, text="⚠  " + ANOMALY_DISCLAIMER + "  Readings are compared with the same building, "
                  "same day type and same hour (IQR rule).", style="Note.TLabel", wraplength=1000).pack(fill="x")
        self.an_eval = ttk.Label(p, text="", style="Muted.TLabel", wraplength=1000)
        self.an_eval.pack(anchor="w", pady=2)
        self.an_chart = ChartPanel(p, 9, 3.1)
        self.an_chart.pack(fill="both", expand=True)
        bar = ttk.Frame(p)
        bar.pack(fill="x", pady=3)
        ttk.Button(bar, text="Inspect selected", command=self.on_inspect_anomaly).pack(side="left")
        ttk.Button(bar, text="Export anomaly report (CSV)", command=lambda: self._save(
            "anomaly_report.csv", ".csv", self.export_anomalies, "anomaly report")).pack(side="right")
        self.an_table = DataTable(p, 6)
        self.an_table.pack(fill="x")
        self.an_table.tree.bind("<Double-1>", lambda _e: self.on_inspect_anomaly())
        self.an_table.tree.bind("<Return>", lambda _e: self.on_inspect_anomaly())

    def _refresh_anomaly_detection(self):
        f, a = self.filtered, self.anomalies
        s = self.settings
        text = (f"{len(a)} statistical anomalies in the selection (k = {s['k']:g}, IQR noise floor "
                f"{s['min_iqr_fraction'] * 100:.0f}% of median, min group size {s['min_group_size']}).")
        if "injected_anomaly" in self.data.columns and (self.data["injected_anomaly"].fillna("") != "").any():
            ev = ad.evaluate_against_injected(self.data, s["k"], s["min_iqr_fraction"])
            text += "  Whole-dataset check against the simulator's injected anomalies: " + "; ".join(
                f"{r.method}: {r.injected_detected}/{r.injected} found, {r.other_flags} other flags"
                for r in ev.itertuples()) + "."
        self.an_eval.configure(text=text)
        self.an_chart.draw(viz.plot_anomalies, f, a, self.colors)
        self.an_table.set_data(["Timestamp", "Building", "Power (kW)", "Energy (kWh)", "Expected range",
                                "Category", "Day complete", "Method"],
                               [(f"{r.timestamp:%Y-%m-%d %H:%M}", r.building_name, f"{r.average_power_kw:.2f}",
                                 f"{r.energy_kwh:.2f}", r.expected_range, r.category,
                                 "Yes" if r.day_complete else "No", r.method) for r in a.itertuples()],
                               {"Timestamp": 125, "Building": 170, "Power (kW)": 80, "Energy (kWh)": 85, "Category": 220,
                                "Day complete": 90, "Method": 420, "Expected range": 130})

    def on_inspect_anomaly(self):
        i = self.an_table.selected_index()
        if i is None or i >= len(self.anomalies):
            self.show_info("Inspect anomaly", "Select a row in the anomaly table first.")
            return
        r = self.anomalies.iloc[i]
        self.show_info("Anomaly details", (
            f"Building: {r.building_name} ({r.building_id})\nTimestamp: {r.timestamp:%Y-%m-%d %H:%M}\n"
            f"Recorded: {r.average_power_kw:.3f} kW ({r.energy_kwh:.3f} kWh)\n"
            f"Expected statistical range: {r.expected_range}\nCategory: {r.category}\n"
            f"Comparison group: {r.group}\nMethod: {r.method}\n"
            f"Day has all readings: {'yes' if r.day_complete else 'no - check for incomplete data'}\n\n"
            f"{ANOMALY_DISCLAIMER}"))

    # ---- Cost calculator
    def _page_cost(self, p):
        self._header(p, "Cost Calculator", TARIFF_NOTE)
        top = ttk.Frame(p)
        top.pack(fill="x", pady=2)
        ttk.Label(top, text=f"Tariff ({RUPEE}/kWh)").pack(side="left")
        self.tariff_var = tk.StringVar(value=f"{self.settings['tariff']:g}")
        e = ttk.Entry(top, textvariable=self.tariff_var, width=8)
        e.pack(side="left", padx=4)
        e.bind("<Return>", lambda _e: self.on_apply_tariff())
        ttk.Button(top, text="Apply tariff", style="Accent.TButton", command=self.on_apply_tariff).pack(side="left")
        self.cost_info = ttk.Label(top, text="", font=(self.family, 10, "bold"))
        self.cost_info.pack(side="left", padx=16)
        cmp = ttk.LabelFrame(p, text="Compare two periods (previous vs current, YYYY-MM-DD, inclusive)", padding=8)
        cmp.pack(side="bottom", fill="x", pady=(6, 0))
        body = ttk.Frame(p)
        body.pack(fill="both", expand=True)
        right = ttk.Frame(body, padding=(8, 0, 0, 0), width=330)
        right.pack(side="right", fill="y")
        right.pack_propagate(False)
        self.cost_chart = ChartPanel(body, 5.0, 3.0)
        self.cost_chart.pack(side="left", fill="both", expand=True)
        ttk.Label(right, text="Monthly estimated cost").pack(anchor="w")
        self.cost_month = DataTable(right, 4)
        self.cost_month.pack(fill="x")
        ttk.Label(right, text="Daily estimated cost").pack(anchor="w", pady=(6, 0))
        self.cost_daily = DataTable(right, 7)
        self.cost_daily.pack(fill="both", expand=True)
        self.cmp_result = ttk.Label(cmp, text="Enter two periods and press Compare.", wraplength=1000)
        self.cmp_result.pack(side="bottom", anchor="w", pady=(6, 0))
        self.cmp_vars = [tk.StringVar() for _ in range(4)]
        for lbl, var in zip(["Previous from", "to", "Current from", "to"], self.cmp_vars):
            ttk.Label(cmp, text=lbl).pack(side="left")
            ttk.Entry(cmp, textvariable=var, width=11).pack(side="left", padx=(3, 8))
        ttk.Button(cmp, text="Compare", command=self.on_compare_periods).pack(side="left")


    def set_tariff(self, value) -> float:
        t = cc.validate_tariff(value)
        self.settings["tariff"] = t
        self.tariff_var.set(f"{t:g}")
        self.apply_filters(quiet=True)
        return t

    def on_apply_tariff(self):
        try:
            self.set_tariff(self.tariff_var.get())
        except ValueError as exc:
            self.show_error("Invalid tariff", str(exc))

    def compare_periods(self, a1, a2, b1, b2) -> dict:
        dates = [parse_date(x, n) for x, n in zip((a1, a2, b1, b2), ("Previous from", "Previous to",
                                                                     "Current from", "Current to"))]
        if any(d is None for d in dates):
            raise ValueError("Enter all four dates.")
        if dates[0] > dates[1] or dates[2] > dates[3]:
            raise ValueError("Each period's start must not be after its end.")
        return an.compare_periods(self.filtered, (dates[0], dates[1]), (dates[2], dates[3]),
                                  self.settings["tariff"])

    def on_compare_periods(self):
        try:
            r = self.compare_periods(*[v.get() for v in self.cmp_vars])
        except ValueError as exc:
            self.show_error("Invalid periods", str(exc))
            return
        ch = r["change_pct"]
        dch = r["daily_change_pct"]
        self.cmp_result.configure(text=(
            f"Previous: {r['previous_kwh']:,.1f} kWh ({money(r['previous_cost'])}, {r['previous_days']} d)  |  "
            f"Current: {r['current_kwh']:,.1f} kWh ({money(r['current_cost'])}, {r['current_days']} d)  |  "
            f"Change: {'n/a (previous = 0)' if ch is None else f'{ch:+.1f} %'}"
            f"  (per day: {'n/a' if dch is None else f'{dch:+.1f} %'})"))

    def _refresh_cost_calculator(self):
        f, t = self.filtered, self.settings["tariff"]
        self.tariff_var.set(f"{t:g}")
        if f.empty:
            self.cost_info.configure(text="No records in selection.")
        else:
            self.cost_info.configure(text=f"Campus-wide estimate: {money(cc.campus_cost(f, t))}   |   "
                                          f"average {money(cc.campus_cost(f, t) / an.observed_days(f))} per day")
        self.cost_chart.draw(viz.plot_cost, an.building_summary(f, t), t, self.colors)
        m = cc.monthly_costs(f, t)
        self.cost_month.set_data(["Month", "Energy (kWh)", f"Cost ({RUPEE})"],
                                 [(r.month, f"{r.energy_kwh:,.1f}", f"{r.cost_inr:,.2f}") for r in m.itertuples()],
                                 {"Month": 70, "Energy (kWh)": 105, f"Cost ({RUPEE})": 115})
        d = cc.daily_costs(f, t)
        self.cost_daily.set_data(["Date", f"Cost ({RUPEE})"], [(f"{i:%Y-%m-%d}", f"{v:,.2f}") for i, v in d.items()],
                                 {"Date": 120, f"Cost ({RUPEE})": 170})

    # ---- Data management
    def _page_data(self, p):
        self._header(p, "Data Management", "Import validates every row; invalid rows are never used in "
                     "calculations and are listed below with reasons. Missing values are never replaced by zero.")
        bar = ttk.Frame(p)
        bar.pack(fill="x", pady=2)
        ttk.Button(bar, text="Import CSV… (Ctrl+O)", style="Accent.TButton", command=self.on_import_csv).pack(side="left")
        ttk.Button(bar, text="Load bundled sample", command=self.on_load_sample).pack(side="left", padx=4)
        ttk.Button(bar, text="Regenerate synthetic data", command=self.on_regenerate).pack(side="left")
        ttk.Button(bar, text="Export monthly JSON", command=lambda: self._save(
            "monthly_summary.json", ".json", self.export_monthly_json, "monthly summary")).pack(side="right")
        ttk.Button(bar, text="Export validation summary", command=self.on_export_validation).pack(side="right", padx=4)
        self.val_label = ttk.Label(p, text="", font=(self.family, 10, "bold"))
        self.val_label.pack(anchor="w", pady=(6, 2))
        self.val_table = DataTable(p, 4)
        self.val_table.pack(fill="x")
        lower = ttk.Notebook(p)
        lower.pack(fill="both", expand=True, pady=(8, 0))
        bf = ttk.Frame(lower, padding=6)
        lower.add(bf, text="Campus buildings (add / edit / remove)")
        self.bld_table = DataTable(bf, 8)
        self.bld_table.pack(fill="both", expand=True)
        bb = ttk.Frame(bf)
        bb.pack(fill="x", pady=(4, 0))
        ttk.Button(bb, text="Add", command=self.on_add_building).pack(side="left")
        ttk.Button(bb, text="Edit", command=self.on_edit_building).pack(side="left", padx=4)
        ttk.Button(bb, text="Remove", command=self.on_remove_building).pack(side="left")
        rf = ttk.Frame(lower, padding=6)
        lower.add(rf, text="Records in current selection (first 500 shown)")
        self.rec_table = DataTable(rf, 8)
        self.rec_table.pack(fill="both", expand=True)

    def _refresh_data_management(self):
        v = self.validation
        if v is None:
            self.val_label.configure(text=f"Source: {self.source_label}. Generated in memory - no import "
                                          "validation was needed (simulator output is valid by construction).")
            self.val_table.set_data(["Item", "Count"], [])
        else:
            self.val_label.configure(text=f"Source: {self.source_label}   |   Total rows: {v.total_rows:,}   "
                                          f"Accepted: {v.accepted_rows:,}   Rejected: {v.rejected_rows:,}")
            cols = ["csv_line"] + [c for c in v.rejected.columns if c not in ("csv_line", "rejection_reason")] \
                + ["rejection_reason"]
            self.val_table.set_data(cols, v.rejected[cols].astype(str).values.tolist() if v.rejected_rows else [],
                                    {"rejection_reason": 360, "csv_line": 70, "timestamp": 140})
        counts = self.data["building_id"].value_counts() if not self.data.empty else {}
        self.bld_table.set_data(["ID", "Name", "Profile", "Records"],
                                [(b.building_id, b.name, b.category, int(counts.get(b.building_id, 0)))
                                 for b in self.registry], {"ID": 80, "Name": 260, "Profile": 160, "Records": 100})
        rec = self.records_with_cost(self.filtered.head(500)) if not self.filtered.empty else pd.DataFrame()
        cols = ["timestamp", "building_id", "building_name", "interval_hours", "average_power_kw", "energy_kwh",
                "estimated_cost_inr", "data_source"]
        self.rec_table.set_data(cols, [(f"{r.timestamp:%Y-%m-%d %H:%M}", r.building_id, r.building_name,
                                        f"{r.interval_hours:g}", f"{r.average_power_kw:.3f}", f"{r.energy_kwh:.3f}",
                                        f"{r.estimated_cost_inr:.2f}", r.data_source) for r in rec.itertuples()],
                                {"timestamp": 130, "building_name": 160})

    def on_import_csv(self):
        path = self.ask_open_path()
        if not path:
            return
        try:
            res = self.import_csv(path)
        except ValidationError as exc:
            self.show_error("Import failed", str(exc))
            self.show_page("Data Management")
            return
        self.show_info("Import complete", f"Rows read: {res.total_rows:,}\nAccepted: {res.accepted_rows:,}\n"
                                          f"Rejected: {res.rejected_rows:,}" +
                       ("\n\nSee Data Management for rejection reasons." if res.rejected_rows else ""))
        self.show_page("Data Management")

    def on_load_sample(self):
        self.load_default_dataset()
        self.show_info("Dataset loaded", f"{self.source_label}: {len(self.data):,} records.")

    def on_regenerate(self):
        try:
            self.regenerate_dataset()
        except ValueError as exc:
            self.show_error("Cannot generate", str(exc))
            return
        self.show_info("Synthetic data generated", f"{len(self.data):,} synthetic records generated "
                                                   f"for {len(self.registry)} buildings.")

    def on_export_validation(self):
        if self.validation is None:
            self.show_info("Validation summary", "The current dataset was generated in memory, so there is no "
                                                 "import validation summary. Import a CSV first.")
            return
        self._save("validation_summary.csv", ".csv",
                   lambda p: dl.export_validation_summary(self.validation, p), "validation summary")

    def _selected_building_id(self):
        i = self.bld_table.selected_index()
        if i is None:
            self.show_info("Buildings", "Select a building in the table first.")
            return None
        return self.bld_table.tree.item(self.bld_table.tree.selection()[0], "values")[0]

    def on_add_building(self):
        d = BuildingDialog(self, "Add building")
        self.wait_window(d)
        if d.result:
            try:
                self.add_building(*d.result)
            except ValueError as exc:
                self.show_error("Cannot add building", str(exc))
                return
            self.show_info("Building added", f"'{d.result[1]}' added with no records yet. Use 'Regenerate "
                                             "synthetic data' to simulate its readings, or import a CSV containing "
                                             f"building ID {d.result[0]}.")

    def on_edit_building(self):
        bid = self._selected_building_id()
        if not bid:
            return
        d = BuildingDialog(self, "Edit building", self.registry.get(bid))
        self.wait_window(d)
        if d.result:
            try:
                self.edit_building(bid, d.result[1], d.result[2])
            except ValueError as exc:
                self.show_error("Cannot edit building", str(exc))

    def on_remove_building(self):
        bid = self._selected_building_id()
        if not bid:
            return
        b = self.registry.get(bid)
        n = int((self.data["building_id"] == bid).sum()) if not self.data.empty else 0
        if self.ask_yes_no("Remove building", (
                f"Remove '{b.name}' ({bid})?\n\nIts {n:,} records will be removed from the working dataset in "
                "memory and excluded from all calculations, charts and exports. Source CSV files on disk are "
                "NOT changed - reload the sample or re-import to restore them.")):
            removed = self.remove_building(bid)
            self.show_info("Building removed", f"Removed '{b.name}' and {removed:,} records.")

    # ---- Reports
    def _page_reports(self, p):
        self._header(p, "Reports", "Export a PDF analysis report of the current selection, or read the "
                     "automatically generated written summary below. All values are computed from the data.")
        bar = ttk.Frame(p)
        bar.pack(fill="x", pady=4)
        ttk.Button(bar, text="Export PDF analysis report", style="Accent.TButton", command=lambda: self._save(
            "campus_energy_analysis_report.pdf", ".pdf", self.export_pdf, "PDF report")).pack(side="left")
        ttk.Button(bar, text="Export anomaly report (CSV)", command=lambda: self._save(
            "anomaly_report.csv", ".csv", self.export_anomalies, "anomaly report")).pack(side="left", padx=4)
        ttk.Button(bar, text="Export building summary (CSV)", command=lambda: self._save(
            "building_summary.csv", ".csv", self.export_summary, "building summary")).pack(side="left")
        self.report_text = tk.Text(p, wrap="word", font=(self.family, 10), relief="flat", padx=12, pady=10,
                                   bg="white", fg=COLORS["text"])
        self.report_text.pack(fill="both", expand=True)

    def written_summary(self) -> str:
        f, t = self.filtered, self.settings["tariff"]
        if f.empty:
            return "No records match the current selection."
        k = an.kpis(f, t, len(self.anomalies))
        s = an.building_summary(f, t)
        ww = an.weekday_weekend(f)
        comp = an.data_completeness(f)
        lines = [f"Data source: {self.source_label}.", f"Selection: {self.selection_text()}.", "",
                 f"Total consumption was {k['total_kwh']:,.1f} kWh over {k['observed_days']} observed days "
                 f"({k['avg_daily_kwh']:,.1f} kWh/day), an estimated {money(k['total_cost'])} at a flat "
                 f"{RUPEE}{t:g}/kWh.",
                 f"{k['top_building']} used the most energy ({s.iloc[0]['share_pct']:.1f}% of the selection)."]
        if k["peak_kw"] is not None:
            lines.append(f"The maximum 1-hour average demand was {k['peak_kw']:,.1f} kW on "
                         f"{k['peak_time']:%d %b %Y at %H:%M}." + (f" The load factor was {k['load_factor']:.1f}%, "
                                                                     "i.e. average demand is that fraction of the peak."
                                                                     if k["load_factor"] is not None else ""))
        if not ww.dropna().empty:
            lower = [n for n, r in ww.iterrows() if pd.notna(r["Weekend"]) and r["Weekend"] < r["Weekday"]]
            lines.append(f"{len(lower)} of {len(ww)} buildings use less energy per day at weekends than on weekdays.")
        inc = comp[~comp["complete"]]
        lines.append(f"Data completeness: {len(comp) - len(inc)} of {len(comp)} building-days have every expected "
                     "reading." + (" Daily totals on incomplete days are lower because readings are missing, not "
                                   "necessarily because less energy was used." if len(inc) else
                                   " Therefore spikes in daily totals are not caused by missing readings."))
        if len(self.anomalies):
            cats = self.anomalies["category"].value_counts()
            lines.append(f"{len(self.anomalies)} readings were outside their IQR limits: " +
                         ", ".join(f"{v} {c.lower()}" for c, v in cats.items()) + ". " +
                         f"{int(self.anomalies['day_complete'].sum())} of them occurred on days with complete data, "
                         "so they reflect recorded values rather than gaps.")
        lines += ["", ANOMALY_DISCLAIMER, TARIFF_NOTE]
        if "synthetic" in self.source_label.lower():
            lines.append(SYNTHETIC_NOTE)
        return "\n".join(lines)

    def _refresh_reports(self):
        self.report_text.configure(state="normal")
        self.report_text.delete("1.0", "end")
        self.report_text.insert("1.0", self.written_summary())
        self.report_text.configure(state="disabled")

    # ---- Settings
    def _page_settings(self, p):
        self._header(p, "Settings", "Analysis settings apply immediately; simulation settings apply when you "
                     "regenerate synthetic data.")
        self.set_vars = {}
        a = ttk.LabelFrame(p, text="Analysis", padding=10)
        a.pack(fill="x", pady=4)
        b = ttk.LabelFrame(p, text="Synthetic data simulator", padding=10)
        b.pack(fill="x", pady=4)
        fields = [(a, "tariff", f"Flat tariff ({RUPEE}/kWh, illustrative)"),
                  (a, "k", "IQR multiplier k (1.5 = standard)"),
                  (a, "min_iqr_fraction", "IQR noise floor (fraction of median, 0 = textbook IQR)"),
                  (a, "min_group_size", "Minimum comparable-group size before fallback"),
                  (b, "seed", "Random seed"), (b, "days", "Number of days"),
                  (b, "start_date", "Start date (YYYY-MM-DD)")]
        for row, (frame, key, label) in enumerate(fields):
            ttk.Label(frame, text=label, width=48).grid(row=row, column=0, sticky="w", pady=3)
            var = tk.StringVar(value=str(self.settings[key]))
            ttk.Entry(frame, textvariable=var, width=14).grid(row=row, column=1, sticky="w")
            self.set_vars[key] = var
        self.anom_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(b, text="Inject labelled test anomalies", variable=self.anom_var).grid(
            row=len(fields), column=0, sticky="w", pady=3)
        bar = ttk.Frame(p)
        bar.pack(fill="x", pady=8)
        ttk.Button(bar, text="Apply analysis settings", style="Accent.TButton",
                   command=self.on_apply_settings).pack(side="left")
        ttk.Button(bar, text="Apply and regenerate synthetic data",
                   command=lambda: self.on_apply_settings(regenerate=True)).pack(side="left", padx=6)
        ttk.Button(bar, text="Restore defaults", command=self.on_restore_defaults).pack(side="left")

    def update_settings(self, values: dict, regenerate: bool = False) -> None:
        new = dict(self.settings)
        try:
            new["tariff"] = cc.validate_tariff(values.get("tariff", new["tariff"]))
            new["k"] = float(values.get("k", new["k"]))
            new["min_iqr_fraction"] = float(values.get("min_iqr_fraction", new["min_iqr_fraction"]))
            new["min_group_size"] = int(values.get("min_group_size", new["min_group_size"]))
            new["seed"] = int(values.get("seed", new["seed"]))
            new["days"] = int(values.get("days", new["days"]))
        except (TypeError, ValueError):
            raise ValueError("Numeric settings must be valid numbers (seed, days and group size are integers).") from None
        new["start_date"] = str(values.get("start_date", new["start_date"])).strip()
        parse_date(new["start_date"], "Start date")
        new["include_anomalies"] = bool(values.get("include_anomalies", new["include_anomalies"]))
        if not 0 < new["k"] <= 10:
            raise ValueError("IQR multiplier must be between 0 and 10.")
        if not 0 <= new["min_iqr_fraction"] <= 1:
            raise ValueError("IQR noise floor must be between 0 and 1.")
        if not 4 <= new["min_group_size"] <= 1000:
            raise ValueError("Minimum group size must be between 4 and 1000.")
        if not 1 <= new["days"] <= 366:
            raise ValueError("Number of days must be between 1 and 366.")
        self.settings = new
        if regenerate:
            self.regenerate_dataset()
        else:
            self._recompute_anomalies()
            self.apply_filters(quiet=True)

    def on_apply_settings(self, regenerate: bool = False):
        values = {k: v.get() for k, v in self.set_vars.items()}
        values["include_anomalies"] = self.anom_var.get()
        try:
            self.update_settings(values, regenerate)
        except ValueError as exc:
            self.show_error("Invalid setting", str(exc))
            return
        self.show_info("Settings", "Settings applied." + (" Synthetic data regenerated." if regenerate else ""))

    def on_restore_defaults(self):
        defaults = {"tariff": DEFAULT_TARIFF_INR_PER_KWH, "k": DEFAULT_IQR_MULTIPLIER,
                    "min_iqr_fraction": MIN_IQR_FRACTION, "min_group_size": MIN_GROUP_SIZE,
                    "seed": DEFAULT_SEED, "days": DEFAULT_DAYS, "start_date": DEFAULT_START_DATE}
        for k, v in defaults.items():
            self.set_vars[k].set(str(v))
        self.anom_var.set(True)

    def _refresh_settings(self):
        for k, var in self.set_vars.items():
            var.set(str(self.settings[k]))

    # ---- About
    def _page_about(self, p):
        self._header(p, "About Project")
        text = tk.Text(p, wrap="word", font=(self.family, 10), relief="flat", padx=14, pady=12, bg="white")
        text.pack(fill="both", expand=True)
        text.insert("1.0", (
            f"{APP_TITLE} v{APP_VERSION}\n{APP_SUBTITLE}\n\n"
            "Python Programming Laboratory project (B.Tech ECE, 2nd year). A 100% software, offline desktop "
            "application that analyses hourly electricity-consumption records of campus buildings.\n\n"
            "What it does\n"
            "• Generates reproducible synthetic data (fixed seed) or imports CSV files, validating every row.\n"
            "• Computes total/average energy, 1-hour interval-average peak demand, load factor, building "
            "shares and flat-tariff cost estimates.\n"
            "• Flags statistical anomalies with the IQR rule using building x day-type x hour groups.\n"
            "• Shows 8 Matplotlib charts and exports CSV, JSON and PDF reports.\n\n"
            "Core relationships\n"
            "Energy (kWh) = Average power (kW) x Time (h)\nCost (Rs) = Energy (kWh) x Tariff (Rs/kWh)\n"
            "Load factor = Average power / Maximum interval-average power\n"
            "IQR = Q3 - Q1; limits = Q1 - k*IQR and Q3 + k*IQR\n\n"
            "Limitations\n"
            f"• {SYNTHETIC_NOTE}\n• {TARIFF_NOTE}\n• {ANOMALY_DISCLAIMER}\n\n"
            "Keyboard: Ctrl+1..9 / Ctrl+0 switch pages, F5 refresh, Ctrl+O import CSV, Ctrl+E export filtered CSV, "
            "Tab moves between controls.\n\nLicence: MIT."))
        text.configure(state="disabled")
