"""Monthly aggregation and merge with CPI / FX data."""
from __future__ import annotations

from pathlib import Path

import pandas as pd


def run_consolidation(
    label_path: Path,
    cpi_path: Path,
    fx_path: Path,
    viz_out: Path,
) -> pd.DataFrame:
    df_exc = pd.read_csv(fx_path)
    df_exc["Price"] = df_exc["Price"].astype(str).str.replace(",", "", regex=False).str.strip()
    df_exc["Price"] = pd.to_numeric(df_exc["Price"], errors="coerce")
    df_exc["Date"] = pd.to_datetime(df_exc["Date"], errors="coerce")
    df_exc_monthly = df_exc.set_index("Date").resample("ME")["Price"].mean().reset_index()
    df_exc_monthly["YearMonth"] = df_exc_monthly["Date"].dt.strftime("%Y-%m")
    df_exc_monthly["Rate_Change_%"] = df_exc_monthly["Price"].pct_change(fill_method=None) * 100
    df_exc_monthly = df_exc_monthly[["YearMonth", "Price", "Rate_Change_%"]].rename(
        columns={"Price": "USD/TZS_Rate"}
    )
    df_exc_monthly["Rate_Change_%"] = df_exc_monthly["Rate_Change_%"].fillna(0)

    df_cpi = pd.read_csv(cpi_path)
    df_cpi["date"] = pd.to_datetime(df_cpi["date"], errors="coerce")
    df_cpi_monthly = df_cpi.copy()
    df_cpi_monthly["YearMonth"] = df_cpi_monthly["date"].dt.strftime("%Y-%m")
    drop_cols = [c for c in ("date", "all_items_index") if c in df_cpi_monthly.columns]
    df_cpi_monthly = df_cpi_monthly.drop(columns=drop_cols)
    df_cpi_monthly = df_cpi_monthly.rename(columns={"inflation_rate_pct": "inflation_rate_%"})

    df_hdl = pd.read_csv(label_path)
    relevant = df_hdl["relevant"]
    if relevant.dtype == object:
        relevant = relevant.astype(str).str.strip().str.lower().isin(["true", "1", "yes", "y"])
    else:
        relevant = relevant.astype(bool)
    df_hdl = df_hdl[relevant]
    df_hdl_clean = df_hdl[["date", "headline", "category", "sentiment"]].copy()
    df_hdl_clean["date"] = pd.to_datetime(df_hdl_clean["date"], format="%Y-%m-%d", errors="coerce")
    df_hdl_clean["YearMonth"] = df_hdl_clean["date"].dt.strftime("%Y-%m")
    df_hdl_clean["category"] = df_hdl_clean["category"].astype("category")
    df_hdl_clean["sentiment"] = df_hdl_clean["sentiment"].astype("category")

    headline_counts = df_hdl_clean.groupby("YearMonth", observed=True).size().reset_index(name="num_headlines")
    top_category = (
        df_hdl_clean.groupby(["YearMonth", "category"], observed=True)
        .size()
        .reset_index(name="count")
    )
    top_category["category %"] = top_category.groupby("YearMonth")["count"].transform(
        lambda x: x / x.sum() * 100
    ).round(2)
    top_category = (
        top_category.sort_values(["YearMonth", "category %"], ascending=[True, False])
        .groupby("YearMonth")
        .first()
        .reset_index()
        .drop(columns=["count"])
    )
    sentiment_counts = (
        df_hdl_clean.groupby(["YearMonth", "sentiment"], observed=True)
        .size()
        .unstack(fill_value=0)
        .reset_index()
    )
    sentiment_cols = [c for c in sentiment_counts.columns if c != "YearMonth"]
    sentiment_counts[sentiment_cols] = (
        sentiment_counts[sentiment_cols].div(sentiment_counts[sentiment_cols].sum(axis=1), axis=0) * 100
    ).round(2)
    sentiment_counts["Avg_sentiment"] = sentiment_counts[sentiment_cols].idxmax(axis=1)
    df_hdl_monthly = headline_counts.merge(top_category, on="YearMonth").merge(sentiment_counts, on="YearMonth")

    df_merge = pd.merge(df_hdl_monthly, df_cpi_monthly, on="YearMonth", how="inner")
    df_merge = pd.merge(df_merge, df_exc_monthly, on="YearMonth", how="inner")
    df_merge = df_merge.rename(
        columns={
            "category": "Top_Category",
            "Negative": "Negative %",
            "Neutral": "Neutral %",
            "Positive": "Positive %",
            "Avg_sentiment": "Dominant_Sentiment",
            "inflation_rate_%": "Inflation %",
        }
    )
    viz_out.parent.mkdir(parents=True, exist_ok=True)
    df_merge.to_csv(viz_out, index=False)
    return df_merge
