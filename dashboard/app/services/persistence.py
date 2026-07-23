"""Durable job storage: manifests, global index, recovery, worker locks."""
from __future__ import annotations

import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import INDEX_PATH, RUNS_DIR

# Jobs actively executing in this server process
_active_workers: set[str] = set()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


from ef02_core.io import atomic_write_json


def read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default


def job_dir(job_id: str) -> Path:
    return RUNS_DIR / job_id


def infer_status_from_files(job_path: Path) -> str:
    """Derive authoritative status from artifacts on disk."""
    viz = job_path / "Visualization_Data.csv"
    corr = job_path / "correlations.json"
    labels = job_path / "tz_headlines_labelled.csv"
    checkpoint = job_path / "classification_checkpoint.json"
    clean = job_path / "headlines_clean.csv"
    uploads = job_path / "headlines.csv"

    if viz.exists() and corr.exists():
        return "completed"
    if labels.exists() and not viz.exists():
        return "interrupted"
    if checkpoint.exists():
        return "interrupted"
    if clean.exists() or uploads.exists():
        return "created"
    return "created"


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    else:
        return True


def lock_path(job_id: str) -> Path:
    return job_dir(job_id) / "worker.lock"


def is_worker_active(job_id: str) -> bool:
    if job_id in _active_workers:
        return True
    lp = lock_path(job_id)
    data = read_json(lp)
    if not data:
        return False
    pid = int(data.get("pid", 0))
    if _pid_alive(pid):
        return True
    lp.unlink(missing_ok=True)
    return False


def acquire_worker_lock(job_id: str) -> bool:
    if is_worker_active(job_id):
        return False
    _active_workers.add(job_id)
    atomic_write_json(lock_path(job_id), {"pid": os.getpid(), "started_at": utc_now()})
    return True


def release_worker_lock(job_id: str) -> None:
    _active_workers.discard(job_id)
    lock_path(job_id).unlink(missing_ok=True)


def manifest_path(job_id: str) -> Path:
    return job_dir(job_id) / "manifest.json"


def session_path(job_id: str) -> Path:
    return job_dir(job_id) / "session.json"


def save_session(job_id: str, api_key_override: str | None) -> None:
    if api_key_override:
        atomic_write_json(session_path(job_id), {"api_key_override": api_key_override})


def load_session_api_key(job_id: str) -> str | None:
    data = read_json(session_path(job_id), {})
    key = data.get("api_key_override")
    return key if key else None


def update_manifest(job_id: str, patch: dict[str, Any]) -> None:
    path = manifest_path(job_id)
    manifest = read_json(path, {})
    for key, value in patch.items():
        if key in ("phases", "outputs", "progress") and isinstance(value, dict):
            manifest.setdefault(key, {})
            manifest[key].update(value)
        else:
            manifest[key] = value
    manifest["job_id"] = job_id
    manifest["updated_at"] = utc_now()
    atomic_write_json(path, manifest)


def build_manifest(
    job_id: str,
    preview: dict[str, Any],
    status: str = "created",
    name: str = "Untitled analysis",
) -> dict[str, Any]:
    now = utc_now()
    return {
        "job_id": job_id,
        "name": name.strip() or "Untitled analysis",
        "created_at": now,
        "updated_at": now,
        "status": status,
        "preview": preview,
        "phases": {
            "data_headlines": "pending",
            "data_cpi": "pending",
            "data_fx": "pending",
            "classify": "pending",
            "consolidate": "pending",
            "analysis": "pending",
        },
        "outputs": {
            "labelled": None,
            "visualization": None,
            "correlations": None,
        },
    }


def load_index() -> dict[str, Any]:
    data = read_json(INDEX_PATH, {"jobs": [], "last_active_job_id": None})
    if "jobs" not in data:
        data["jobs"] = []
    return data


def save_index(data: dict[str, Any]) -> None:
    atomic_write_json(INDEX_PATH, data)


def upsert_index_entry(job_id: str, entry: dict[str, Any]) -> None:
    index = load_index()
    jobs: list[dict[str, Any]] = index.get("jobs", [])
    jobs = [j for j in jobs if j.get("job_id") != job_id]
    jobs.insert(0, entry)
    index["jobs"] = jobs[:50]
    index["last_active_job_id"] = job_id
    save_index(index)


def list_index_jobs() -> list[dict[str, Any]]:
    return load_index().get("jobs", [])


def get_latest_job_id() -> str | None:
    index = load_index()
    last = index.get("last_active_job_id")
    if last and job_dir(last).exists():
        return last
    jobs = index.get("jobs", [])
    return jobs[0]["job_id"] if jobs else None


