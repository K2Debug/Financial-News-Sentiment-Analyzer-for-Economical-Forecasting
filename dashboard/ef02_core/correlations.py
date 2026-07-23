"""Pearson correlation summary for dashboard."""
from __future__ import annotations

import pandas as pd
from scipy import stats


def compute_correlations(viz: pd.DataFrame) -> dict:
    df = viz.copy()
    df["Net_Sentiment"] = df["Positive %"] - df["Negative %"]

    pairs = [
        ("Negative % vs USD/TZS_Rate", "Negative %", "USD/TZS_Rate"),
        ("Net_Sentiment vs USD/TZS_Rate", "Net_Sentiment", "USD/TZS_Rate"),
        ("Positive % vs USD/TZS_Rate", "Positive %", "USD/TZS_Rate"),
        ("Net_Sentiment vs Inflation %", "Net_Sentiment", "Inflation %"),
    ]

    openai: dict[str, dict] = {}
    for key, col_a, col_b in pairs:
        r, p = stats.pearsonr(df[col_a], df[col_b])
        openai[key] = {
            "r": float(r),
            "p": float(p),
            "significant": bool(p <= 0.05),
        }

    return {"openai": openai}


def build_analysis_summary(corr: dict, viz: pd.DataFrame) -> dict:
    """Plain-language research conclusion from correlation results."""
    model = corr.get("openai", {})
    pairs = [
        ("Negative % vs USD/TZS Rate", "Negative % vs USD/TZS_Rate"),
        ("Net Sentiment vs USD/TZS Rate", "Net_Sentiment vs USD/TZS_Rate"),
        ("Positive % vs USD/TZS Rate", "Positive % vs USD/TZS_Rate"),
        ("Net Sentiment vs Inflation %", "Net_Sentiment vs Inflation %"),
    ]
    significant = []
    not_significant = []
    for display, key in pairs:
        row = model.get(key, {})
        if row.get("significant"):
            significant.append({"pair": display, "r": row.get("r"), "p": row.get("p")})
        else:
            not_significant.append({"pair": display, "r": row.get("r"), "p": row.get("p")})

    fx_sig = any("USD/TZS" in s["pair"] for s in significant)
    infl_sig = any("Inflation" in s["pair"] for s in significant)

    if significant:
        verdict = (
            "Statistically significant sentiment–macro correlations were found (p ≤ 0.05). "
            + ("FX rate links dominate. " if fx_sig and not infl_sig else "")
            + ("Inflation links are present. " if infl_sig else "")
            + f"{len(significant)} of {len(pairs)} tested pairs reached significance."
        )
    else:
        verdict = (
            "No sentiment–macro pair reached conventional significance (p ≤ 0.05) "
            f"across {len(viz)} monthly observations. "
            "Sentiment alone may not be a reliable concurrent indicator on this window."
        )

    return {
        "significant_pairs": significant,
        "not_significant_pairs": not_significant,
        "verdict": verdict,
        "months": len(viz),
        "has_significant_fx": fx_sig,
        "has_significant_inflation": infl_sig,
        "any_significant": bool(significant),
    }
