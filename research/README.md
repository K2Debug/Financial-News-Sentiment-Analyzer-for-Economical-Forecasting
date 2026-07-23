# Research pipeline (notebooks)

Historical notebook pipeline for EF-02. This is **not** the main product — use [`../dashboard/`](../dashboard/) for the interactive tool.

Production classification in these notebooks used **Groq** (`llama-3.1-8b-instant`). The dashboard defaults to OpenAI (`gpt-4o-mini`).

## Setup

```bash
pip install -r requirements.txt
# Prefer project-root keys: copy ../.env.example → ../.env
# Local research/.env still works as a fallback
```

## Pipeline (run in order)

| Notebook | Purpose |
|----------|---------|
| `notebooks/00_setup.ipynb` | Install packages and verify environment |
| `notebooks/01_scraper.ipynb` | Scrape Daily News and The Citizen |
| `notebooks/02_cleaning.ipynb` | Dedupe, date-filter, clean headlines |
| `notebooks/03_benchmarking.ipynb` | Benchmark sentiment models |
| `notebooks/04_classifier.ipynb` | LLM classification (relevance, category, sentiment) |
| `notebooks/05_consolidation.ipynb` | Monthly aggregates + CPI + FX |
| `notebooks/06_visualisation.ipynb` | Charts and Pearson correlation analysis |

Conceptual walkthroughs: `docs/` (demo notebooks).

> Note: this folder may still contain its own `.git` history from the earlier standalone research repo. The monorepo entrypoint is the parent `ef02/` folder.
