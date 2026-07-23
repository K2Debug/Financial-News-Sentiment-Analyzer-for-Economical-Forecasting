"""Run OpenAI classifier → consolidation → comparison (non-notebook)."""
from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from openai import OpenAI
from scipy import stats

ROOT = Path(__file__).resolve().parents[1]
EF02 = ROOT.parent / "EF-02"
PROCESSED = ROOT / "data" / "processed"
PROCESSED.mkdir(parents=True, exist_ok=True)

CLEAN_IN = EF02 / "data" / "processed" / "tz_headlines_clean.csv"
LABEL_OUT = PROCESSED / "tz_headlines_labelled.csv"
VIZ_OUT = PROCESSED / "Visualization_Data.csv"
GROQ_LABEL = EF02 / "data" / "processed" / "tz_headlines_labelled.csv"
GROQ_VIZ = EF02 / "data" / "processed" / "Visualization_Data.csv"

MODEL = "gpt-4o-mini"
BATCH_SIZE = 25
SLEEP_SEC = 0.15

VALID_CATEGORIES = {
    "Forex", "Policy", "Banking", "Trade",
    "Agriculture", "Energy", "Transport", "Investment",
    "Markets", "Tourism", "Inflation",
}
VALID_SENTIMENTS = {"Positive", "Negative", "Neutral"}

SYSTEM_PROMPT = """You are a financial news classifier for Tanzania.
You return ONLY a valid JSON array. No preamble, no explanation, no markdown fences.
Every object in the array must be complete and the array must be properly closed with ]."""


def build_prompt(batch, include_reason=False):
    lines = "\n".join(f"{i+1}. {item['headline']}" for i, item in enumerate(batch))
    reason_field = ""
    if include_reason:
        reason_field = '\nAdd "reason": 4-6 words explaining your decision (debugging only).'
    return f"""You classify Tanzanian financial headlines. Output ONLY a valid JSON array.

Schema: [{{"pos":1,"relevant":true,"category":"Forex","sentiment":"Positive"}}, ...]{reason_field}

STEP 0 — RELEVANCE:
relevant true → Tanzania economy, finance, business, trade, banking, currency, energy, agriculture
relevant false → sports, crime, entertainment, foreign-only news, opinion/lifestyle; if false set category/sentiment null

STEP 1 — pick ONE category:
Forex(shilling,dollar,reserves) | Policy(BOT,IMF,budget,tax,debt,GDP,NBS,rates) | Banking(banks,loans,fintech,insurance) | Trade(imports,exports,tariffs,ports,AfCFTA) | Agriculture(crops,farming,food) | Energy(TANESCO,fuel,power) | Transport(SGR,rail,roads,logistics) | Investment(FDI,factories,PPP,crowdfunding) | Markets(DSE,CMSA,equity,bonds,turnover) | Tourism(hotels,arrivals) | Inflation(CPI,food/cement price spikes)

Disambiguation: DSE/CMSA→Markets | BOT rate/GDP→Policy | food/cement price spike→Inflation | hotels→Tourism

STEP 2 — SENTIMENT (economic outcome not tone):
Positive=growth,profit up,shilling firms,easing inflation,launches | Negative=decline,loss,miss target,weakening,rising inflation | Neutral=steady,guidelines,reviews,no clear direction
Falling inflation=Positive. Rising inflation=Negative.

Headlines:
{lines}"""


