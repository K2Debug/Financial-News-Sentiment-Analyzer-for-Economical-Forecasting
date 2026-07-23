"""Full classification + consolidation pipeline using Groq gpt-oss-20b."""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from groq import Groq
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

MODEL = "openai/gpt-oss-20b"
BATCH_SIZE = 10
SLEEP_SEC = 1.5
CHECKPOINT = PROCESSED / "classification_checkpoint.json"
MAX_RETRY_PASSES = 3
MAX_API_ATTEMPTS = 12

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


def parse_rate_limit_wait(exc: Exception) -> float | None:
    msg = str(exc)
    m = re.search(r"try again in (\d+)m([\d.]+)s", msg, re.I)
    if m:
        return int(m.group(1)) * 60 + float(m.group(2))
    m = re.search(r"try again in ([\d.]+)s", msg, re.I)
    if m:
        return float(m.group(1))
    return None


def load_checkpoint() -> dict[int, dict]:
    if not CHECKPOINT.exists():
        return {}
    data = json.loads(CHECKPOINT.read_text(encoding="utf-8"))
    return {int(k): v for k, v in data.get("results", {}).items()}


def save_checkpoint(results: dict[int, dict]) -> None:
    CHECKPOINT.parent.mkdir(parents=True, exist_ok=True)
    CHECKPOINT.write_text(
        json.dumps({"results": {str(k): v for k, v in results.items()}}, indent=2),
        encoding="utf-8",
    )


def classify_batch(client, batch, batch_num, total_batches):
    prompt = build_prompt(batch)
    raw = ""
    attempt = 0
    while attempt < MAX_API_ATTEMPTS:
        attempt += 1
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
                raise ValueError(f"expected list, got {type(parsed)}")
            if len(parsed) != len(batch):
                raise ValueError(f"got {len(parsed)} for {len(batch)}")
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
        except (json.JSONDecodeError, ValueError) as e:
            print(f"  Batch {batch_num}/{total_batches} attempt {attempt}: {e}", flush=True)
            time.sleep(2)
        except Exception as e:
            wait = parse_rate_limit_wait(e)
            if wait is not None:
                wait = min(wait + 2, 900)
                print(
                    f"  Batch {batch_num}/{total_batches} attempt {attempt}: rate limit — waiting {wait:.0f}s",
                    flush=True,
                )
                time.sleep(wait)
            else:
                print(f"  Batch {batch_num}/{total_batches} attempt {attempt}: API error — {e}", flush=True)
                time.sleep(5)
    print(f"  Batch {batch_num}/{total_batches} — FAILED after {MAX_API_ATTEMPTS} attempts", flush=True)
    return [{"id": item["id"], "relevant": None, "category": None, "sentiment": None} for item in batch]


def needs_retry(df: pd.DataFrame) -> pd.Index:
    rel = df["relevant"] == True
    bad_sent = ~df["sentiment"].isin(VALID_SENTIMENTS)
    bad_cat = ~df["category"].isin(VALID_CATEGORIES)
    return df[(rel & (bad_sent | bad_cat)) | df["relevant"].isna()].index


def run_batches(client, rows, label="Classifying", checkpoint: dict[int, dict] | None = None):
    checkpoint = checkpoint or {}
    pending = [r for r in rows if r["id"] not in checkpoint or checkpoint[r["id"]].get("relevant") is None]
    if len(pending) < len(rows):
        print(f"{label}: resuming — {len(checkpoint)} done, {len(pending)} remaining", flush=True)
    batches = [pending[i : i + BATCH_SIZE] for i in range(0, len(pending), BATCH_SIZE)]
    total = len(batches)
    if total == 0:
        print(f"{label}: nothing to do", flush=True)
        return list(checkpoint.values())
    print(f"{label}: {len(pending)} headlines in {total} batches (model={MODEL}, batch_size={BATCH_SIZE})", flush=True)
    for batch_num, batch in enumerate(batches, start=1):
        print(f"  Starting batch {batch_num}/{total}...", flush=True)
        for r in classify_batch(client, batch, batch_num, total):
            checkpoint[r["id"]] = r
        save_checkpoint(checkpoint)
        if batch_num < total:
            time.sleep(SLEEP_SEC)
        if batch_num % 25 == 0 or batch_num == total:
            done = len(checkpoint)
            print(f"  >> Progress: {done}/{len(rows)} headlines ({batch_num}/{total} batches)", flush=True)
    return list(checkpoint.values())


