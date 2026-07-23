"""Label reliability audit: Groq vs GPT-4o-mini."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pandas as pd
from scipy import stats

ROOT = Path(__file__).resolve().parents[1]
EF02 = ROOT.parent / "EF-02"
AUDIT = ROOT / "data" / "audit"
AUDIT.mkdir(parents=True, exist_ok=True)

GROQ_LABEL = EF02 / "data" / "processed" / "tz_headlines_labelled.csv"
OAI_LABEL = ROOT / "data" / "processed" / "tz_headlines_labelled.csv"
GROQ_VIZ = EF02 / "data" / "processed" / "Visualization_Data.csv"
OAI_VIZ = ROOT / "data" / "processed" / "Visualization_Data.csv"

VALID_CATEGORIES = {
    "Forex", "Policy", "Banking", "Trade",
    "Agriculture", "Energy", "Transport", "Investment",
    "Markets", "Tourism", "Inflation",
}
VALID_SENTIMENTS = {"Positive", "Negative", "Neutral"}


def _quality_scorecard(df: pd.DataFrame, name: str) -> dict:
    rel = df[df["relevant"] == True]
    n_rel = len(rel)
    metrics = {
        "name": name,
        "total_rows": len(df),
        "relevant_count": n_rel,
        "relevant_pct": round(n_rel / len(df) * 100, 1),
        "failed_relevant_nan": int(df["relevant"].isna().sum()),
        "relevant_null_sentiment": int(rel["sentiment"].isna().sum()),
        "relevant_null_category": int(rel["category"].isna().sum()),
        "invalid_categories": int(rel[~rel["category"].isin(VALID_CATEGORIES) & rel["category"].notna()].shape[0]),
        "sentiment_distribution": {
            k: int(v) for k, v in rel["sentiment"].value_counts(dropna=False).items()
        },
        "positive_pct_of_relevant": round(
            (rel["sentiment"] == "Positive").sum() / n_rel * 100, 1
        ) if n_rel else 0,
        "neutral_pct_of_relevant": round(
            (rel["sentiment"] == "Neutral").sum() / n_rel * 100, 1
        ) if n_rel else 0,
        "positive_bias_alarm": bool((rel["sentiment"] == "Positive").sum() / n_rel > 0.7) if n_rel else False,
    }
    if "year_month" in df.columns:
        null_by_month = (
            rel[rel["sentiment"].isna()]
            .groupby("year_month")
            .size()
            .sort_values(ascending=False)
            .head(5)
        )
        metrics["top_null_sentiment_months"] = {str(k): int(v) for k, v in null_by_month.items()}
    return metrics


def _monthly_sentiment_impact(groq: pd.DataFrame) -> pd.DataFrame:
    rel = groq[groq["relevant"] == True].copy()
    rel["date"] = pd.to_datetime(rel["date"], errors="coerce")
    rel["YearMonth"] = rel["date"].dt.strftime("%Y-%m")

    def agg(sub):
        counts = sub.groupby("sentiment", observed=True).size()
        total = counts.sum()
        if total == 0:
            return pd.Series({"Positive %": 0, "Neutral %": 0, "Negative %": 0, "n": 0})
        return pd.Series({
            "Positive %": round(counts.get("Positive", 0) / total * 100, 2),
            "Neutral %": round(counts.get("Neutral", 0) / total * 100, 2),
            "Negative %": round(counts.get("Negative", 0) / total * 100, 2),
            "n": int(total),
        })

    with_null = rel.groupby("YearMonth", observed=True).apply(agg, include_groups=False).reset_index()
    without_null = (
        rel[rel["sentiment"].notna()]
        .groupby("YearMonth", observed=True)
        .apply(agg, include_groups=False)
        .reset_index()
    )
    merged = with_null.merge(without_null, on="YearMonth", suffixes=("_with_null", "_no_null"))
    merged["positive_delta_pp"] = merged["Positive %_no_null"] - merged["Positive %_with_null"]
    return merged


def _merge_labels(groq: pd.DataFrame, oai: pd.DataFrame) -> pd.DataFrame:
    return groq.merge(oai, on=["date", "headline", "url"], suffixes=("_groq", "_oai"))


def _disagreement_buckets(m: pd.DataFrame) -> dict:
    both_rel = m[(m["relevant_groq"] == True) & (m["relevant_oai"] == True)]
    buckets = {
        "groq_relevant_only": m[(m["relevant_groq"] == True) & (m["relevant_oai"] == False)],
        "openai_relevant_only": m[(m["relevant_groq"] == False) & (m["relevant_oai"] == True)],
        "neutral_to_positive": both_rel[
            (both_rel["sentiment_groq"] == "Neutral") & (both_rel["sentiment_oai"] == "Positive")
        ],
        "negative_to_positive": both_rel[
            (both_rel["sentiment_groq"] == "Negative") & (both_rel["sentiment_oai"] == "Positive")
        ],
        "groq_null_to_oai_positive": both_rel[
            both_rel["sentiment_groq"].isna() & (both_rel["sentiment_oai"] == "Positive")
        ],
        "category_disagree": both_rel[both_rel["category_groq"] != both_rel["category_oai"]],
        "full_agreement": both_rel[
            (both_rel["sentiment_groq"] == both_rel["sentiment_oai"])
            & both_rel["sentiment_groq"].notna()
            & (both_rel["category_groq"] == both_rel["category_oai"])
        ],
    }
    return {k: len(v) for k, v in buckets.items()}, buckets


def _sample_rows(df: pd.DataFrame, n: int, label: str) -> pd.DataFrame:
    if len(df) == 0:
        return pd.DataFrame()
    take = df.sample(n=min(n, len(df)), random_state=42).copy()
    take["disagreement_type"] = label
    return take


def export_manual_review(m: pd.DataFrame, buckets: dict) -> pd.DataFrame:
    parts = [
        _sample_rows(buckets["negative_to_positive"], 25, "negative_to_positive"),
        _sample_rows(buckets["neutral_to_positive"], 25, "neutral_to_positive"),
        _sample_rows(buckets["groq_relevant_only"], 8, "groq_relevant_only"),
        _sample_rows(buckets["openai_relevant_only"], 7, "openai_relevant_only"),
        _sample_rows(
            m[(m["relevant_groq"] == True) & m["sentiment_groq"].isna()], 15, "groq_null_sentiment"
        ),
        _sample_rows(
            m[(m["relevant_oai"] == True) & m["category_oai"].isna()], 15, "openai_null_category"
        ),
        _sample_rows(buckets["full_agreement"], 5, "full_agreement"),
    ]
    sample = pd.concat([p for p in parts if len(p)], ignore_index=True)

    out = pd.DataFrame({
        "headline": sample["headline"],
        "date": sample["date"],
        "source": sample["source_groq"] if "source_groq" in sample.columns else sample.get("source", ""),
        "relevant_groq": sample["relevant_groq"],
        "relevant_openai": sample["relevant_oai"],
        "category_groq": sample["category_groq"],
        "category_openai": sample["category_oai"],
        "sentiment_groq": sample["sentiment_groq"],
        "sentiment_openai": sample["sentiment_oai"],
        "disagreement_type": sample["disagreement_type"],
        "your_relevant": "",
        "your_category": "",
        "your_sentiment": "",
        "notes": "",
    })
    path = AUDIT / "disagreement_review_sample.csv"
    out.to_csv(path, index=False)
    print(f"Exported {len(out)} rows to {path}")
    return out


def _top_correlations(viz: pd.DataFrame) -> dict:
    viz = viz.copy()
    viz["Net_Sentiment"] = viz["Positive %"] - viz["Negative %"]
    pairs = [
        ("Negative %", "USD/TZS_Rate"),
        ("Net_Sentiment", "USD/TZS_Rate"),
        ("Positive %", "USD/TZS_Rate"),
        ("Net_Sentiment", "Inflation %"),
    ]
    result = {}
    for s, e in pairs:
        r, p = stats.pearsonr(viz[s], viz[e])
        result[f"{s} vs {e}"] = {"r": round(float(r), 3), "p": round(float(p), 4), "significant": bool(p < 0.05)}
    return result


def agreement_only_consolidation(groq: pd.DataFrame, oai: pd.DataFrame) -> pd.DataFrame:
    m = _merge_labels(groq, oai)
    agreed = m[
        (m["relevant_groq"] == True)
        & (m["relevant_oai"] == True)
        & (m["sentiment_groq"] == m["sentiment_oai"])
        & m["sentiment_groq"].notna()
    ].copy()
    agreed["relevant"] = True
    agreed["category"] = agreed["category_groq"]
    agreed["sentiment"] = agreed["sentiment_groq"]
    agreed["date"] = agreed["date"]
    if "source_groq" in agreed.columns:
        agreed["source"] = agreed["source_groq"]

    # Reuse consolidation logic inline
    df_hdl_clean = agreed[["date", "headline", "category", "sentiment"]].copy()
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
    top_category["category %"] = top_category.groupby("YearMonth")["count"].transform(lambda x: x / x.sum() * 100).round(2)
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

    df_exc = pd.read_csv(EF02 / "data" / "raw" / "usd_tzs_2022_2024.csv")
    df_exc["Price"] = pd.to_numeric(df_exc["Price"].astype(str).str.replace(",", "", regex=False), errors="coerce")
    df_exc["Date"] = pd.to_datetime(df_exc["Date"], format="%m/%d/%Y")
    df_exc_monthly = df_exc.set_index("Date").resample("ME")["Price"].mean().reset_index()
    df_exc_monthly["YearMonth"] = df_exc_monthly["Date"].dt.strftime("%Y-%m")
    df_exc_monthly["Rate_Change_%"] = df_exc_monthly["Price"].pct_change(fill_method=None) * 100
    df_exc_monthly = df_exc_monthly[["YearMonth", "Price", "Rate_Change_%"]].rename(columns={"Price": "USD/TZS_Rate"})
    df_exc_monthly["Rate_Change_%"] = df_exc_monthly["Rate_Change_%"].fillna(0)

    df_cpi = pd.read_csv(EF02 / "data" / "raw" / "tanzania_cpi_2022_2024.csv")
    df_cpi["date"] = pd.to_datetime(df_cpi["date"], format="%Y-%m-%d")
    df_cpi_monthly = df_cpi.copy()
    df_cpi_monthly["YearMonth"] = df_cpi_monthly["date"].dt.strftime("%Y-%m")
    df_cpi_monthly = df_cpi_monthly.drop(columns=["date", "all_items_index"])
    df_cpi_monthly = df_cpi_monthly.rename(columns={"inflation_rate_pct": "inflation_rate_%"})

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
    path = AUDIT / "Visualization_Data_agreement_only.csv"
    df_merge.to_csv(path, index=False)
    print(f"Agreement-only consolidation: {len(agreed)} headlines -> {len(df_merge)} months -> {path}")
    return df_merge


def run_gold_eval() -> dict:
    out_path = AUDIT / "gold_eval_scores.json"
    if out_path.exists():
        print(f"Using cached gold eval: {out_path}")
        return json.loads(out_path.read_text(encoding="utf-8"))
    script = EF02 / "scripts" / "prompt_eval.py"
    subprocess.run(
        [sys.executable, str(script), "--provider", "both", "--out", str(out_path)],
        check=True,
    )
    return json.loads(out_path.read_text(encoding="utf-8"))


def write_audit_report(metrics: dict, gold: dict, correlations: dict) -> None:
    groq = metrics["groq"]
    oai = metrics["openai"]
    buckets = metrics["disagreement_counts"]
    agree_corr = correlations["agreement_only"]
    groq_corr = correlations["groq"]
    oai_corr = correlations["openai"]

    g_gold = gold.get("groq", {})
    o_gold = gold.get("openai", {})

    report = f"""# Label Reliability Audit Report

