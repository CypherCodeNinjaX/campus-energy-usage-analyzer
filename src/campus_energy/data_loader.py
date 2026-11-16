"""CSV/JSON input and output helpers (portable pathlib paths only)."""
from __future__ import annotations

import json
import logging
from pathlib import Path

import pandas as pd

from .config import SAMPLE_DATA_FILE, TIMESTAMP_FORMAT
from .validation import ValidationError, ValidationResult, validate_dataframe

log = logging.getLogger(__name__)


def read_raw_csv(path: str | Path) -> pd.DataFrame:
    """Read a CSV as text so that the original values are preserved."""
    path = Path(path)
    if not path.is_file():
        raise ValidationError(f"File not found: {path}")
    try:
        return pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    except pd.errors.EmptyDataError:
        raise ValidationError("The CSV file is empty.") from None
    except (pd.errors.ParserError, UnicodeDecodeError) as exc:
        raise ValidationError(f"The file is not a readable CSV: {exc}") from None


def load_csv(path: str | Path) -> ValidationResult:
    result = validate_dataframe(read_raw_csv(path))
    log.info("Loaded %s: %d rows, %d accepted, %d rejected",
             path, result.total_rows, result.accepted_rows, result.rejected_rows)
    return result


def load_sample(path: str | Path = SAMPLE_DATA_FILE) -> ValidationResult | None:
    """Load the bundled sample dataset if it exists, else None."""
    return load_csv(path) if Path(path).is_file() else None


def _format_for_csv(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in out.columns:
        if pd.api.types.is_datetime64_any_dtype(out[col]):
            out[col] = out[col].dt.strftime(TIMESTAMP_FORMAT)
    return out


def export_csv(df: pd.DataFrame, path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    _format_for_csv(df).to_csv(path, index=False, float_format="%.3f")
    log.info("Exported %d rows to %s", len(df), path)
    return path


def export_json(obj, path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, default=str), encoding="utf-8")
    return path


def export_validation_summary(result: ValidationResult, path: str | Path) -> Path:
    """Write counts and every rejected row (with reasons) to one CSV."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        result.summary_frame().to_csv(fh, index=False)
        fh.write("\n")
        if result.rejected_rows:
            result.rejected.to_csv(fh, index=False)
        else:
            fh.write("No rows were rejected.\n")
    return path
