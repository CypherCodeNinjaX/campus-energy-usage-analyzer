# Data folder

| File | Content |
|---|---|
| `sample_energy_data.csv` | **Synthetic** demonstration dataset: 3,600 hourly records, 5 buildings, 1–30 Oct 2026, seed 42. Not real meter data. Regenerate with `python scripts/generate_sample_data.py`. |
| `sample_invalid_rows.csv` | 16 hand-written rows (5 valid, 11 invalid) that exercise every validation rule. Import it from *Data Management* to see rejection reasons. |

Columns: `timestamp` (`YYYY-MM-DD HH:MM:SS`), `building_id`, `building_name`, `interval_hours` (h), `average_power_kw` (kW), `energy_kwh` (kWh = kW × h), `estimated_cost_inr` (₹, recomputed by the app from the current tariff), `data_source` (`synthetic`), `injected_anomaly` (ground-truth label of the 8 injected test anomalies, empty otherwise).