Groq (`llama-3.1-8b-instant`) vs OpenAI (`gpt-4o-mini`) on shared `tz_headlines_clean.csv` input.

## 1. Data quality scorecard

| Metric | Groq | OpenAI |
|--------|------|--------|
| Relevant rows | {groq['relevant_count']} ({groq['relevant_pct']}%) | {oai['relevant_count']} ({oai['relevant_pct']}%) |
| Relevant + null sentiment | **{groq['relevant_null_sentiment']}** | {oai['relevant_null_sentiment']} |
| Relevant + null category | {groq['relevant_null_category']} | **{oai['relevant_null_category']}** |
| Positive % of relevant | {groq['positive_pct_of_relevant']}% | **{oai['positive_pct_of_relevant']}%** |
| Neutral % of relevant | {groq['neutral_pct_of_relevant']}% | {oai.get('neutral_pct_of_relevant', 'n/a')}% |
| Positive-bias alarm (>70%) | {groq['positive_bias_alarm']} | {oai['positive_bias_alarm']} |

**Groq anomaly:** {groq['relevant_null_sentiment']} relevant headlines lack sentiment — likely incomplete retry after relabeling. These distort monthly sentiment aggregates until fixed.

**OpenAI anomaly:** {oai['relevant_null_category']} relevant rows lost category after schema enforcement; {oai['positive_pct_of_relevant']}% positive rate vs Groq's {groq['positive_pct_of_relevant']}% suggests systematic positive upgrading.