def sync_job_from_disk(job_id: str) -> dict[str, Any] | None:
    """Reconcile status.json + manifest with files; return summary for index."""
    path = job_dir(job_id)
    if not path.is_dir():
        return None

    inferred = infer_status_from_files(path)
    status_data = read_json(path / "status.json", {})
    stored_status = status_data.get("status", "created")

    if stored_status == "running" and not is_worker_active(job_id):
        stored_status = "interrupted"
    if inferred == "completed":
        stored_status = "completed"
    elif inferred == "interrupted" and stored_status not in ("completed", "failed"):
        stored_status = "interrupted"

    status_data["status"] = stored_status
    status_data["job_id"] = job_id
    atomic_write_json(path / "status.json", status_data)

    manifest = read_json(manifest_path(job_id), {})
    if manifest:
        manifest["status"] = stored_status
        manifest["updated_at"] = utc_now()
        if inferred == "completed":
            manifest.setdefault("phases", {})
            manifest["phases"]["clean"] = "done"
            manifest["phases"]["classify"] = "done"
            manifest["phases"]["consolidate"] = "done"
            manifest["phases"]["correlations"] = "done"
            manifest.setdefault("outputs", {})
            manifest["outputs"]["visualization"] = "Visualization_Data.csv"
            manifest["outputs"]["labelled"] = "tz_headlines_labelled.csv"
            manifest["outputs"]["correlations"] = "correlations.json"
        atomic_write_json(manifest_path(job_id), manifest)

    preview = status_data.get("preview") or manifest.get("preview") or {}
    name = (
        manifest.get("name")
        or status_data.get("name")
        or f"Session {job_id[:8]}"
    )
    entry = {
        "job_id": job_id,
        "name": name,
        "status": stored_status,
        "phase": status_data.get("phase", ""),
        "message": status_data.get("message", ""),
        "created_at": status_data.get("created_at") or manifest.get("created_at", ""),
        "updated_at": manifest.get("updated_at") or status_data.get("updated_at") or status_data.get("created_at", ""),
        "preview": preview,
        "batch": status_data.get("batch", 0),
        "total_batches": status_data.get("total_batches", 0),
    }
    upsert_index_entry(job_id, entry)
    return entry


def rename_job(job_id: str, name: str) -> dict[str, Any]:
    clean = name.strip()
    if not clean:
        raise ValueError("Session name cannot be empty")
    path = job_dir(job_id)
    if not path.is_dir():
        raise FileNotFoundError("Job not found")

    now = utc_now()
    manifest = read_json(manifest_path(job_id), {})
    manifest["name"] = clean
    manifest["updated_at"] = now
    manifest["job_id"] = job_id
    atomic_write_json(manifest_path(job_id), manifest)

    status_path = path / "status.json"
    status_data = read_json(status_path, {})
    status_data["name"] = clean
    status_data["updated_at"] = now
    status_data["job_id"] = job_id
    atomic_write_json(status_path, status_data)

    index = load_index()
    for job in index.get("jobs", []):
        if job.get("job_id") == job_id:
            job["name"] = clean
            job["updated_at"] = now
            break
    save_index(index)
    return {"job_id": job_id, "name": clean, "updated_at": now}


def delete_job(job_id: str) -> None:
    if is_worker_active(job_id):
        raise RuntimeError("Cannot delete a session while it is running")

    path = job_dir(job_id)
    if path.is_dir():
        shutil.rmtree(path)

    _active_workers.discard(job_id)
    lock_path(job_id).unlink(missing_ok=True)

    index = load_index()
    jobs = [j for j in index.get("jobs", []) if j.get("job_id") != job_id]
    index["jobs"] = jobs
    if index.get("last_active_job_id") == job_id:
        index["last_active_job_id"] = jobs[0]["job_id"] if jobs else None
    save_index(index)


def settings_path(job_id: str) -> Path:
    return job_dir(job_id) / "settings.json"


def load_settings(job_id: str):
    from ef02_core.prompts import ClassifierSettings, notebook_defaults

    data = read_json(settings_path(job_id))
    if not data:
        defaults = notebook_defaults()
        save_settings(job_id, defaults)
        return defaults
    return ClassifierSettings.from_dict(data)


def save_settings(job_id: str, settings) -> None:
    atomic_write_json(settings_path(job_id), settings.to_dict())


def get_pipeline_state(job_id: str) -> dict:
    """Return readiness flags for each UI section."""
    d = job_dir(job_id)
    clean = (d / "headlines_clean.csv").exists()
    cpi = (d / "cpi.csv").exists()
    fx = (d / "fx.csv").exists()
    labels = (d / "tz_headlines_labelled.csv").exists()
    viz = (d / "Visualization_Data.csv").exists()
    corr = (d / "correlations.json").exists()

    classify_ready = clean and cpi and fx
    # Skip-classify path: labelled CSV + macro data is enough for consolidation/analysis
    consolidate_ready = labels and cpi and fx
    # Data Import is "complete" for either classify path or skip-to-analysis path
    data_ready = classify_ready or consolidate_ready
    return {
        "data": {
            "ready": data_ready,
            "headlines": clean,
            "labels": labels,
            "cpi": cpi,
            "fx": fx,
            "can_classify": classify_ready,
            "can_skip_to_analysis": consolidate_ready,
        },
        "classify": {
            "ready": classify_ready or labels,
            "done": labels,
            "can_run": classify_ready and not persistence_is_running(job_id),
            "optional": labels,
        },
        "consolidate": {
            "ready": consolidate_ready,
            "done": viz,
            "can_run": consolidate_ready and not persistence_is_running(job_id),
        },
        "analysis": {
            "ready": viz and corr,
            "done": viz and corr,
        },
    }


def persistence_is_running(job_id: str) -> bool:
    return is_worker_active(job_id)


def recover_all_jobs_on_startup() -> list[dict[str, Any]]:
    """Scan runs/ and fix stale running jobs; rebuild index."""
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    recovered: list[dict[str, Any]] = []
    for child in sorted(RUNS_DIR.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        if not child.is_dir() or child.name.startswith("."):
            continue
        entry = sync_job_from_disk(child.name)
        if entry:
            recovered.append(entry)

    if recovered and not load_index().get("last_active_job_id"):
        save_index({"jobs": recovered[:50], "last_active_job_id": recovered[0]["job_id"]})
    return recovered
