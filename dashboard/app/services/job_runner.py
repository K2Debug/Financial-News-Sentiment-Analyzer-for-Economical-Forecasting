"""Background pipeline execution — split phase runners."""
from __future__ import annotations

import os
import traceback
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from openai import OpenAI

from app.config import ROOT
from app.services import persistence
from app.services.job_store import JobState
from ef02_core.classifier import run_classifier
from ef02_core.consolidation import run_consolidation
from ef02_core.correlations import build_analysis_summary, compute_correlations
from ef02_core.prompts import notebook_defaults

PROJECT_ENV = ROOT.parent / ".env"
DASHBOARD_ENV = ROOT / ".env"
RESEARCH_ENV = ROOT.parent / "research" / ".env"


def _resolve_api_key(job: JobState) -> str:
    if job.api_key_override:
        return job.api_key_override
    session_key = persistence.load_session_api_key(job.job_id)
    if session_key:
        return session_key
    load_dotenv(PROJECT_ENV)
    load_dotenv(DASHBOARD_ENV)
    load_dotenv(RESEARCH_ENV)
    key = os.getenv("OPENAI_API_KEY", "")
    if not key:
        raise RuntimeError(
            "OPENAI_API_KEY not set. Add it to ef02/.env (or dashboard/.env), or paste a key when resuming."
        )
    return key


def _job_paths(job: JobState) -> dict[str, Path]:
    d = job.dir()
    return {
        "headlines": d / "headlines.csv",
        "cpi": d / "cpi.csv",
        "fx": d / "fx.csv",
        "clean": d / "headlines_clean.csv",
        "labels": d / "tz_headlines_labelled.csv",
        "viz": d / "Visualization_Data.csv",
        "checkpoint": d / "classification_checkpoint.json",
        "corr": d / "correlations.json",
        "analysis": d / "analysis_summary.json",
    }


def run_classify_phase(job: JobState) -> None:
    if not persistence.acquire_worker_lock(job.job_id):
        return
    paths = _job_paths(job)
    try:
        if paths["labels"].exists():
            job.push_event({
                "status": "completed",
                "phase": "classify",
                "message": "Using cached labelled headlines",
            })
            persistence.update_manifest(job.job_id, {"phases": {"classify": "done"}})
            return

        if not paths["clean"].exists():
            raise RuntimeError("Headlines data not uploaded. Complete Data Import first.")

        n_rows = len(pd.read_csv(paths["clean"]))
        job.push_event({
            "status": "running",
            "phase": "classify",
            "message": "Classifying headlines...",
            "headlines_total": n_rows,
        })

        client = OpenAI(api_key=_resolve_api_key(job))
        settings = persistence.load_settings(job.job_id)

        def on_progress(event: dict) -> None:
            job.push_event({"status": "running", **event})

        run_classifier(
            client,
            paths["clean"],
            paths["labels"],
            checkpoint_path=paths["checkpoint"],
            on_progress=on_progress,
            settings=settings,
        )
        job.push_event({
            "status": "completed",
            "phase": "classify",
            "message": f"Classification complete — {n_rows} headlines labelled",
        })
        persistence.update_manifest(job.job_id, {
            "phases": {"classify": "done"},
            "outputs": {"labelled": "tz_headlines_labelled.csv"},
        })
    except Exception as exc:
        job.error = str(exc)
        job.push_event({
            "status": "failed",
            "phase": "error",
            "message": str(exc),
            "error": str(exc),
            "trace": traceback.format_exc(),
        })
    finally:
        persistence.release_worker_lock(job.job_id)
        persistence.sync_job_from_disk(job.job_id)


def run_consolidate_phase(job: JobState) -> None:
    if not persistence.acquire_worker_lock(job.job_id):
        return
    paths = _job_paths(job)
    try:
        if not paths["labels"].exists():
            raise RuntimeError("Labelled headlines required. Run Classify or upload a labelled CSV.")

        for name, p in [("CPI", paths["cpi"]), ("USD/TZS", paths["fx"])]:
            if not p.exists():
                raise RuntimeError(f"{name} data not uploaded. Complete Data Import first.")

        if paths["viz"].exists() and paths["corr"].exists():
            job.push_event({
                "status": "completed",
                "phase": "consolidate",
                "message": "Using cached visualization data",
            })
            return

        job.push_event({"status": "running", "phase": "consolidate", "message": "Merging monthly data..."})

        viz_df = run_consolidation(paths["labels"], paths["cpi"], paths["fx"], paths["viz"])
        correlations = compute_correlations(viz_df)
        persistence.atomic_write_json(paths["corr"], correlations)
        summary = build_analysis_summary(correlations, viz_df)
        persistence.atomic_write_json(paths["analysis"], summary)

        job.push_event({
            "status": "completed",
            "phase": "done",
            "message": f"Consolidation complete — {len(viz_df)} months",
        })
        persistence.update_manifest(job.job_id, {
            "phases": {"consolidate": "done", "analysis": "done"},
            "outputs": {
                "visualization": "Visualization_Data.csv",
                "correlations": "correlations.json",
            },
        })
    except Exception as exc:
        job.error = str(exc)
        job.push_event({
            "status": "failed",
            "phase": "error",
            "message": str(exc),
            "error": str(exc),
            "trace": traceback.format_exc(),
        })
    finally:
        persistence.release_worker_lock(job.job_id)
        persistence.sync_job_from_disk(job.job_id)


def run_job(job: JobState) -> None:
    """Full pipeline — classify then consolidate."""
    run_classify_phase(job)
    from app.services.job_store import job_store

    refreshed = job_store.get(job.job_id)
    if refreshed and refreshed.status != "failed":
        run_consolidate_phase(refreshed)
