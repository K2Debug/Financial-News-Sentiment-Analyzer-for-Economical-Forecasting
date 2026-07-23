"""FastAPI routes for upload, jobs, phases, and results."""
from __future__ import annotations

import asyncio
import json
from io import StringIO
from pathlib import Path

import pandas as pd
from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from app.config import RUNS_DIR
from app.services import persistence
from app.services.job_runner import run_classify_phase, run_consolidate_phase, run_job
from app.services.job_store import job_store
from ef02_core.cleaning import (
    clean_headlines,
    merge_headline_csvs,
    normalize_labelled_df,
    preview_uploads,
    validate_cpi_df,
    validate_fx_df,
    validate_headlines_df,
    validate_labelled_df,
)
from ef02_core.correlations import build_analysis_summary, compute_correlations
from ef02_core.prompts import ClassifierSettings, notebook_defaults

router = APIRouter(prefix="/api")

_RESUMABLE = frozenset({"created", "queued", "interrupted", "failed"})


class SettingsUpdate(BaseModel):
    model: str | None = None
    batch_size: int | None = None
    retry_batch_size: int | None = None
    sleep_sec: float | None = None
    system_prompt: str | None = None
    user_prompt_template: str | None = None
    api_key: str | None = None


class JobRename(BaseModel):
    name: str


def _has_api_key(job_id: str) -> bool:
    job = job_store.get(job_id)
    if job and job.api_key_override:
        return True
    return bool(persistence.load_session_api_key(job_id))


def _enqueue(job_id: str, background_tasks: BackgroundTasks, fn, api_key: str | None = None):
    job = job_store.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if persistence.is_worker_active(job_id):
        return {"job_id": job_id, "status": "running"}
    if api_key and api_key.strip():
        job.api_key_override = api_key.strip()
        persistence.save_session(job_id, job.api_key_override)
    job.push_event({"status": "queued", "phase": "queued", "message": "Job queued"})
    background_tasks.add_task(fn, job)
    return {"job_id": job_id, "status": "queued"}


def _update_preview(job_id: str) -> None:
    d = persistence.job_dir(job_id)
    preview = {}
    try:
        headlines_path = d / "headlines_clean.csv"
        labels_path = d / "tz_headlines_labelled.csv"
        source = headlines_path if headlines_path.exists() else labels_path if labels_path.exists() else None
        if source is not None and (d / "cpi.csv").exists() and (d / "fx.csv").exists():
            h = pd.read_csv(source, nrows=50000, engine="python", on_bad_lines="warn")
            c = pd.read_csv(d / "cpi.csv", engine="python", on_bad_lines="warn")
            f = pd.read_csv(d / "fx.csv", engine="python", on_bad_lines="warn")
            preview = preview_uploads(h, c, f)
            if source == labels_path:
                preview["labelled_rows"] = len(h)
                if "relevant" in h.columns:
                    preview["relevant_rows"] = int(h["relevant"].astype(str).str.lower().isin(["true", "1"]).sum())
    except Exception:
        preview = {}
    job = job_store.get(job_id)
    if job:
        job.preview = preview
        job.save()


@router.get("/jobs")
async def list_jobs():
    jobs = job_store.list_jobs()
    return {"jobs": jobs, "last_active_job_id": persistence.get_latest_job_id()}


@router.get("/jobs/latest")
async def latest_job():
    job_id = persistence.get_latest_job_id()
    if not job_id:
        raise HTTPException(status_code=404, detail="No jobs yet")
    persistence.sync_job_from_disk(job_id)
    job = job_store.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job.to_dict()


@router.post("/jobs")
async def create_job(name: str = Form(...), api_key: str | None = Form(default=None)):
    clean_name = name.strip()
    if not clean_name:
        raise HTTPException(status_code=400, detail="Session name is required")
    if len(clean_name) > 80:
        raise HTTPException(status_code=400, detail="Session name must be 80 characters or fewer")
    override = api_key.strip() if api_key and api_key.strip() else None
    job = job_store.create(preview={}, api_key_override=override, name=clean_name)
    return {"job_id": job.job_id, "name": job.name, "created_at": job.created_at}


