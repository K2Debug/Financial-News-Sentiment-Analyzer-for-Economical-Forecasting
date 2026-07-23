"""Shared paths for the dashboard app."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNS_DIR = ROOT / "runs"
STATIC_DIR = ROOT / "static"
INDEX_PATH = RUNS_DIR / "index.json"