def classify_batch(client, batch, batch_num, total_batches, max_retries=3):
    prompt = build_prompt(batch)
    raw = ""
    for attempt in range(1, max_retries + 1):
        try:
            response = client.chat.completions.create(
                model=MODEL,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                temperature=0,
                max_tokens=2500,
            )
            raw = response.choices[0].message.content.strip()
            clean = re.sub(r"```(?:json)?|```", "", raw).strip()
            parsed = json.loads(clean)
            if not isinstance(parsed, list):
                raise ValueError(f"Expected list, got {type(parsed)}")
            if len(parsed) != len(batch):
                raise ValueError(f"Got {len(parsed)} results for {len(batch)} headlines")
            for i, result in enumerate(parsed):
                result["id"] = batch[i]["id"]
                result.pop("pos", None)
                if result.get("relevant") is True:
                    if result.get("category") not in VALID_CATEGORIES:
                        result["category"] = None
                    if result.get("sentiment") not in VALID_SENTIMENTS:
                        result["sentiment"] = None
            print(f"  Batch {batch_num}/{total_batches} — OK ({len(parsed)} results)", flush=True)
            return parsed
        except json.JSONDecodeError:
            tail = raw[-80:] if len(raw) > 80 else raw
            print(f"  Batch {batch_num} attempt {attempt}: JSON cut off. Ends: ...{repr(tail)}")
            time.sleep(2)
        except ValueError as e:
            print(f"  Batch {batch_num} attempt {attempt}: Validation error — {e}")
            time.sleep(2)
        except Exception as e:
            print(f"  Batch {batch_num} attempt {attempt}: API error — {e}")
            time.sleep(5)
    print(f"  Batch {batch_num}: FAILED after {max_retries} attempts.")
    return [{"id": item["id"], "relevant": None, "category": None, "sentiment": None} for item in batch]


def run_classifier(client):
    df = pd.read_csv(CLEAN_IN, engine="python", on_bad_lines="warn").reset_index(drop=True)
    df["id"] = df.index
    rows = df[["id", "headline"]].to_dict("records")
    batches = [rows[i : i + BATCH_SIZE] for i in range(0, len(rows), BATCH_SIZE)]
    total = len(batches)
    print(f"Classifying {len(df)} headlines in {total} batches (model={MODEL})")

    all_results = []
    for batch_num, batch in enumerate(batches, start=1):
        all_results.extend(classify_batch(client, batch, batch_num, total))
        if batch_num < total:
            time.sleep(SLEEP_SEC)

    df_out = df.merge(pd.DataFrame(all_results), on="id", how="left").drop(columns=["id"])
    n_failed = df_out["relevant"].isna().sum()
    if n_failed:
        print(f"Retrying {n_failed} failed rows...")
        failed = df_out[df_out["relevant"].isna()].copy()
        retry_rows = failed.reset_index().rename(columns={"index": "id"})[["id", "headline"]].to_dict("records")
        retry_batches = [retry_rows[i : i + 10] for i in range(0, len(retry_rows), 10)]
        retry_results = []
        for batch_num, batch in enumerate(retry_batches, start=1):
            retry_results.extend(classify_batch(client, batch, batch_num, len(retry_batches)))
            time.sleep(SLEEP_SEC)
        retry_df = pd.DataFrame(retry_results)
        df_out = df_out.reset_index().merge(retry_df, left_on="index", right_on="id", how="left", suffixes=("", "_retry"))
        for col in ["relevant", "category", "sentiment"]:
            df_out[col] = df_out[f"{col}_retry"].combine_first(df_out[col])
        df_out = df_out.drop(columns=[c for c in df_out.columns if c.endswith("_retry") or c in ("index", "id")])

    df_out.to_csv(LABEL_OUT, index=False)
    n_rel = int(df_out["relevant"].sum())
    print(f"Saved {LABEL_OUT} — relevant: {n_rel}/{len(df_out)} ({n_rel/len(df_out)*100:.1f}%)")
    return df_out