@router.patch("/jobs/{job_id}")
async def rename_job(job_id: str, body: JobRename):
    if not persistence.job_dir(job_id).exists():
        raise HTTPException(status_code=404, detail="Job not found")
    clean_name = body.name.strip()
    if not clean_name:
        raise HTTPException(status_code=400, detail="Session name is required")
    if len(clean_name) > 80:
        raise HTTPException(status_code=400, detail="Session name must be 80 characters or fewer")
    try:
        result = persistence.rename_job(job_id, clean_name)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Job not found")
    job = job_store.get(job_id)
    if job:
        job.name = clean_name
        job.updated_at = result["updated_at"]
    return result


@router.delete("/jobs/{job_id}")
async def delete_job(job_id: str):
    if not persistence.job_dir(job_id).exists():
        raise HTTPException(status_code=404, detail="Job not found")
    if persistence.is_worker_active(job_id):
        raise HTTPException(status_code=409, detail="Cannot delete a session while it is running")
    persistence.delete_job(job_id)
    job_store.forget(job_id)
    return {"deleted": job_id}


@router.get("/jobs/{job_id}/pipeline-state")
async def pipeline_state(job_id: str):
    if not persistence.job_dir(job_id).exists():
        raise HTTPException(status_code=404, detail="Job not found")
    return persistence.get_pipeline_state(job_id)


@router.get("/jobs/{job_id}/settings")
async def get_settings(job_id: str):
    if not persistence.job_dir(job_id).exists():
        raise HTTPException(status_code=404, detail="Job not found")
    settings = persistence.load_settings(job_id)
    defaults = notebook_defaults()
    return {
        "settings": settings.to_dict(),
        "defaults": defaults.to_dict(),
        "has_api_key": _has_api_key(job_id),
    }


@router.put("/jobs/{job_id}/settings")
async def put_settings(job_id: str, body: SettingsUpdate):
    if not persistence.job_dir(job_id).exists():
        raise HTTPException(status_code=404, detail="Job not found")
    current = persistence.load_settings(job_id)
    data = current.to_dict()
    payload = body.model_dump(exclude_none=True)
    api_key = payload.pop("api_key", None)
    for key, val in payload.items():
        data[key] = val
    updated = ClassifierSettings.from_dict(data)
    persistence.save_settings(job_id, updated)
    if api_key and api_key.strip():
        persistence.save_session(job_id, api_key.strip())
        job = job_store.get(job_id)
        if job:
            job.api_key_override = api_key.strip()
    return {"settings": updated.to_dict(), "has_api_key": _has_api_key(job_id)}


@router.post("/jobs/{job_id}/settings/reset")
async def reset_settings(job_id: str):
    if not persistence.job_dir(job_id).exists():
        raise HTTPException(status_code=404, detail="Job not found")
    defaults = notebook_defaults()
    persistence.save_settings(job_id, defaults)
    return {"settings": defaults.to_dict()}


@router.post("/jobs/{job_id}/data/headlines")
async def upload_headlines(job_id: str, files: list[UploadFile] = File(...)):
    job_dir = persistence.job_dir(job_id)
    if not job_dir.exists():
        raise HTTPException(status_code=404, detail="Job not found")
    if not files:
        raise HTTPException(status_code=400, detail="No files uploaded")

    frames = []
    raw_dir = job_dir / "headlines_raw"
    raw_dir.mkdir(exist_ok=True)
    for i, f in enumerate(files):
        text = (await f.read()).decode("utf-8", errors="replace")
        df = pd.read_csv(StringIO(text), engine="python", on_bad_lines="warn")
        errors = validate_headlines_df(df)
        if errors:
            raise HTTPException(status_code=400, detail=f"{f.filename}: {'; '.join(errors)}")
        frames.append(df)
        (raw_dir / f"source_{i}_{f.filename or 'upload.csv'}").write_text(text, encoding="utf-8")

    merged = merge_headline_csvs(frames)
    merged.to_csv(job_dir / "headlines_clean.csv", index=False)
    merged.to_csv(job_dir / "headlines.csv", index=False)
    persistence.update_manifest(job_id, {"phases": {"data_headlines": "done"}})
    _update_preview(job_id)
    return {"rows": len(merged), "files": len(files)}


