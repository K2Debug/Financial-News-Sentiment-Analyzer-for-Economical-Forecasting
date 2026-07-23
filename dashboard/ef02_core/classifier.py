"""OpenAI batch classifier with checkpoint support."""
from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Callable

import pandas as pd
from openai import OpenAI

from ef02_core.constants import VALID_CATEGORIES, VALID_SENTIMENTS
from ef02_core.io import atomic_write_json
from ef02_core.prompts import ClassifierSettings, build_user_prompt, notebook_defaults

ProgressCallback = Callable[[dict], None]


def classify_batch(
    client: OpenAI,
    batch: list[dict],
    batch_num: int,
    total_batches: int,
    settings: ClassifierSettings | None = None,
    max_retries: int = 3,
) -> list[dict]:
    cfg = settings or notebook_defaults()
    prompt = build_user_prompt(batch, cfg)
    raw = ""
    for attempt in range(1, max_retries + 1):
        try:
            response = client.chat.completions.create(
                model=cfg.model,
                messages=[
                    {"role": "system", "content": cfg.system_prompt},
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
            return parsed
        except json.JSONDecodeError:
            time.sleep(2)
        except ValueError:
            time.sleep(2)
        except Exception:
            time.sleep(5)
    return [{"id": item["id"], "relevant": None, "category": None, "sentiment": None} for item in batch]


def _save_checkpoint(path: Path, results: dict[int, dict], completed_batches: int) -> None:
    atomic_write_json(
        path,
        {"completed_batches": completed_batches, "results": {str(k): v for k, v in results.items()}},
    )


def run_classifier(
    client: OpenAI,
    clean_path: Path,
    label_out: Path,
    checkpoint_path: Path | None = None,
    on_progress: ProgressCallback | None = None,
    settings: ClassifierSettings | None = None,
) -> pd.DataFrame:
    cfg = settings or notebook_defaults()
    df = pd.read_csv(clean_path, engine="python", on_bad_lines="warn").reset_index(drop=True)
    df["id"] = df.index
    rows = df[["id", "headline"]].to_dict("records")
    batches = [rows[i : i + cfg.batch_size] for i in range(0, len(rows), cfg.batch_size)]
    total = len(batches)

    stored: dict[int, dict] = {}
    start_batch = 0
    if checkpoint_path and checkpoint_path.exists():
        ck = json.loads(checkpoint_path.read_text(encoding="utf-8"))
        start_batch = ck.get("completed_batches", 0)
        stored = {int(k): v for k, v in ck.get("results", {}).items()}

    if on_progress:
        on_progress({
            "phase": "classify",
            "batch": start_batch,
            "total_batches": total,
            "headlines_done": min(start_batch * cfg.batch_size, len(df)),
            "headlines_total": len(df),
            "message": f"Resuming from batch {start_batch + 1}" if start_batch else "Starting classification",
        })

    for batch_num, batch in enumerate(batches, start=1):
        if batch_num <= start_batch:
            continue
        results = classify_batch(client, batch, batch_num, total, settings=cfg)
        for item in results:
            stored[item["id"]] = {
                "relevant": item.get("relevant"),
                "category": item.get("category"),
                "sentiment": item.get("sentiment"),
            }
        if checkpoint_path:
            _save_checkpoint(checkpoint_path, stored, batch_num)
        if on_progress:
            on_progress({
                "phase": "classify",
                "batch": batch_num,
                "total_batches": total,
                "headlines_done": min(batch_num * cfg.batch_size, len(df)),
                "headlines_total": len(df),
                "message": f"Batch {batch_num}/{total} complete",
            })
        if batch_num < total:
            time.sleep(cfg.sleep_sec)

    all_results = [
        {
            "relevant": stored.get(i, {}).get("relevant"),
            "category": stored.get(i, {}).get("category"),
            "sentiment": stored.get(i, {}).get("sentiment"),
        }
        for i in range(len(df))
    ]
    df_out = df.drop(columns=["id"]).reset_index(drop=True)
    results_df = pd.DataFrame(all_results)
    df_out = pd.concat([df_out, results_df], axis=1)

    n_failed = int(df_out["relevant"].isna().sum())
    if n_failed:
        if on_progress:
            on_progress({
                "phase": "classify_retry",
                "headlines_done": len(df) - n_failed,
                "headlines_total": len(df),
                "message": f"Retrying {n_failed} failed rows",
            })
        failed = df_out[df_out["relevant"].isna()].copy()
        retry_rows = failed.reset_index().rename(columns={"index": "id"})[["id", "headline"]].to_dict("records")
        retry_batches = [
            retry_rows[i : i + cfg.retry_batch_size] for i in range(0, len(retry_rows), cfg.retry_batch_size)
        ]
        retry_results: list[dict] = []
        for rb_num, rb in enumerate(retry_batches, start=1):
            retry_results.extend(classify_batch(client, rb, rb_num, len(retry_batches), settings=cfg))
            time.sleep(cfg.sleep_sec)
        retry_df = pd.DataFrame(retry_results)
        df_out = df_out.reset_index().merge(retry_df, left_on="index", right_on="id", how="left", suffixes=("", "_retry"))
        for col in ["relevant", "category", "sentiment"]:
            df_out[col] = df_out[f"{col}_retry"].combine_first(df_out[col])
        df_out = df_out.drop(columns=[c for c in df_out.columns if c.endswith("_retry") or c in ("index", "id")])

    label_out.parent.mkdir(parents=True, exist_ok=True)
    df_out.to_csv(label_out, index=False)
    return df_out
