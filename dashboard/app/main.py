"""EF-02 Dashboard — FastAPI application."""
from __future__ import annotations

from contextlib import asynccontextmanager
from urllib.parse import urlencode

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.config import ROOT, RUNS_DIR, STATIC_DIR
from app.routes.jobs import router as jobs_router
from app.services.persistence import recover_all_jobs_on_startup

# Prefer monorepo root .env; keep local/legacy paths as fallbacks
load_dotenv(ROOT.parent / ".env")
load_dotenv(ROOT / ".env")
load_dotenv(ROOT.parent / "research" / ".env")


@asynccontextmanager
async def lifespan(app: FastAPI):
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    recover_all_jobs_on_startup()
    yield


app = FastAPI(title="EF-02 Dashboard", version="2.0.0", lifespan=lifespan)
app.include_router(jobs_router)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
async def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/progress/{job_id}")
async def progress_redirect(job_id: str):
    q = urlencode({"job": job_id, "page": "classify"})
    return RedirectResponse(url=f"/?{q}")


@app.get("/results/{job_id}")
async def results_redirect(job_id: str):
    q = urlencode({"job": job_id, "page": "analysis"})
    return RedirectResponse(url=f"/?{q}")