@router.post("/jobs/{job_id}/data/cpi")
async def upload_cpi(job_id: str, file: UploadFile = File(...)):
    job_dir = persistence.job_dir(job_id)
    if not job_dir.exists():
        raise HTTPException(status_code=404, detail="Job not found")
    text = (await file.read()).decode("utf-8", errors="replace")
    df = pd.read_csv(StringIO(text), engine="python", on_bad_lines="warn")
    errors = validate_cpi_df(df)
    if errors:
        raise HTTPException(status_code=400, detail="; ".join(errors))
    df.to_csv(job_dir / "cpi.csv", index=False)
    persistence.update_manifest(job_id, {"phases": {"data_cpi": "done"}})
    _update_preview(job_id)
    return {"rows": len(df)}


@router.post("/jobs/{job_id}/data/fx")
async def upload_fx(job_id: str, file: UploadFile = File(...)):
    job_dir = persistence.job_dir(job_id)
    if not job_dir.exists():
        raise HTTPException(status_code=404, detail="Job not found")
    text = (await file.read()).decode("utf-8", errors="replace")
    df = pd.read_csv(StringIO(text), engine="python", on_bad_lines="warn")
    errors = validate_fx_df(df)
    if errors:
        raise HTTPException(status_code=400, detail="; ".join(errors))
    df.to_csv(job_dir / "fx.csv", index=False)
    persistence.update_manifest(job_id, {"phases": {"data_fx": "done"}})
    _update_preview(job_id)
    return {"rows": len(df)}


@router.post("/jobs/{job_id}/classify")
async def classify_job(job_id: str, background_tasks: BackgroundTasks, api_key: str | None = Form(default=None)):
    state = persistence.get_pipeline_state(job_id)
    if not state["classify"]["can_run"]:
        if state["classify"]["done"]:
            raise HTTPException(
                status_code=400,
                detail="Labelled CSV already present. Continue to Analysis, or upload new raw headlines to re-classify.",
            )
        raise HTTPException(status_code=400, detail="Upload headlines, CPI, and FX first")
    return _enqueue(job_id, background_tasks, run_classify_phase, api_key)


@router.post("/jobs/{job_id}/consolidate")
async def consolidate_job(job_id: str, background_tasks: BackgroundTasks):
    state = persistence.get_pipeline_state(job_id)
    if not state["consolidate"]["ready"]:
        raise HTTPException(status_code=400, detail="Labelled headlines and macro data required")
    return _enqueue(job_id, background_tasks, run_consolidate_phase)


@router.post("/jobs/{job_id}/consolidate/upload-labels")
async def upload_labels(job_id: str, file: UploadFile = File(...)):
    """Accept a pre-labelled CSV so Classify can be skipped."""
    job_dir = persistence.job_dir(job_id)
    if not job_dir.exists():
        raise HTTPException(status_code=404, detail="Job not found")
    text = (await file.read()).decode("utf-8", errors="replace")
    df = pd.read_csv(StringIO(text), engine="python", on_bad_lines="warn")
    errors = validate_labelled_df(df)
    if errors:
        raise HTTPException(status_code=400, detail="; ".join(errors))
    df = normalize_labelled_df(df)
    out = job_dir / "tz_headlines_labelled.csv"
    df.to_csv(out, index=False)

    # Invalidate downstream caches so a new labelled file always re-consolidates
    for stale in ("Visualization_Data.csv", "correlations.json", "analysis_summary.json"):
        stale_path = job_dir / stale
        if stale_path.exists():
            stale_path.unlink()

    persistence.update_manifest(
        job_id,
        {
            "phases": {
                "classify": "done",
                "consolidate": "pending",
                "analysis": "pending",
            },
            "outputs": {
                "labelled": out.name,
                "visualization": None,
                "correlations": None,
            },
        },
    )
    _update_preview(job_id)
    return {
        "rows": len(df),
        "relevant_rows": int(df["relevant"].sum()) if "relevant" in df.columns else 0,
        "can_skip_to_analysis": (job_dir / "cpi.csv").exists() and (job_dir / "fx.csv").exists(),
    }


