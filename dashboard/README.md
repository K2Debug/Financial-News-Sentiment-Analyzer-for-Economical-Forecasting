# EF-02 Dashboard (v2)

**Main product** for this project (parent folder: `ef02/`).

Sectioned pipeline UI for Tanzania financial news sentiment analysis.

## Run

```bash
cd dashboard
py -m pip install -r requirements.txt
py -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000

API keys load from the monorepo root `ef02/.env` (preferred), then `dashboard/.env`, then `research/.env`.

## Workflow (sidebar sections)

1. **Data Import** — upload CPI + USD/TZS, then either raw headlines **or** a pre-labelled CSV
2. **Classify** (optional) — OpenAI gpt-4o-mini labelling; skip if you uploaded labelled data
3. **Analysis** — consolidate monthly data, then correlation table and charts

### Skip-classify path

Upload `tz_headlines_labelled.csv`-style file with columns:
`date, headline, relevant, category, sentiment`

Plus CPI and FX → **Skip to Analysis** → Run consolidation.

## Settings (gear icon)

- Edit system/user prompts (defaults from `04_classifier.ipynb`)
- Adjust batch size, retry batch size, sleep between batches
- Stored per job in `runs/{job_id}/settings.json`

## API (v2)

- `POST /api/jobs` — create empty job
- `POST /api/jobs/{id}/data/headlines` — multipart `files[]`
- `POST /api/jobs/{id}/data/cpi` | `data/fx` — single CSV
- `GET /api/jobs/{id}/pipeline-state` — section unlock status
- `POST /api/jobs/{id}/classify` | `consolidate`
- `POST /api/jobs/{id}/consolidate/upload-labels` — skip re-classify
- `GET /api/jobs/{id}/analysis` — conclusion + correlations
- `GET/PUT /api/jobs/{id}/settings`

Artifacts cache under `runs/{job_id}/` between sections.
