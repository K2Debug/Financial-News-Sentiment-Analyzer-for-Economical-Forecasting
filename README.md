# EF-02 — Tanzania Financial News Sentiment Analyser

Investigates whether sentiment in Tanzanian financial news headlines correlates with macroeconomic movement (CPI inflation and USD/TZS) across 2022–2024.

**The main deliverable is the interactive dashboard.** Notebook research, experiments, and reports live beside it as supporting material.

## Quick start (dashboard)

```bash
cd dashboard
py -m pip install -r requirements.txt
# keys live in ef02/.env (copy from ../.env.example if needed)
py -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000

Pipeline in the UI: **Data Import → Classify (optional) → Analysis**.

API keys: put them in [`../.env`](.env) at the project root (see [`.env.example`](.env.example)). The dashboard also accepts `dashboard/.env` as a local override.

Details: [`dashboard/README.md`](dashboard/README.md)

## Project layout

```
ef02/
├── dashboard/       # ★ Main product — FastAPI + sectioned pipeline UI
├── research/        # Notebook pipeline that produced the original findings
├── experiments/     # Side-tracks (OpenAI audit, gpt-oss comparison)
├── reports/         # Word/PDF reports + generators + figures
├── docs/            # Architecture plan, decision log, outline
└── archive/         # Old prototypes and legacy scratch work
```

| Folder | Role |
|--------|------|
| `dashboard/` | Production tool — upload CPI/FX/headlines, classify, consolidate, chart |
| `research/` | Numbered notebooks (`01`–`06`), research data, demo docs |
| `experiments/` | One-off model / audit runs (not the mainline story) |
| `reports/` | Academic / tool reports and figure assets |
| `docs/` | Project narrative (architecture, decisions) |
| `archive/` | Superseded static UI, early drafts, share zips |

## Research notebooks

If you need the original Colab / Jupyter pipeline:

```bash
cd research
py -m pip install -r requirements.txt
```

See [`research/README.md`](research/README.md).

## Docs & reports

- Architecture: [`docs/architecture.md`](docs/architecture.md)
- Decision log: [`docs/decision-log.md`](docs/decision-log.md)
- Report generators: `reports/generate_report.py`, `reports/generate_tool_report.py`