## 2. Disagreement anatomy

| Bucket | Count |
|--------|-------|
| Groq relevant only | {buckets['groq_relevant_only']} |
| OpenAI relevant only | {buckets['openai_relevant_only']} |
| Neutral → Positive | {buckets['neutral_to_positive']} |
| Negative → Positive | {buckets['negative_to_positive']} |
| Groq null → OpenAI Positive | {buckets['groq_null_to_oai_positive']} |
| Category disagree (both relevant) | {buckets['category_disagree']} |
| Full agreement (rel + cat + sent) | {buckets['full_agreement']} |

Manual review sample: `disagreement_review_sample.csv` (~100 stratified rows).

## 3. Gold-set 3-in-1 evaluation (`project_testing.csv`)

| Metric | Groq | OpenAI |
|--------|------|--------|
| Relevance accuracy | {g_gold.get('relevance_acc', 'n/a')} | {o_gold.get('relevance_acc', 'n/a')} |
| Sentiment accuracy | {g_gold.get('sentiment_acc', 'n/a')} | {o_gold.get('sentiment_acc', 'n/a')} |
| Category accuracy | {g_gold.get('category_acc', 'n/a')} | {o_gold.get('category_acc', 'n/a')} |
| Strict 3-in-1 accuracy | {g_gold.get('strict_3in1_acc', 'n/a')} | {o_gold.get('strict_3in1_acc', 'n/a')} |
| Pred positive % | {g_gold.get('pred_positive_pct', 'n/a')}% | {o_gold.get('pred_positive_pct', 'n/a')}% |

