# User Guide

## Start
`python -m campus_energy.main` (see README for installation). The bundled synthetic dataset loads automatically; the header shows the data source, record count, date range and tariff. Green dot = records match the filter, amber = none.

## Filter bar (top)
* **Building** – one building or *All buildings*.
* **From / To** – inclusive dates `YYYY-MM-DD` (prefilled with the dataset range).
* **Apply (F5)** recalculates every page; **Reset** restores all buildings and the full range.
* **Export filtered CSV** saves the selected records with cost at the current tariff.

## Pages
| Page | What you can do |
|---|---|
| Overview | 8 KPIs, daily trend, building comparison |
| Energy Analysis | tabs: daily trend + 7-day average, hourly profile, heatmap, weekday vs weekend |
| Building Comparison | bar chart + table (energy, share, avg/peak kW, load factor, cost); export summary |
| Peak Demand | campus demand with top-10 readings, average line, load factor, top individual readings |
| Anomaly Detection | flagged readings chart and table; double-click / *Inspect selected* for details; export report |
| Cost Calculator | change tariff, building/daily/monthly cost, compare two periods |
| Data Management | import CSV, load sample, regenerate synthetic data, validation results, building add/edit/remove, record preview, JSON/validation exports |
| Reports | export PDF analysis report; automatically written summary |
| Settings | tariff, IQR k, noise floor, min group size; simulator seed, days, start date, injected anomalies |
| About Project | formulas, limitations, shortcuts |

Every chart has a toolbar: home, back/forward, pan, zoom, subplot settings, save image.

## Importing your own data
CSV header: `timestamp,building_id,building_name,interval_hours,average_power_kw,energy_kwh`. After import a dialog shows rows read/accepted/rejected; Data Management lists each rejected row with its line number and reason. Try `data/sample_invalid_rows.csv`.

## Buildings
*Add* creates a building with no records (use *Regenerate synthetic data* or import its readings). *Edit* changes name/profile everywhere. *Remove* asks for confirmation and removes the building's records from the working dataset in memory only — files on disk are not changed; reload to restore.

## Keyboard
`Ctrl+1…9`, `Ctrl+0` pages · `F5` refresh · `Ctrl+O` import · `Ctrl+E` export · `Tab` moves focus · `Enter` in the tariff box applies it.

Logs are written to `.campus_energy_analyzer.log` in your home folder.
