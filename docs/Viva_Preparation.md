# Viva Preparation — Campus Energy Usage Analyzer

## Purpose of each Python file
| File | One-line explanation |
|---|---|
| `config.py` | All constants in one place: tariff, IQR k, default buildings, colours, portable paths. |
| `models.py` | Classes: `Building`, `MeterRecord` (one reading), `BuildingRegistry` (dict of buildings), `EnergyDataset` (DataFrame wrapper with `__len__`, `__iter__`, `__getitem__`). |
| `simulator.py` | Creates reproducible synthetic hourly data with building-specific load profiles and injected anomalies. |
| `validation.py` | Checks every imported row and records why bad rows are rejected. |
| `data_loader.py` | Reads CSV files and writes CSV/JSON exports. |
| `analytics.py` | Energy totals, daily averages, campus demand, peak, load factor, summaries, moving average. |
| `anomaly_detection.py` | IQR outlier detection within comparable groups. |
| `cost_calculator.py` | Tariff validation and cost estimates. |
| `visualizations.py` | Eight chart functions drawing on Matplotlib figures. |
| `report_generator.py` | Builds the PDF analysis report. |
| `dashboard.py` | The Tkinter window: pages, filters, KPI cards, tables, dialogs. |
| `main.py` | Entry point: sets up logging and starts the app. |

## 32 questions with short answers

**Python fundamentals**
1. **Why Python?** Readable syntax and mature libraries (Pandas, NumPy, Matplotlib, Tkinter) for data analysis and GUIs.
2. **What is a module and a package?** A module is one `.py` file; a package is a folder of modules with `__init__.py` (`campus_energy`).
3. **What does `if __name__ == "__main__":` do?** Runs `main()` only when the file is executed, not when it is imported.
4. **What is a function? Example?** A named reusable block; `energy_cost(energy_kwh, tariff)` returns `round(energy × tariff, 2)`.
5. **List vs dictionary?** A list is ordered and indexed by position; a dictionary maps keys to values. `BuildingRegistry` stores buildings in a dict keyed by building ID for fast lookup.
6. **What is exception handling here?** `try/except` catches bad input, e.g. a non-numeric tariff raises `ValueError`, shown in an error dialog instead of crashing.

**OOP**
7. **Class vs object?** A class is a blueprint (`MeterRecord`); an object is one instance (one reading at 10:00 for B001).
8. **What is a dataclass?** A decorator that auto-generates `__init__`, `__repr__` and `__eq__` from field definitions.
9. **Which special methods did you implement and why?** `__len__`, `__iter__`, `__getitem__` in `EnergyDataset` so it behaves like a sequence: `len(ds)`, `for r in ds`, `ds[0]`.
10. **What is encapsulation in your project?** Building rules (unique IDs/names, non-empty names) live inside `BuildingRegistry`; the GUI cannot bypass them.

**File handling & CSV**
11. **How is a CSV imported?** `pandas.read_csv(dtype=str, keep_default_na=False)` so original text is kept, then validated.
12. **Why `pathlib`?** Portable paths on Windows and Linux; no hard-coded user folders.
13. **What exports exist?** Filtered records, building summary, anomaly report, validation summary (CSV), monthly summary (JSON), PDF report.

**Pandas / NumPy / Matplotlib / Tkinter**
14. **What is a DataFrame?** A table with labelled columns; we use `groupby`, `pivot_table`, filtering and `to_csv`.
15. **Example of `groupby`?** Building summary: `df.groupby(["building_id","building_name"])["energy_kwh"].sum()`.
16. **Where is NumPy used?** `np.percentile` for quartiles, `np.convolve` for the 7-day moving average, random numbers for simulation.
17. **How are charts shown inside Tkinter?** `FigureCanvasTkAgg` embeds a Matplotlib `Figure`; `NavigationToolbar2Tk` adds zoom/pan/save.
18. **Why not `pyplot` in the GUI?** pyplot keeps global state; drawing on separate `Figure` objects is safer and reusable for the PDF.
19. **How does navigation work?** All pages are frames in the same grid cell; `tkraise()` brings the selected one to the front.
20. **How did you test a GUI?** Data-changing actions are methods (`import_csv`, `set_tariff`, `remove_building`) that tests call directly on the real window; dialogs are replaced by test stubs.

**Energy concepts**
21. **kW vs kWh?** kW is power (rate); kWh is energy (power × time). A 10 kW load for 2 h uses 20 kWh.
22. **How is energy computed from a reading?** `E = average power × interval` → 1-hour interval: kWh equals kW numerically.
23. **What is peak demand here?** The highest 1-hour **average** campus demand (242.1 kW in the sample) — not the instantaneous peak and not the utility's billing demand.
24. **What is load factor?** Average power ÷ peak power. Sample: 86.16 / 242.11 = 35.6 %. Low LF means a peaky load (labs).
25. **How is cost estimated?** Energy × flat tariff (₹8/kWh, illustrative, editable). Real bills add fixed, demand and tax charges.
26. **Why define average daily energy over observed days?** Dividing by calendar days would understate usage if some days have no data.

**Validation, statistics & anomalies**
27. **Name five validation checks.** Missing timestamp, negative energy, inf value, duplicate building-timestamp, energy ≠ power × interval.
28. **Why not fill missing values with zero?** Zero is a real measurement (no consumption); filling would falsely lower totals.
29. **What is the IQR rule?** IQR = Q3 − Q1; values below Q1 − 1.5·IQR or above Q3 + 1.5·IQR are outliers. Robust because quartiles are not pulled by extremes.
30. **Why not one campus-wide threshold?** Labs and libraries have different normal levels and 02:00 differs from 14:00. Our evaluation: global threshold found 4/8 injected anomalies, building × day type × hour found 8/8.
31. **Is an anomaly a fault?** No. A statistical anomaly is not proof of equipment failure, theft or malfunction — only that a reading is unusual for its group.

**Simulation, testing, limitations**
32. **Why a fixed random seed?** Same seed → identical dataset, so results and tests are reproducible.
33. **How many tests, and what do they cover?** 73 pytest tests: simulator, validation, analytics, cost, anomalies, GUI; 86 % coverage in the latest run.
34. **Main limitations?** Synthetic data, no meter connection, hourly resolution, flat tariff, statistical (not diagnostic) anomalies.