@router.post("/jobs/{job_id}/start")
async def start_job(job_id: str, background_tasks: BackgroundTasks, api_key: str | None = Form(default=None)):
    return _enqueue(job_id, background_tasks, run_job, api_key)


@router.post("/jobs/{job_id}/resume")
async def resume_job(job_id: str, background_tasks: BackgroundTasks, api_key: str | None = Form(default=None)):
    persistence.sync_job_from_disk(job_id)
    job = job_store.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    state = persistence.get_pipeline_state(job_id)
    if state["analysis"]["done"]:
        return {"job_id": job_id, "status": "completed"}
    if state["consolidate"]["ready"] and not state["consolidate"]["done"]:
        return _enqueue(job_id, background_tasks, run_consolidate_phase, api_key)
    if state["classify"]["ready"]:
        return _enqueue(job_id, background_tasks, run_classify_phase, api_key)
    raise HTTPException(status_code=400, detail="Nothing to resume — upload data first")


@router.get("/jobs/{job_id}/status")
async def job_status(job_id: str):
    persistence.sync_job_from_disk(job_id)
    job = job_store.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job.to_dict()


@router.get("/jobs/{job_id}/events")
async def job_events(job_id: str):
    job = job_store.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    async def stream():
        sent = 0
        while True:
            job = job_store.get(job_id)
            if not job:
                break
            while sent < len(job.events):
                payload = json.dumps(job.events[sent])
                yield f"data: {payload}\n\n"
                sent += 1
            if job.status in ("completed", "failed"):
                break
            await asyncio.sleep(0.5)
        yield 'data: {"type":"close"}\n\n'

    return StreamingResponse(stream(), media_type="text/event-stream")


@router.get("/jobs/{job_id}/analysis")
async def get_analysis(job_id: str):
    job_dir = persistence.job_dir(job_id)
    viz_path = job_dir / "Visualization_Data.csv"
    corr_path = job_dir / "correlations.json"
    summary_path = job_dir / "analysis_summary.json"
    if not viz_path.exists():
        raise HTTPException(status_code=404, detail="Analysis not ready")
    viz = pd.read_csv(viz_path)
    corr = json.loads(corr_path.read_text(encoding="utf-8")) if corr_path.exists() else compute_correlations(viz)
    summary = read_summary(summary_path, corr, viz)
    return {"correlations": corr, "summary": summary, "months": len(viz)}


def read_summary(summary_path: Path, corr: dict, viz: pd.DataFrame) -> dict:
    if summary_path.exists():
        return json.loads(summary_path.read_text(encoding="utf-8"))
    summary = build_analysis_summary(corr, viz)
    persistence.atomic_write_json(summary_path, summary)
    return summary


@router.get("/jobs/{job_id}/visualization-data")
async def visualization_data(job_id: str):
    path = RUNS_DIR / job_id / "Visualization_Data.csv"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Results not ready")
    return FileResponse(path, media_type="text/csv", filename="Visualization_Data.csv")


@router.get("/jobs/{job_id}/correlations")
async def correlations(job_id: str):
    path = RUNS_DIR / job_id / "correlations.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Correlations not ready")
    return json.loads(path.read_text(encoding="utf-8"))


@router.get("/jobs/{job_id}/downloads/{filename}")
async def download(job_id: str, filename: str):
    allowed = {
        "Visualization_Data.csv": "Visualization_Data.csv",
        "tz_headlines_labelled.csv": "tz_headlines_labelled.csv",
        "headlines_clean.csv": "headlines_clean.csv",
    }
    if filename not in allowed:
        raise HTTPException(status_code=404, detail="Unknown file")
    path = RUNS_DIR / job_id / allowed[filename]
    if not path.exists():
        raise HTTPException(status_code=404, detail="File not ready")
    return FileResponse(path, media_type="text/csv", filename=filename)