def run_consolidation():
    # Exchange rate
    df_exc = pd.read_csv(EF02 / "data" / "raw" / "usd_tzs_2022_2024.csv")
    df_exc["Price"] = df_exc["Price"].astype(str).str.replace(",", "", regex=False).str.strip()
    df_exc["Price"] = pd.to_numeric(df_exc["Price"], errors="coerce")
    df_exc["Date"] = pd.to_datetime(df_exc["Date"], format="%m/%d/%Y")
    df_exc_monthly = (
        df_exc.set_index("Date").resample("ME")["Price"].mean().reset_index()
    )
    df_exc_monthly["YearMonth"] = df_exc_monthly["Date"].dt.strftime("%Y-%m")
    df_exc_monthly["Rate_Change_%"] = df_exc_monthly["Price"].pct_change(fill_method=None) * 100
    df_exc_monthly = df_exc_monthly[["YearMonth", "Price", "Rate_Change_%"]].rename(
        columns={"Price": "USD/TZS_Rate"}
    )
    df_exc_monthly["Rate_Change_%"] = df_exc_monthly["Rate_Change_%"].fillna(0)

    # CPI
    df_cpi = pd.read_csv(EF02 / "data" / "raw" / "tanzania_cpi_2022_2024.csv")
    df_cpi["date"] = pd.to_datetime(df_cpi["date"], format="%Y-%m-%d")
    df_cpi_monthly = df_cpi.copy()
    df_cpi_monthly["YearMonth"] = df_cpi_monthly["date"].dt.strftime("%Y-%m")
    df_cpi_monthly = df_cpi_monthly.drop(columns=["date", "all_items_index"])
    df_cpi_monthly = df_cpi_monthly.rename(columns={"inflation_rate_pct": "inflation_rate_%"})

    # Headlines
    df_hdl = pd.read_csv(LABEL_OUT)
    df_hdl = df_hdl[df_hdl["relevant"] == True]
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
    df_merge.to_csv(VIZ_OUT, index=False)
    print(f"Saved {VIZ_OUT} — {len(df_merge)} months ({df_merge['YearMonth'].min()} to {df_merge['YearMonth'].max()})")
    return df_merge


def run_comparison():
    groq_hdl = pd.read_csv(GROQ_LABEL)
    groq_viz = pd.read_csv(GROQ_VIZ)
    oai_hdl = pd.read_csv(LABEL_OUT)
    oai_viz = pd.read_csv(VIZ_OUT)

    def summary(name, hdl, viz):
        rel = hdl[hdl["relevant"] == True]
        viz = viz.copy()
        viz["Net_Sentiment"] = viz["Positive %"] - viz["Negative %"]
        print(f"\n=== {name} ===")
        print(f"  Total headlines : {len(hdl)}")
        print(f"  Relevant        : {len(rel)} ({len(rel)/len(hdl)*100:.1f}%)")
        print(f"  Monthly rows    : {len(viz)} ({viz['YearMonth'].min()} to {viz['YearMonth'].max()})")
        print(f"  Avg Positive %  : {viz['Positive %'].mean():.1f}")
        print(f"  Avg Negative %  : {viz['Negative %'].mean():.1f}")
        print(f"  Top categories  : {dict(viz['Top_Category'].value_counts().head(3))}")
        for s, e in [("Negative %", "USD/TZS_Rate"), ("Net_Sentiment", "USD/TZS_Rate"), ("Net_Sentiment", "Inflation %")]:
            r, p = stats.pearsonr(viz[s], viz[e])
            sig = "*" if p < 0.05 else ""
            print(f"  {s} vs {e}: r={r:.3f}, p={p:.4f}{sig}")

    summary("Groq (llama-3.1-8b-instant)", groq_hdl, groq_viz)
    summary("OpenAI (gpt-4o-mini)", oai_hdl, oai_viz)

    merged = groq_hdl.merge(oai_hdl, on=["date", "headline", "url"], suffixes=("_groq", "_oai"))
    both_rel = merged[(merged["relevant_groq"] == True) & (merged["relevant_oai"] == True)]
    print(f"\n=== Label agreement ({len(merged)} matched rows) ===")
    print(f"  Relevance agreement : {(merged['relevant_groq'] == merged['relevant_oai']).mean()*100:.1f}%")
    print(f"  Sentiment agreement : {(both_rel['sentiment_groq'] == both_rel['sentiment_oai']).mean()*100:.1f}%")
    print(f"  Category agreement  : {(both_rel['category_groq'] == both_rel['category_oai']).mean()*100:.1f}%")


def main():
    load_dotenv(EF02 / ".env")
    if not os.getenv("OPENAI_API_KEY"):
        sys.exit("OPENAI_API_KEY not found in EF-02/.env")
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    if not LABEL_OUT.exists():
        run_classifier(client)
    else:
        print(f"Skipping classifier — {LABEL_OUT} already exists")

    if not VIZ_OUT.exists():
        run_consolidation()
    else:
        print(f"Skipping consolidation — {VIZ_OUT} already exists")

    run_comparison()


if __name__ == "__main__":
    main()