## 4. Correlation robustness (36 months)

### Groq monthly data
"""
    for k, v in groq_corr.items():
        sig = " *" if v["significant"] else ""
        report += f"- {k}: r={v['r']}, p={v['p']}{sig}\n"

    report += "\n### OpenAI monthly data\n"
    for k, v in oai_corr.items():
        sig = " *" if v["significant"] else ""
        report += f"- {k}: r={v['r']}, p={v['p']}{sig}\n"

    report += "\n### Agreement-only labels (both models agree on relevance + sentiment)\n"
    for k, v in agree_corr.items():
        sig = " *" if v["significant"] else ""
        report += f"- {k}: r={v['r']}, p={v['p']}{sig}\n"

    agree_sig = sum(1 for v in agree_corr.values() if v["significant"])
    oai_sig = sum(1 for v in oai_corr.values() if v["significant"])

    report += f"""
## 5. Production recommendation rubric

| Criterion | Weight | Groq | OpenAI |
|-----------|--------|------|--------|
| Schema completeness | High | Poor ({groq['relevant_null_sentiment']} null sentiments) | Moderate ({oai['relevant_null_category']} null categories) |
| Sentiment plausibility | High | Good (~{groq['positive_pct_of_relevant']}% positive) | Poor ({oai['positive_pct_of_relevant']}% positive) |
| Gold 3-in-1 accuracy | High | {g_gold.get('strict_3in1_acc', 'TBD')} | {o_gold.get('strict_3in1_acc', 'TBD')} |
| FX correlation stability | Medium | Not significant | {oai_sig} significant pairs (suspect) |
| Agreement-only FX signal | Medium | — | {agree_sig} significant pairs |

