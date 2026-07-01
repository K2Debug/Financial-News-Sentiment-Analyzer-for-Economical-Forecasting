"""Retry Groq classification for relevant rows missing a valid sentiment.

Fixes the gap where the production retry only targeted `relevant is NaN`,
leaving relevant==True rows with null/invalid sentiment untouched. Then
re-consolidates the Groq monthly dataset and compares correlations.
"""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from groq import Groq
from scipy import stats

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

client = Groq(api_key=os.getenv("GROQ_API_KEY"))
MODEL = "llama-3.1-8b-instant"
BATCH_SIZE = 10
SLEEP_SEC = 1.5
MAX_PASSES = 3

LABELLED = ROOT / "data" / "processed" / "tz_headlines_labelled.csv"
VIZ = ROOT / "data" / "processed" / "Visualization_Data.csv"
RAW = ROOT / "data" / "raw"

VALID_CATEGORIES = {
    "Forex", "Policy", "Banking", "Trade",
    "Agriculture", "Energy", "Transport", "Investment",
    "Markets", "Tourism", "Inflation",
}
VALID_SENTIMENTS = {"Positive", "Negative", "Neutral"}

SYSTEM_PROMPT = """You are a financial news classifier for Tanzania.
You return ONLY a valid JSON array. No preamble, no explanation, no markdown fences.
Every object in the array must be complete and the array must be properly closed with ]."""


def build_prompt(batch):
    lines = "\n".join(f"{i+1}. {item['headline']}" for i, item in enumerate(batch))
    return f"""You classify Tanzanian financial headlines. Output ONLY a valid JSON array.

Schema: [{{"pos":1,"relevant":true,"category":"Forex","sentiment":"Positive"}}, ...]

STEP 0 — RELEVANCE:
relevant true → Tanzania economy, finance, business, trade, banking, currency, energy, agriculture
relevant false → sports, crime, entertainment, foreign-only news, opinion/lifestyle; if false set category/sentiment null

STEP 1 — pick ONE category:
Forex(shilling,dollar,reserves) | Policy(BOT,IMF,budget,tax,debt,GDP,NBS,rates) | Banking(banks,loans,fintech,insurance) | Trade(imports,exports,tariffs,ports,AfCFTA) | Agriculture(crops,farming,food) | Energy(TANESCO,fuel,power) | Transport(SGR,rail,roads,logistics) | Investment(FDI,factories,PPP,crowdfunding) | Markets(DSE,CMSA,equity,bonds,turnover) | Tourism(hotels,arrivals) | Inflation(CPI,food/cement price spikes)

Disambiguation: DSE/CMSA→Markets | BOT rate/GDP→Policy | food/cement price spike→Inflation | hotels→Tourism

STEP 2 — SENTIMENT (economic outcome not tone). EVERY relevant headline MUST get exactly one:
Positive=growth,profit up,shilling firms,easing inflation,launches | Negative=decline,loss,miss target,weakening,rising inflation | Neutral=steady,guidelines,reviews,no clear direction
Falling inflation=Positive. Rising inflation=Negative. Never leave sentiment null for a relevant headline.

Headlines:
{lines}"""


def classify_batch(batch, batch_num, total, max_retries=3):
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
            if not isinstance(parsed, list) or len(parsed) != len(batch):
                raise ValueError(f"got {len(parsed)} for {len(batch)}")
            for i, result in enumerate(parsed):
                result["id"] = batch[i]["id"]
                result.pop("pos", None)
                if result.get("relevant") is True:
                    if result.get("category") not in VALID_CATEGORIES:
                        result["category"] = None
                    if result.get("sentiment") not in VALID_SENTIMENTS:
                        result["sentiment"] = None
            print(f"  batch {batch_num}/{total} ok", flush=True)
            return parsed
        except (json.JSONDecodeError, ValueError) as e:
            print(f"  batch {batch_num} attempt {attempt}: {e}")
            time.sleep(2)
        except Exception as e:
            print(f"  batch {batch_num} attempt {attempt}: API {e}")
            time.sleep(5)
    return [{"id": item["id"], "relevant": None, "category": None, "sentiment": None} for item in batch]


def needs_retry(df):
    rel = df["relevant"] == True
    bad_sent = ~df["sentiment"].isin(VALID_SENTIMENTS)
    return df[(rel & bad_sent) | df["relevant"].isna()].index


def retry_pass(df, pass_num):
    idx = needs_retry(df)
    if len(idx) == 0:
        return df, 0
    print(f"\nPass {pass_num}: {len(idx)} rows to retry")
    rows = [{"id": int(i), "headline": df.at[i, "headline"]} for i in idx]
    batches = [rows[i : i + BATCH_SIZE] for i in range(0, len(rows), BATCH_SIZE)]
    results = {}
    for bn, batch in enumerate(batches, start=1):
        for r in classify_batch(batch, bn, len(batches)):
            results[r["id"]] = r
        if bn < len(batches):
            time.sleep(SLEEP_SEC)
    fixed = 0
    for i in idx:
        r = results.get(int(i))
        if not r:
            continue
        if r.get("relevant") is not None:
            df.at[i, "relevant"] = r["relevant"]
        if r.get("category") is not None:
            df.at[i, "category"] = r["category"]
        if r.get("sentiment") is not None:
            df.at[i, "sentiment"] = r["sentiment"]
            fixed += 1
    return df, fixed