def run_classifier(client, force: bool = False, resume: bool = True):
    if LABEL_OUT.exists() and not force and not resume:
        print(f"Skipping classifier — {LABEL_OUT} exists (use --force to rerun)")
        return pd.read_csv(LABEL_OUT)

    if force and CHECKPOINT.exists():
        CHECKPOINT.unlink()
        print("Cleared checkpoint (--force)", flush=True)

    checkpoint = {} if force else (load_checkpoint() if resume else {})

    df = pd.read_csv(CLEAN_IN, engine="python", on_bad_lines="warn").reset_index(drop=True)
    df["id"] = df.index
    rows = df[["id", "headline"]].to_dict("records")
    all_results = run_batches(client, rows, label="Classifying", checkpoint=checkpoint)

    df_out = df.merge(pd.DataFrame(all_results), on="id", how="left").drop(columns=["id"])

    for pass_num in range(1, MAX_RETRY_PASSES + 1):
        idx = needs_retry(df_out)
        if len(idx) == 0:
            break
        retry_rows = [{"id": int(i), "headline": df_out.at[i, "headline"]} for i in idx]
        print(f"\nRetry pass {pass_num}: {len(retry_rows)} incomplete rows", flush=True)
        retry_results = run_batches(client, retry_rows, label=f"Retry pass {pass_num}", checkpoint={})
        by_id = {r["id"]: r for r in retry_results}
        fixed = 0
        for i in idx:
            r = by_id.get(int(i))
            if not r:
                continue
            for col in ["relevant", "category", "sentiment"]:
                if r.get(col) is not None:
                    df_out.at[i, col] = r[col]
            if df_out.at[i, "relevant"] is True and df_out.at[i, "sentiment"] in VALID_SENTIMENTS:
                fixed += 1
        remaining = len(needs_retry(df_out))
        print(f"Retry pass {pass_num}: patched {fixed}, remaining {remaining}", flush=True)
        if remaining == 0:
            break

    df_out.to_csv(LABEL_OUT, index=False)
    if CHECKPOINT.exists():
        CHECKPOINT.unlink()
    rel = df_out[df_out["relevant"] == True]
    bad = (~rel["sentiment"].isin(VALID_SENTIMENTS)).sum()
    print(f"\nSaved {LABEL_OUT}", flush=True)
    print(f"  Relevant: {len(rel)}/{len(df_out)} ({len(rel)/len(df_out)*100:.1f}%)", flush=True)
    print(f"  Relevant + bad sentiment: {bad}", flush=True)
    print(f"  Sentiment dist: {rel['sentiment'].value_counts(dropna=False).to_dict()}", flush=True)
    return df_out


def run_consolidation(force: bool = False):
    if VIZ_OUT.exists() and not force:
        print(f"Skipping consolidation — {VIZ_OUT} exists")
        return pd.read_csv(VIZ_OUT)

    df_hdl = pd.read_csv(LABEL_OUT)

    df_exc = pd.read_csv(EF02 / "data" / "raw" / "usd_tzs_2022_2024.csv")
    df_exc["Price"] = pd.to_numeric(
        df_exc["Price"].astype(str).str.replace(",", "", regex=False), errors="coerce"
    )
    df_exc["Date"] = pd.to_datetime(df_exc["Date"], format="%m/%d/%Y")
    fx = df_exc.set_index("Date").resample("ME")["Price"].mean().reset_index()
    fx["YearMonth"] = fx["Date"].dt.strftime("%Y-%m")
    fx["Rate_Change_%"] = (fx["Price"].pct_change(fill_method=None) * 100).fillna(0)
    fx = fx[["YearMonth", "Price", "Rate_Change_%"]].rename(columns={"Price": "USD/TZS_Rate"})

    df_cpi = pd.read_csv(EF02 / "data" / "raw" / "tanzania_cpi_2022_2024.csv")
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
    merged = merged.rename(columns={
        "category": "Top_Category", "Negative": "Negative %", "Neutral": "Neutral %",
        "Positive": "Positive %", "Avg_sentiment": "Dominant_Sentiment", "inflation_rate_%": "Inflation %",
    })
    merged.to_csv(VIZ_OUT, index=False)
    print(f"Saved {VIZ_OUT} — {len(merged)} months ({merged['YearMonth'].min()} to {merged['YearMonth'].max()})", flush=True)
    return merged


def print_correlations(viz: pd.DataFrame, label: str):
    viz = viz.copy()
    viz["Net_Sentiment"] = viz["Positive %"] - viz["Negative %"]
    print(f"\n=== {label} ===", flush=True)
    for s, e in [
        ("Negative %", "USD/TZS_Rate"),
        ("Net_Sentiment", "USD/TZS_Rate"),
        ("Positive %", "USD/TZS_Rate"),
        ("Net_Sentiment", "Inflation %"),
    ]:
        r, p = stats.pearsonr(viz[s], viz[e])
        sig = " *" if p < 0.05 else ""
        print(f"  {s} vs {e}: r={r:.3f}, p={p:.4f}{sig}", flush=True)


def run_comparison():
    gpt_viz = pd.read_csv(VIZ_OUT)
    gpt_hdl = pd.read_csv(LABEL_OUT)
    print_correlations(gpt_viz, "GPT-OSS-20b monthly correlations")

    if GROQ_VIZ.exists():
        print_correlations(pd.read_csv(GROQ_VIZ), "Groq Llama 8B (current production)")

    rel = gpt_hdl[gpt_hdl["relevant"] == True]
    print(f"\n=== GPT-OSS-20b summary ===", flush=True)
    print(f"  Total headlines : {len(gpt_hdl)}", flush=True)
    print(f"  Relevant        : {len(rel)} ({len(rel)/len(gpt_hdl)*100:.1f}%)", flush=True)
    print(f"  Avg Positive %  : {gpt_viz['Positive %'].mean():.1f}", flush=True)
    print(f"  Avg Negative %  : {gpt_viz['Negative %'].mean():.1f}", flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="Restart from scratch")
    parser.add_argument("--no-resume", action="store_true", help="Ignore checkpoint")
    args = parser.parse_args()

    load_dotenv(EF02 / ".env")
    if not os.getenv("GROQ_API_KEY"):
        sys.exit("GROQ_API_KEY not found in EF-02/.env")

    client = Groq(api_key=os.getenv("GROQ_API_KEY"))
    print(f"=== GPT-OSS-20b pipeline ===\n", flush=True)

    run_classifier(client, force=args.force, resume=not args.no_resume)
    run_consolidation(force=args.force)
    run_comparison()
    print("\nDone.", flush=True)


if __name__ == "__main__":
    main()
