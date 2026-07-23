"""Headline CSV cleaning and validation."""
from __future__ import annotations

from pathlib import Path

import pandas as pd


def _month_range(series: pd.Series) -> tuple[str | None, str | None]:
    parsed = pd.to_datetime(series, errors="coerce")
    valid = parsed.dropna()
    if valid.empty:
        return None, None
    return valid.min().strftime("%Y-%m"), valid.max().strftime("%Y-%m")


def validate_headlines_df(df: pd.DataFrame) -> list[str]:
    errors: list[str] = []
    if "date" not in df.columns or "headline" not in df.columns:
        errors.append("Headlines file must include columns: date, headline")
    if not errors and df["headline"].astype(str).str.strip().eq("").all():
        errors.append("Headlines file has no usable headline text")
    return errors


def validate_cpi_df(df: pd.DataFrame) -> list[str]:
    errors: list[str] = []
    if "date" not in df.columns or "inflation_rate_pct" not in df.columns:
        errors.append("CPI file must include columns: date, inflation_rate_pct")
    return errors


def validate_fx_df(df: pd.DataFrame) -> list[str]:
    errors: list[str] = []
    if "Date" not in df.columns or "Price" not in df.columns:
        errors.append("FX file must include columns: Date, Price")
    return errors


def validate_labelled_df(df: pd.DataFrame) -> list[str]:
    errors: list[str] = []
    required = {"date", "headline", "relevant", "category", "sentiment"}
    missing = sorted(required - set(df.columns))
    if missing:
        errors.append(f"Labelled CSV must include columns: {', '.join(sorted(required))} (missing: {', '.join(missing)})")
        return errors
    if df["headline"].astype(str).str.strip().eq("").all():
        errors.append("Labelled CSV has no usable headline text")
    return errors


def normalize_labelled_df(df: pd.DataFrame) -> pd.DataFrame:
    """Coerce labelled CSV columns so consolidation can consume them."""
    out = df.copy()
    out["headline"] = out["headline"].astype(str).str.strip()
    out["date"] = pd.to_datetime(out["date"], errors="coerce")
    out = out.dropna(subset=["date"])
    out["date"] = out["date"].dt.strftime("%Y-%m-%d")

    def _as_bool(val):
        if isinstance(val, bool):
            return val
        if pd.isna(val):
            return False
        s = str(val).strip().lower()
        if s in {"true", "1", "yes", "y"}:
            return True
        if s in {"false", "0", "no", "n", ""}:
            return False
        return bool(val)

    out["relevant"] = out["relevant"].map(_as_bool)
    out["category"] = out["category"].where(out["relevant"], None)
    out["sentiment"] = out["sentiment"].where(out["relevant"], None)
    return out.reset_index(drop=True)


def preview_uploads(
    headlines: pd.DataFrame,
    cpi: pd.DataFrame,
    fx: pd.DataFrame,
) -> dict:
    h_min, h_max = _month_range(headlines["date"])
    c_min, c_max = _month_range(cpi["date"])
    fx_parsed = pd.to_datetime(fx["Date"], errors="coerce")
    f_min = fx_parsed.min().strftime("%Y-%m") if fx_parsed.notna().any() else None
    f_max = fx_parsed.max().strftime("%Y-%m") if fx_parsed.notna().any() else None

    overlap_start = max(filter(None, [h_min, c_min, f_min]), default=None)
    overlap_end = min(filter(None, [h_max, c_max, f_max]), default=None)

    return {
        "headline_rows": len(headlines),
        "cpi_rows": len(cpi),
        "fx_rows": len(fx),
        "headline_range": [h_min, h_max],
        "cpi_range": [c_min, c_max],
        "fx_range": [f_min, f_max],
        "overlap_range": [overlap_start, overlap_end],
        "overlap_ok": bool(
            overlap_start and overlap_end and overlap_start <= overlap_end
        ),
    }


def clean_headlines(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["headline"] = out["headline"].astype(str).str.strip()
    out = out[out["headline"].ne("") & out["headline"].ne("nan")]
    out["date"] = pd.to_datetime(out["date"], errors="coerce")
    out = out.dropna(subset=["date"])
    out["date"] = out["date"].dt.strftime("%Y-%m-%d")
    out["year_month"] = pd.to_datetime(out["date"]).dt.strftime("%Y-%m")
    subset = ["date", "headline"]
    if "url" in out.columns:
        subset.append("url")
    if "source" in out.columns:
        subset.append("source")
    out = out.drop_duplicates(subset=subset, keep="first")
    return out.reset_index(drop=True)


def clean_headlines_file(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, engine="python", on_bad_lines="warn")
    cleaned = clean_headlines(df)
    cleaned.to_csv(path, index=False)
    return cleaned


def merge_headline_csvs(frames: list[pd.DataFrame]) -> pd.DataFrame:
    if not frames:
        raise ValueError("No headline files to merge")
    combined = pd.concat(frames, ignore_index=True)
    return clean_headlines(combined)