def consolidate(df_hdl):
    df_exc = pd.read_csv(RAW / "usd_tzs_2022_2024.csv")
    df_exc["Price"] = pd.to_numeric(
        df_exc["Price"].astype(str).str.replace(",", "", regex=False), errors="coerce"
    )
    df_exc["Date"] = pd.to_datetime(df_exc["Date"], format="%m/%d/%Y")
    fx = df_exc.set_index("Date").resample("ME")["Price"].mean().reset_index()
    fx["YearMonth"] = fx["Date"].dt.strftime("%Y-%m")
    fx["Rate_Change_%"] = (fx["Price"].pct_change(fill_method=None) * 100).fillna(0)
    fx = fx[["YearMonth", "Price", "Rate_Change_%"]].rename(columns={"Price": "USD/TZS_Rate"})

    df_cpi = pd.read_csv(RAW / "tanzania_cpi_2022_2024.csv")
    df_cpi["date"] = pd.to_datetime(df_cpi["date"], format="%Y-%m-%d")
    df_cpi["YearMonth"] = df_cpi["date"].dt.strftime("%Y-%m")
    cpi = df_cpi.drop(columns=["date", "all_items_index"]).rename(
        columns={"inflation_rate_pct": "inflation_rate_%"}
    )

    rel = df_hdl[df_hdl["relevant"] == True].copy()
    rel["date"] = pd.to_datetime(rel["date"], format="%Y-%m-%d", errors="coerce")
    rel["YearMonth"] = rel["date"].dt.strftime("%Y-%m")
    rel["category"] = rel["category"].astype("category")
    rel["sentiment"] = rel["sentiment"].astype("category")

    counts = rel.groupby("YearMonth", observed=True).size().reset_index(name="num_headlines")
    topcat = rel.groupby(["YearMonth", "category"], observed=True).size().reset_index(name="c")
    topcat["category %"] = topcat.groupby("YearMonth")["c"].transform(lambda x: x / x.sum() * 100).round(2)
    topcat = (
        topcat.sort_values(["YearMonth", "category %"], ascending=[True, False])
        .groupby("YearMonth").first().reset_index().drop(columns=["c"])
    )
    sent = rel.groupby(["YearMonth", "sentiment"], observed=True).size().unstack(fill_value=0).reset_index()
    scols = [c for c in sent.columns if c != "YearMonth"]
    sent[scols] = (sent[scols].div(sent[scols].sum(axis=1), axis=0) * 100).round(2)
    sent["Avg_sentiment"] = sent[scols].idxmax(axis=1)

    monthly = counts.merge(topcat, on="YearMonth").merge(sent, on="YearMonth")
    merged = monthly.merge(cpi, on="YearMonth", how="inner").merge(fx, on="YearMonth", how="inner")
    return merged.rename(columns={
        "category": "Top_Category", "Negative": "Negative %", "Neutral": "Neutral %",
        "Positive": "Positive %", "Avg_sentiment": "Dominant_Sentiment", "inflation_rate_%": "Inflation %",
    })


def correlations(viz, label):
    viz = viz.copy()
    viz["Net_Sentiment"] = viz["Positive %"] - viz["Negative %"]
    pairs = [
        ("Negative %", "USD/TZS_Rate"),
        ("Net_Sentiment", "USD/TZS_Rate"),
        ("Positive %", "USD/TZS_Rate"),
        ("Net_Sentiment", "Inflation %"),
    ]
    print(f"\n=== {label} ===")
    out = {}
    for s, e in pairs:
        r, p = stats.pearsonr(viz[s], viz[e])
        sig = " *" if p < 0.05 else ""
        print(f"  {s} vs {e}: r={r:.3f}, p={p:.4f}{sig}")
        out[f"{s} vs {e}"] = (round(float(r), 3), round(float(p), 4))
    return out


def main():
    df = pd.read_csv(LABELLED)
    rel = df[df["relevant"] == True]
    print(f"Loaded {len(df)} rows, relevant {len(rel)}")
    print(f"Relevant + invalid/null sentiment BEFORE: {(~rel['sentiment'].isin(VALID_SENTIMENTS)).sum()}")

    before_viz = pd.read_csv(VIZ)
    before = correlations(before_viz, "BEFORE retry (current Groq viz)")

    for p in range(1, MAX_PASSES + 1):
        df, fixed = retry_pass(df, p)
        remaining = len(needs_retry(df))
        print(f"Pass {p}: fixed {fixed}, remaining {remaining}")
        if remaining == 0:
            break

    df.to_csv(LABELLED, index=False)
    rel2 = df[df["relevant"] == True]
    print(f"\nSaved patched {LABELLED}")
    print(f"Relevant + invalid/null sentiment AFTER: {(~rel2['sentiment'].isin(VALID_SENTIMENTS)).sum()}")
    print("Sentiment dist AFTER:", rel2["sentiment"].value_counts(dropna=False).to_dict())

    after_viz = consolidate(df)
    after_viz.to_csv(VIZ, index=False)
    print(f"Re-consolidated -> {VIZ} ({len(after_viz)} months)")
    after = correlations(after_viz, "AFTER retry (regenerated Groq viz)")

    print("\n=== DELTA (r, p) ===")
    for k in before:
        rb, pb = before[k]
        ra, pa = after[k]
        print(f"  {k}: r {rb}->{ra}, p {pb}->{pa}")


if __name__ == "__main__":
    main()
