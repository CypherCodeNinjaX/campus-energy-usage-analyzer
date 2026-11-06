# Methodology

## 1. Data input
* **Simulator** (`simulator.py`): `P = P_base + (P_peak − P_base) × activity(hour, weekday)`, times noise `N(1, σ)` clipped to [0.7, 1.3] → never negative. Activity = 1 in active hours, 0.35 in the hour before/after, 0.8 at 13:00, otherwise 0; multiplied by the building's weekend factor. `E = P × 1 h`. Eight anomalies are injected at fixed times and labelled in `injected_anomaly`.
* **CSV import** (`data_loader.py`): read entirely as text (`dtype=str`) so rejected rows can be shown exactly as written.

## 2. Validation rules (`validation.py`)
| Check | Handling |
|---|---|
| Required column missing | whole file rejected with list of missing columns |
| Blank timestamp / unparseable timestamp | row rejected (`missing timestamp` / `invalid date format`) |
| Blank building ID or name | row rejected |
| Blank or non-numeric number | row rejected — **never replaced by 0** |
| `inf` values | row rejected |
| Negative power or energy | row rejected |
| `interval_hours ≤ 0` or `> 24` | row rejected |
| `|E − P·t| > max(0.01 kWh, 1 %)` | row rejected (inconsistent) |
| Same ID with a different name | row rejected (first name wins) |
| Duplicate (building ID, timestamp) | first kept, later copies rejected |

A row can collect several reasons. Rejected rows keep their CSV line number.

## 3. Definitions
* **Observed days** = dates with at least one valid reading (not the calendar span).
* **Campus demand** `P_c(t) = Σ_b P_b(t)` only at timestamps where **every selected building** reports (prevents under-counting the peak when a building is missing).
* **Average power** = total energy / observed duration = mean `P_c`.
* **Maximum recorded demand** = max `P_c` — a 1-hour interval average, not an instantaneous peak and not utility billing demand.
* **Load factor** = `P_avg / P_max × 100 %`; only when all intervals are equal and ≥ 24 complete timestamps exist.
* **Cost** = `E × tariff` (flat). ₹8/kWh is illustrative and user-configurable.
* **% change** = `(current − previous)/previous × 100`; `n/a` when previous = 0.

## 4. Anomaly detection (`anomaly_detection.py`)
1. Compare **interval-average power (kW)** so different interval lengths stay comparable.
2. Group each reading with the same **building × day type (weekday/weekend) × hour of day**.
3. Fallback if a group has < 8 readings: building × day type, then whole building; < 4 readings → not evaluated.
4. `IQR = Q3 − Q1` (NumPy linear percentiles), `IQR′ = max(IQR, 0.10 × median)` (noise floor; set 0 for textbook IQR), limits `Q1 − k·IQR′`, `Q3 + k·IQR′`, k = 1.5.
5. Category: below lower → *Unusually low reading*; above upper outside weekday 08:00–17:59 → *Unexpected off-hours consumption*; > 50 % jump from previous reading → *Sudden demand increase*; else *High consumption*.
6. `day_complete` shows whether the building had every reading that day (spike vs incomplete data).

Thresholds are computed on the whole dataset, then filtered for display, so they do not change when you zoom into a few days.

**Evaluation on the sample (k = 1.5):** global campus threshold 4/8 injected found (66 other flags); building-only 2/8 (319); building × day type × hour 8/8 (12).

**A statistical anomaly is not proof of electrical equipment failure, energy theft, or malfunction.**
