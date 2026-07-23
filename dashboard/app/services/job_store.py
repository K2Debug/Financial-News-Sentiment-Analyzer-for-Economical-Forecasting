"""In-memory job registry backed by disk persistence."""
from __future__ import annotations

import json
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import RUNS_DIR, STATIC_DIR
from app.services import persistence


@dataclass
class JobState:
    job_id: str
    name: str = "Untitled analysis"
    status: str = "created"
    phase: str = "idle"
    message: str = ""
    batch: int = 0
    total_batches: int = 0
    headlines_done: int = 0
    headlines_total: int = 0
    preview: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    events: list[dict[str, Any]] = field(default_factory=list)
    api_key_override: str | None = None

    def dir(self) -> Path:
        return persistence.job_dir(self.job_id)

    def status_path(self) -> Path:
        return self.dir() / "status.json"

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "name": self.name,
            "status": self.status,
            "phase": self.phase,
            "message": self.message,
            "batch": self.batch,
            "total_batches": self.total_batches,
            "headlines_done": self.headlines_done,
            "headlines_total": self.headlines_total,
            "preview": self.preview,
            "error": self.error,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    def save(self) -> None:
        self.dir().mkdir(parents=True, exist_ok=True)
        persistence.atomic_write_json(self.status_path(), self.to_dict())
        persistence.update_manifest(
            self.job_id,
            {
                "name": self.name,
                "status": self.status,
                "preview": self.preview,
                "progress": {
                    "batch": self.batch,
                    "total_batches": self.total_batches,
                    "headlines_done": self.headlines_done,
                    "headlines_total": self.headlines_total,
                },
            },
        )
        persistence.upsert_index_entry(self.job_id, self.to_dict())

    def push_event(self, event: dict[str, Any]) -> None:
        self.events.append(event)
        for key in ("phase", "message", "batch", "total_batches", "headlines_done", "headlines_total", "status", "error"):
            if key in event:
                setattr(self, key, event[key])
        self.save()
        phase = event.get("phase")
        if phase == "clean":
            persistence.update_manifest(self.job_id, {"phases": {"clean": "done"}})
        elif phase in ("classify", "classify_retry"):
            persistence.update_manifest(self.job_id, {"phases": {"classify": "in_progress"}})
        elif phase == "consolidate":
            persistence.update_manifest(self.job_id, {"phases": {"classify": "done", "consolidate": "in_progress"}})
        elif phase == "done" or event.get("status") == "completed":
            persistence.update_manifest(
                self.job_id,
                {
                    "phases": {
                        "clean": "done",
                        "classify": "done",
                        "consolidate": "done",
                        "correlations": "done",
                    },
                    "outputs": {
                        "labelled": "tz_headlines_labelled.csv",
                        "visualization": "Visualization_Data.csv",
                        "correlations": "correlations.json",
                    },
                },
            )


class JobStore:
    def __init__(self) -> None:
        self._jobs: dict[str, JobState] = {}
        self._lock = threading.Lock()

    def create(
        self,
        preview: dict[str, Any] | None = None,
        api_key_override: str | None = None,
        name: str = "Untitled analysis",
    ) -> JobState:
        job_id = uuid.uuid4().hex[:12]
        preview = preview or {}
        clean_name = name.strip() or "Untitled analysis"
        job = JobState(job_id=job_id, name=clean_name, preview=preview, api_key_override=api_key_override)
        job.dir().mkdir(parents=True, exist_ok=True)
        persistence.atomic_write_json(
            persistence.manifest_path(job_id),
            persistence.build_manifest(job_id, preview, name=clean_name),
        )
        persistence.save_session(job_id, api_key_override)
        persistence.load_settings(job_id)
        job.save()
        with self._lock:
            self._jobs[job_id] = job
        return job

    def get(self, job_id: str) -> JobState | None:
        with self._lock:
            job = self._jobs.get(job_id)
        if job:
            return job

        status_path = RUNS_DIR / job_id / "status.json"
        if not status_path.exists():
            persistence.sync_job_from_disk(job_id)
            if not status_path.exists():
                return None

        data = json.loads(status_path.read_text(encoding="utf-8"))
        manifest = persistence.read_json(persistence.manifest_path(job_id), {})
        api_key = persistence.load_session_api_key(job_id)
        job = JobState(
            job_id=job_id,
            name=data.get("name") or manifest.get("name") or f"Session {job_id[:8]}",
            status=data.get("status", "unknown"),
            phase=data.get("phase", "idle"),
            message=data.get("message", ""),
            batch=data.get("batch", 0),
            total_batches=data.get("total_batches", 0),
            headlines_done=data.get("headlines_done", 0),
            headlines_total=data.get("headlines_total", 0),
            preview=data.get("preview", {}),
            error=data.get("error"),
            created_at=data.get("created_at", "") or manifest.get("created_at", ""),
            updated_at=data.get("updated_at", "") or manifest.get("updated_at", ""),
            api_key_override=api_key,
        )
        with self._lock:
            self._jobs[job_id] = job
        return job

    def list_jobs(self) -> list[dict[str, Any]]:
        persistence.recover_all_jobs_on_startup()
        return persistence.list_index_jobs()

    def forget(self, job_id: str) -> None:
        with self._lock:
            self._jobs.pop(job_id, None)


job_store = JobStore()