## 6. Recommendation

**Do not switch production to GPT-4o-mini based on FX correlations alone.** OpenAI significance ({oai_sig} pairs) likely reflects positive-label inflation ({buckets['neutral_to_positive']} Neutral→Positive flips), not a truer economic signal.

**Short-term production path:**
1. **Fix Groq** — re-run retry in `EF-02/notebooks/04_classifier.ipynb` Section 5 to clear {groq['relevant_null_sentiment']} null sentiments, then re-consolidate.
2. **Keep Groq as production classifier** unless gold eval shows OpenAI clearly wins strict 3-in-1 accuracy AND manual review favours its labels.
3. **Report framing** — present OpenAI run as sensitivity analysis; note that agreement-only consolidation {'still shows significant FX correlations' if agree_sig else 'removes significant FX correlations'}, indicating {'some shared signal' if agree_sig else 'GPT-specific label noise drove significance'}.

Fill `your_*` columns in `disagreement_review_sample.csv` and re-run the scoring cell in `04_label_audit.ipynb` to refine this recommendation with human agreement rates.
"""
    path = AUDIT / "AUDIT_REPORT.md"
    path.write_text(report, encoding="utf-8")
    print(f"Wrote {path}")


def main():
    groq = pd.read_csv(GROQ_LABEL)
    oai = pd.read_csv(OAI_LABEL)
    merged = _merge_labels(groq, oai)
    bucket_counts, buckets = _disagreement_buckets(merged)

    metrics = {
        "groq": _quality_scorecard(groq, "Groq"),
        "openai": _quality_scorecard(oai, "OpenAI"),
        "disagreement_counts": bucket_counts,
        "null_sentiment_impact": _monthly_sentiment_impact(groq).to_dict(orient="records"),
    }
    (AUDIT / "quality_metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    print("Wrote quality_metrics.json")

    export_manual_review(merged, buckets)

    agree_viz = agreement_only_consolidation(groq, oai)
    correlations = {
        "groq": _top_correlations(pd.read_csv(GROQ_VIZ)),
        "openai": _top_correlations(pd.read_csv(OAI_VIZ)),
        "agreement_only": _top_correlations(agree_viz),
    }
    (AUDIT / "correlation_comparison.json").write_text(json.dumps(correlations, indent=2), encoding="utf-8")

    print("\nRunning gold-set eval (both providers, 504 rows)...")
    gold = run_gold_eval()

    write_audit_report(metrics, gold, correlations)

    # Worked examples for notebook
    examples = {}
    for name, bdf in buckets.items():
        if len(bdf) and name in ("negative_to_positive", "neutral_to_positive", "groq_relevant_only"):
            examples[name] = bdf[["headline", "category_groq", "sentiment_groq", "category_oai", "sentiment_oai"]].head(5).to_dict(orient="records")
    (AUDIT / "worked_examples.json").write_text(json.dumps(examples, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
