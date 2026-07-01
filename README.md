# Financial News Sentiment Analyzer for Economic Forecasting

Investigates whether sentiment in Tanzanian financial news headlines correlates with macroeconomic movement (USD/TZS exchange rate and headline inflation) across 2022–2024.

Production classification uses **Groq** (`llama-3.1-8b-instant`) with an 11-category v5 prompt schema. The committed results in this repo were produced with that model.

> **Model caveat:** Groq is officially decommissioning **Llama 3.1 8B Instant** on **16 August 2026**. If you re-run the classifier on Groq’s free or developer tiers, migrate before that date to avoid interruptions. Groq’s recommended replacement is **`openai/gpt-oss-20b`** (similar speed and strong agentic performance). **`llama-3.3-70b-versatile`** also remains available on Groq as a free-tier alternative. For the best classification quality and stability, a fully paid API key (e.g. OpenAI `gpt-4o-mini` or equivalent) is recommended. See [Groq model deprecation docs](https://console.groq.com/docs/deprecations) for official upgrade paths.

## Setup (local)

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

## Google Colab

**Start here:** [Open `00_setup.ipynb` in Colab](https://colab.research.google.com/github/K2Debug/Financial-News-Sentiment-Analyzer-for-Economic-Forecasting/blob/main/notebooks/00_setup.ipynb)

Run the top Colab section in `00_setup.ipynb` first — it clones this repo to `/content/EF-02` and installs all dependencies. Then run the pipeline notebooks below in order. Each notebook’s first cell points to the cloned workspace so `../data/` paths resolve correctly; if you open a later notebook directly, that cell will initialize the workspace for you.

| Notebook | Purpose | Open in Colab |
|----------|---------|---------------|
| `00_setup.ipynb` | Clone repo, install packages, verify environment | [Open](https://colab.research.google.com/github/K2Debug/Financial-News-Sentiment-Analyzer-for-Economic-Forecasting/blob/main/notebooks/00_setup.ipynb) |
| `01_scraper.ipynb` | Scrape Daily News and The Citizen | [Open](https://colab.research.google.com/github/K2Debug/Financial-News-Sentiment-Analyzer-for-Economic-Forecasting/blob/main/notebooks/01_scraper.ipynb) |
| `02_cleaning.ipynb` | Dedupe, date-filter, clean headlines | [Open](https://colab.research.google.com/github/K2Debug/Financial-News-Sentiment-Analyzer-for-Economic-Forecasting/blob/main/notebooks/02_cleaning.ipynb) |
| `03_benchmarking.ipynb` | Benchmark sentiment models (TextBlob, VADER, FinBERT, LLMs) | [Open](https://colab.research.google.com/github/K2Debug/Financial-News-Sentiment-Analyzer-for-Economic-Forecasting/blob/main/notebooks/03_benchmarking.ipynb) |
| `04_classifier.ipynb` | Groq LLM classification (relevance, category, sentiment) | [Open](https://colab.research.google.com/github/K2Debug/Financial-News-Sentiment-Analyzer-for-Economic-Forecasting/blob/main/notebooks/04_classifier.ipynb) |
| `05_consolidation.ipynb` | Monthly aggregates + CPI + FX | [Open](https://colab.research.google.com/github/K2Debug/Financial-News-Sentiment-Analyzer-for-Economic-Forecasting/blob/main/notebooks/05_consolidation.ipynb) |
| `06_visualisation.ipynb` | Charts and Pearson correlation analysis | [Open](https://colab.research.google.com/github/K2Debug/Financial-News-Sentiment-Analyzer-for-Economic-Forecasting/blob/main/notebooks/06_visualisation.ipynb) |

Add your API keys to `/content/EF-02/.env` after setup (copy from `.env.example`).

## Pipeline (run in order)

| Notebook | Purpose |
|----------|---------|
| `notebooks/00_setup.ipynb` | Install packages and verify environment |
| `notebooks/01_scraper.ipynb` | Scrape Daily News and The Citizen |
| `notebooks/02_cleaning.ipynb` | Dedupe, date-filter, clean headlines |
| `notebooks/03_benchmarking.ipynb` | Benchmark sentiment models (TextBlob, VADER, FinBERT, LLMs) |
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
