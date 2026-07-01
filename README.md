# EF-02 — Tanzania Financial News Sentiment Analyser

Investigates whether sentiment in Tanzanian financial news headlines correlates with macroeconomic movement (USD/TZS exchange rate and headline inflation) across 2022–2024.

Production classification uses **Groq** (`llama-3.1-8b-instant`) with an 11-category v5 prompt schema.

## Setup

1. **Python 3.10+** and Jupyter (VS Code, JupyterLab, or Anaconda).
2. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

   Or run `notebooks/00_setup.ipynb` for guided installs.

3. Copy the environment template and add your Groq API key:

   ```bash
   cp .env.example .env
   ```

   Get a key at [console.groq.com](https://console.groq.com).

## Pipeline (run in order)

| Notebook | Purpose |
|----------|---------|
| `notebooks/00_setup.ipynb` | Install packages and verify environment |
| `notebooks/01_scraper.ipynb` | Scrape Daily News and The Citizen |
| `notebooks/02_cleaning.ipynb` | Dedupe, date-filter, clean headlines |
| `notebooks/04_classifier.ipynb` | Groq LLM classification (relevance, category, sentiment) |
| `notebooks/05_consolidation.ipynb` | Monthly aggregates + CPI + FX |
| `notebooks/06_visualisation.ipynb` | Charts and Pearson correlation analysis |

See `docs/00_pipeline_overview.ipynb` for a full pipeline map.

## Data included in this repo

**Raw**

- `data/raw/citizen_raw.csv`, `dailynews_raw.csv` — scraped headlines
- `data/raw/tanzania_cpi_2022_2024.csv` — monthly CPI / inflation
- `data/raw/usd_tzs_2022_2024.csv` — USD/TZS exchange rates

**Processed (final Groq run)**

- `data/processed/tz_headlines_clean.csv` — cleaned combined headlines
- `data/processed/tz_headlines_labelled.csv` — Groq-classified output
- `data/processed/Visualization_Data.csv` — 36-month monthly aggregates

## Scripts

- `scripts/retry_sentiment.py` — Re-classify rows missing valid sentiment labels and regenerate consolidation output.

## Intentionally excluded

Testing artifacts (benchmark notebooks, gold-set eval tools, test-run CSVs, backup files) and alternate provider pipelines are kept local and not tracked in this repository.
