# EF-02: Financial News Sentiment Analyser
## Architecture & Restructuring Plan

> **Layout note (Jul 2026):** The live monorepo root is `ef02/` with `dashboard/` as the main product and the notebook pipeline under `research/`. Section 6 below still documents the earlier notebook-only `EF-02/` tree for historical context.

**Project:** EF-02 — Tanzania Financial News Sentiment Analysis  
**Programme:** BSc Data Science and AI, Ardhi University  
**Academic Year:** 2025/2026  
**Author:** K2 | Group 8  
**Supervisors:** Dr. Ahmad, Mr. Kamali

---

## 1. Project Overview

EF-02 investigates whether the sentiment of Tanzanian financial news headlines can be used as a leading or concurrent indicator of macroeconomic movement — specifically TZS inflation and the USD/TZS exchange rate — between 2022 and 2024.

The core research question is: **does the tone of financial media in Tanzania correlate with measurable economic outcomes at the monthly level?**

The project pipeline covers the full data science lifecycle: raw web scraping, LLM-based classification, economic data acquisition, monthly aggregation, and visualisation-driven correlation analysis. The current codebase exists across several experimental notebooks. This document serves as the reference for restructuring that work into a clean, reproducible, and presentable project.

---

## 2. Development Timeline

The project did not begin with scraping. The actual sequence was:

**Phase 1 — Model Benchmarking (proof of concept)**  
Before any real data was scraped, a benchmarking phase was run on synthetic and small sample data to determine which NLP model could reliably classify Tanzanian financial sentiment. The progression of models tested, in order of increasing accuracy:

| Model | Accuracy |
|---|---|
| TextBlob | ~28% |
| VADER | ~50% |
| FinBERT | ~67% |
| LLM (GPT-4o-mini, Llama 3.1 8B, Llama 3.3 70B) | ~92% |

The benchmarking used a multi-model batch runner (`gpt_notebook.ipynb`) that sent numbered headlines to multiple providers in parallel — OpenAI via the `openai` SDK and Groq via the `groq` SDK — validated output length and label validity, and compiled results into a comparison DataFrame for accuracy scoring against a labelled ground truth.

This phase established that an LLM-based approach via Groq's free tier was both viable and necessary, and that implied economic outcome was a better classification signal than surface emotional tone.

**Phase 2 — Scraping**  
With the classification approach confirmed, the scraper was built to collect real headlines.

**Phase 3 — Classification, Consolidation, and Visualisation**  
The production classifier was built, economic data was sourced, and all data streams were merged and visualised.

---

## 3. Current State of the Codebase

The project currently lives across five notebooks, some of which contain experimental code, dead cells, and exposed API keys. This is the as-is state before restructuring:

| File | Purpose | Status |
|---|---|---|
| `gpt_notebook.ipynb` | Multi-model benchmarking (Phase 1) | Functional but messy; contains exposed API keys |
| `tz_news_scraper.ipynb` | Web scraping Daily News and The Citizen | Functional; output is `final_news_scrape.csv` |
| `Untitled.ipynb` | Production classifier (single-pass 3-in-1 prompt) | Functional; needs clean-up and proper naming |
| `data_consolidation.ipynb` | Merges CPI, FX, and classified headlines | Functional; produces `Visualization_Data.csv` |
| `EF02_Visualization2.ipynb` | 10-section analysis and visualisation notebook | Functional; contains known data quality notes |

---

## 4. Component Breakdown

### 4.1 Web Scraper

**File:** `01_scraper.ipynb`  
**Libraries:** `requests`, `BeautifulSoup` (bs4), `csv`, `os`, `time`, `datetime`  
**Sources:** Daily News Tanzania (`dailynews.co.tz`) and The Citizen (`thecitizen.co.tz`)  
**Outputs:** `data/raw/dailynews_raw.csv`, `data/raw/citizen_raw.csv`

**Source selection rationale:**  
Three Tanzanian English-language outlets were evaluated. IPP Media was ruled out on two grounds: (1) their search archive only covers 2024, not the full 2022–2024 range required; (2) their category filter is a Livewire component that does not modify the URL, making it inaccessible to a `requests`-based scraper without a headless browser. The Guardian Tanzania (owned by IPP) was similarly excluded for the same reasons. Daily News and The Citizen together provide full 2022–2024 coverage and are scrape-friendly.

The scraper paginates through the business category archives of both publications, collecting headline text, publication date, article URL, and source per article. It processes pages sequentially with checkpointing so a network failure does not lose collected data.

**Key behaviours:**
- Shared config dict per source — all selectors, URL pattern, and base domain in one place per section
- Each source has two cells: a test cell (3–5 pages, prints sample headlines) and a full scrape cell
- Live inline logging: scraped pages overwrite a single terminal line between checkpoints
- Checkpoint saves every 30 pages with a permanent printed summary line
- Skipped pages (no articles) and failed pages (connection errors) accumulate silently and print as a summary at the end of the run
- Resume support: update `start_page` to the last checkpoint page to continue after a crash
- Final flush writes remaining records after loop completion

**Logging format:**
```
284 headlines scraped: page 287, page 288, page 289 ...   <- live overwrite
284 headlines scraped: page 287 ... page 316               <- permanent at checkpoint
Checkpoint saved -- page 316 | dailynews_raw.csv

Skipped : page 412 (no articles), page 533 (no articles)  <- end of run only
Failed  : page 290 (ConnectionError)                       <- end of run only
```

**Sample output columns:** `date`, `headline`, `url`, `source`, `scraped_on`

---

### 4.2 Headline Cleaning

**File:** `02_cleaning.ipynb`  
**Libraries:** `pandas`  
**Inputs:** `data/raw/dailynews_raw.csv`, `data/raw/citizen_raw.csv`  
**Output:** `data/processed/tz_headlines_clean.csv`

Merges the two per-source raw CSVs into a single dataset. Parses and normalises dates, removes duplicates, and drops malformed or empty rows. The output is the clean, unified headline file consumed by the production classifier in the next stage.

---

### 4.3 Multi-Model Sentiment Benchmarker

**File:** `03_benchmarking.ipynb`  
**Libraries:** `openai`, `groq`, `pandas`, `sklearn`  
**Models tested:** `gpt-4o-mini` (OpenAI), `llama-3.1-8b-instant` (Groq), `llama-3.3-70b-versatile` (Groq)  
**Input:** `data/processed/tz_headlines_clean.csv` (small labelled sample)  
**Output:** `data/processed/benchmarking_results.csv`

The benchmarker runs a multi-model batch classification function that accepts a Series of headlines and dispatches them to each configured model in sequence. Headlines are sent in numbered batches of 25. Each model's responses are validated for output length (must match input count) and label validity (must be one of `Positive`, `Negative`, `Neutral`). If validation fails, the batch is retried up to 3 times before marking the model as failed.

**System prompt approach at this stage:** Single-label sentiment only, with classification by implied economic outcome rather than emotional tone. The prompt defines each label explicitly:
- Positive: growth, stability, investment, record highs
- Negative: contraction, loss, risk, market decline
- Neutral: informational announcements, budget approvals, no directional signal

**Why this came first:** Running this on a small labelled sample before scraping the full dataset confirmed LLMs were the right tool and that Groq's free tier (Llama 3.3 70B) was sufficient, avoiding the cost of OpenAI at scale.

**Status:** Complete and confirmed running. Fixed system prompt mismatch (Negative definition was copy-pasted from Neutral in the original). Groq accessed via OpenAI SDK with custom base URL.

---

### 4.4 Production Classifier

**File:** `04_classifier.ipynb` (previously `Untitled.ipynb`)  
**Library:** `openai` SDK pointed at Groq base URL (`https://api.groq.com/openai/v1`)  
**Model:** `llama-3.1-8b-instant` (configurable)  
**API:** Groq free tier  
**Input:** `tz_headlines_clean.csv`  
**Output:** `data/processed/tz_headlines_labelled.csv`

The production classifier performs a single-pass three-in-one classification per headline — relevance filtering, category assignment, and sentiment scoring — in a single API call per batch. This is the key architectural decision: rather than making three separate API calls per headline, all three judgments are returned together as a structured JSON array.

**Batch configuration:**
- Batch size: 25 headlines per API call (proven safe within Groq token limits)
- Sleep between batches: 1.5 seconds (rate limit compliance)
- Max retries per batch: 3
- Max tokens per response: 2,500 (25 rows × ~80 tokens each with headroom)
- Temperature: 0 (deterministic output)

**Prompt structure:**  
Each batch sends numbered headlines (1 to 25) to the model. The system prompt instructs the model to return only a valid JSON array with no preamble or markdown fences. Each object in the array contains:
- `pos` — position within the batch (remapped to global `id` after response)
- `relevant` — boolean; true if the headline relates to Tanzania's economy, finance, trade, banking, investment, currency, inflation, energy, or agricultural markets
- `category` — one of 9 defined categories if relevant, otherwise null
- `sentiment` — `Positive`, `Negative`, or `Neutral` if relevant, otherwise null
- `reason` — 4–6 word debug note (dropped before production use)

**The 9 categories:**

| Category | Scope |
|---|---|
| Forex | Exchange rates, TZS/USD, currency reserves |
| Policy | BOT, IMF, World Bank, government economic policy, interest rates, inflation statistics |
| Banking | Commercial banks (CRDB, NBC), mobile money, insurance, fintech |
| Trade | Imports/exports, AfCFTA, ports, counterfeit goods, tariffs |
| Agriculture | Farming, crops, tea, sugar, dairy, food prices |
| Energy | TANESCO, power supply, electricity costs, fuel prices |
| Transport | SGR, railways, roads, ports in logistics context |
| Investment | FDI, PPP, new projects, business expansion |
| General | Financially relevant but fits none of the above |

**Sentiment classification rule:** By implied economic outcome, not emotional tone.
- Positive: growth, stability, record highs, new investment, rate holds amid stability
- Negative: decline, weakening, shortage, rate hikes amid crisis, job losses
- Neutral: announcements, reports, projections with no clear directional outcome

**Retry and failure handling:**  
On `JSONDecodeError` (truncated response) or `ValueError` (length mismatch), the batch is retried with a 2-second sleep. On API errors, the sleep is 3 seconds. If all retries are exhausted, placeholder rows with `None` values and `reason="batch_failed"` are inserted so the merge step is not broken.

**Post-classification output columns:** `date`, `headline`, `source`, `relevant`, `category`, `sentiment`, `reason`

---

### 4.5 Data Consolidation

**File:** `05_consolidation.ipynb`  
**Libraries:** `pandas`  
**Inputs:** `tz_headlines_labelled.csv`, `tanzania_cpi_2022_2024.csv`, `usd_tzs_2022_2024.csv`  
**Output:** `data/processed/Visualization_Data.csv`

This notebook aggregates all three data sources to the monthly level and merges them on a shared `YearMonth` key (`YYYY-MM` string format).

**Exchange rate processing (`usd_tzs_2022_2024.csv`):**  
Source: Investing.com daily USD/TZS historical data. The `Price` column contains comma-formatted strings that must be cleaned before conversion to float. Dates are in `MM/DD/YYYY` format. After cleaning, data is resampled to monthly averages using `resample("ME")`, and a month-on-month percentage change column (`Rate_Change_%`) is computed.

**CPI processing (`tanzania_cpi_2022_2024.csv`):**  
Source: NBS Tanzania CPI Summary Excel file, extracted via a custom parser that reads the `INFLATION RATE` and `ALL ITEMS INDEX` rows from the per-year sheets. The file is already monthly — no resampling needed. The `all_items_index` column is dropped at this stage; only `inflation_rate_%` is carried forward.

**Headlines processing (`tz_headlines_labelled.csv`):**  
Irrelevant headlines (where `relevant == False`) are dropped first. The remaining records are grouped by `YearMonth` to produce:
- `num_headlines` — total relevant headlines per month
- `Top_Category` and `category %` — the dominant category by share of that month's headlines
- `Negative %`, `Neutral %`, `Positive %` — share of each sentiment label per month
- `Dominant_Sentiment` — the modal sentiment for the month

**Final merged DataFrame columns:**

| Column | Source | Description |
|---|---|---|
| `YearMonth` | All | Merge key (`YYYY-MM`) |
| `num_headlines` | Headlines | Total relevant headlines that month |
| `Top_Category` | Headlines | Category with highest share |
| `category %` | Headlines | That category's monthly share |
| `Negative %` | Headlines | Share of negative headlines |
| `Neutral %` | Headlines | Share of neutral headlines |
| `Positive %` | Headlines | Share of positive headlines |
| `Dominant_Sentiment` | Headlines | Modal sentiment label |
| `inflation_rate_%` | CPI | Monthly YoY headline inflation rate |
| `USD/TZS_Rate` | FX | Monthly average exchange rate |
| `Rate_Change_%` | FX | Month-on-month rate change |

---

### 4.6 Visualisation & Analysis

**File:** `06_visualisation.ipynb`  
**Libraries:** `pandas`, `numpy`, `matplotlib`, `seaborn`  
**Input:** `data/processed/Visualization_Data.csv`  
**Style:** `seaborn` whitegrid theme, consistent `SENTIMENT_COLORS` palette (`#2196F3` positive, `#9E9E9E` neutral, `#F44336` negative)

The notebook reads from both `tz_headlines_labelled.csv` (unaggregated) and `Visualization_Data.csv` (monthly aggregates). It engineers a `Net_Sentiment` column (`Positive % − Negative %`) on load. It is organised into 8 sections:

**Section 1 — Setup**
Imports, load both CSVs, engineer `Net_Sentiment`, define `SENTIMENT_COLORS` palette.

**Section 2 — Raw Headline Data Summary**
Reads from `tz_headlines_labelled.csv` directly. Provides context on the unaggregated data before any monthly aggregation is shown.
- 2.1: Donut chart — relevance split (Relevant 72.2% vs Irrelevant 27.8%, n=5,310)
- 2.2: Stacked bar — category share of relevant headlines by month (9 main categories; edge-case categories Tourism/Mining/Inflation noted in markdown)

**Section 3 — Monthly Overview**
- 3.1: Bar chart of monthly relevant headline count with mean line
- 3.2: Horizontal bar — number of months each category was the top category

**Section 4 — Sentiment Distribution**
- 4.1: Stacked bar — monthly Positive / Neutral / Negative share
- 4.2: Net Sentiment Index bar chart (`Positive % − Negative %`), bars colour-coded by sign

**Section 5 — Economic Indicators**
- 5.1: Line with fill — monthly TZS inflation rate (%)
- 5.2: Line with fill — monthly USD/TZS exchange rate

**Section 6 — Sentiment vs Economic Indicators**
All dual-axis charts pair a sentiment line (left axis) with an economic indicator (right axis, dashed). Positive and Negative are shown as side-by-side pairs.
- 6.1: Side-by-side — Positive % vs Inflation | Negative % vs Inflation
- 6.2: Side-by-side — Positive % vs USD/TZS Rate | Negative % vs USD/TZS Rate
- 6.3: Dual-axis — Net Sentiment (bar) vs Rate_Change_% (line)

**Section 7 — Correlation Analysis**
- 7.1: Pearson correlation matrix heatmap (all numeric columns including `Net_Sentiment`)
- 7.2: Printed Pearson r and p-value table for all sentiment vs economic variable pairs, with significance flags (* p<0.05, ** p<0.01, *** p<0.001)

**Section 8 — Limitations**
Markdown only. Documents: missing Jan–Feb 2022 data, Neutral dominance bias, General category over-assignment, and the classifier downgrade from `llama-3.3-70b-versatile` to `llama-3.1-8b-instant`.

---

## 5. Known Data Issues & Planned Fixes

### 5.1 General Category Over-Assignment

**Observed:** `General` is the top category in 24 of 36 months. Approximately 49% of all `General`-labelled headlines keyword-match a more specific category upon post-hoc inspection.

**Root cause:** The classifier prompt did not include a tie-breaking rule. When a headline is cross-cutting or ambiguous, Llama defaults to `General` rather than committing to the most specific applicable category. This is standard LLM behaviour when the prompt does not explicitly penalise the catch-all option.

**Example:** "How Tanzania plans to benefit from carbon credit business" — correctly relevant, but labelled `General` when it should likely be `Investment` or `Trade`.

**Planned fix for next version:**
Add an explicit tie-breaking instruction to the classifier prompt:
> "If a headline could fit both General and a specific category, always prefer the specific category. Use General only when no other category applies at all."

**Recommended pre-fix audit:** Manually review 20–30 flagged General headlines to estimate the true mislabelling rate before committing Groq tokens to a re-classification pass on the entire General subset (~913 records). If the real mislabelling rate is 30%+, a targeted re-run is warranted.

**Impact on analysis:** Category-level sentiment correlations (Banking, Agriculture, Trade) are not materially affected since those categories look clean. The inflation correlation uses headline-level sentiment aggregates, not category breakdowns, so the distortion is limited. However, a corrected General bucket will improve the category distribution charts in Section 2.2.

### 5.2 Neutral Sentiment Dominance

**Observed:** Monthly sentiment aggregates are dominated by Neutral across most of the 2022–2024 period. This limits the discriminatory power of the sentiment signal in correlation analysis.

**Root cause:** Likely a combination of (a) the financial news genre skewing toward factual reporting rather than opinion, and (b) the LLM erring toward Neutral on ambiguous headlines, particularly in early classifier iterations.

**Planned fix:** The tie-breaking prompt fix for General (5.1) may partially address this if some Neutral labels are co-occurring with General misclassifications. A targeted review of Neutral-labelled headlines is recommended alongside the General audit.

---

## 6. Project Structure

The restructured project follows this folder layout (reflects current on-disk state):

```
EF-02/
├── data/
│   ├── raw/
│   │   ├── dailynews_raw.csv              # Raw scraped headlines — Daily News
│   │   ├── citizen_raw.csv                # Raw scraped headlines — The Citizen
│   │   ├── usd_tzs_2022_2024.csv          # Daily FX from Investing.com
│   │   ├── tanzania_cpi_2022_2024.csv     # NBS Tanzania monthly CPI (extracted)
│   │   └── project_testing.csv            # Scratch file used during development
│   ├── processed/
│   │   ├── tz_headlines_clean.csv         # Merged and cleaned headlines
│   │   ├── tz_headlines_labelled.csv      # Classified headlines (classifier output)
│   │   ├── tz_headlines_test.csv          # Small sample used for classifier testing
│   │   ├── benchmarking_results.csv       # Multi-model benchmarking results
│   │   └── Visualization_Data.csv         # Final merged dataset
├── notebooks/
│   ├── 01_scraper.ipynb                   # Web scraper
│   ├── 02_cleaning.ipynb                  # Merges and cleans raw CSVs
│   ├── 03_benchmarking.ipynb              # Multi-model accuracy comparison
│   ├── 04_classifier.ipynb                # Production 3-in-1 classifier
│   ├── 05_consolidation.ipynb             # Data merging and aggregation
│   └── 06_visualisation.ipynb             # Analysis and charts
├── docs/
│   ├── 00_pipeline_overview.ipynb         # Index + pipeline map
│   ├── demo_scraper_logic.ipynb           # Scraper concepts + 1-page demo
│   ├── demo_llm_classifier.ipynb          # 3-in-1 LLM design + mini demo
│   ├── demo_benchmarking.ipynb            # Model comparison concepts
│   ├── demo_consolidation.ipynb           # Monthly merge walkthrough
│   └── demo_visualisation.ipynb           # Net Sentiment + correlation concepts
├── .env                                   # API keys (never committed to git)
├── .gitignore                             # Covers .env, data/raw/, and checkpoints
└── README.md                              # Project summary
```

**Naming convention:** Notebooks are prefixed with a two-digit number reflecting pipeline order. `data/raw/` contains source files that should never be modified. `data/processed/` contains all derived files.

---

## 7. Pre-Finalisation Checklist

Before the project is considered complete for submission or sharing:

- [x] Move all API keys to a `.env` file; load with `python-dotenv`; add `.env` to `.gitignore`
- [ ] Remove the `reason` column from `tz_headlines_labelled.csv` before production use
- [x] Rename notebooks to numbered pipeline order (`01_` through `06_`, all complete)
- [ ] Confirm all notebooks run top-to-bottom without errors on clean kernel
- [ ] Run the General category prompt fix and re-classify the General subset
- [ ] Manually audit a 20–30 headline sample of General and Neutral labels before re-running
- [ ] Verify December 2024 is present in both CPI and FX monthly outputs
- [x] Add a `README.md` with project summary, data sources, and how to run each notebook in order
- [ ] Confirm no raw API keys appear anywhere in committed notebook outputs (clear all outputs before committing)

---

## 8. Finalisation Roadmap

Five phases ordered by dependency — each phase unblocks the next.

### Phase 1 — Environment & Security
Move all API keys out of notebooks into a `.env` file. Set up `python-dotenv` loading at the top of each relevant notebook. Create `.gitignore` covering `.env`, `data/raw/`, and notebook outputs.

**Why first:** Every other phase involves running notebooks. Keys must be secured before anything is committed.

### Phase 2 — File & Folder Restructure
Create the `EF-02/` folder layout from Section 6. Rename and renumber all notebooks. Move raw data files into `data/raw/`, processed files into `data/processed/`. Update all hardcoded file paths inside notebooks to match the new structure.

**Why second:** Cleaner to fix data issues in correctly-named, correctly-placed files rather than cleaning a mess and then moving it.

### Phase 3 — Data Quality Fixes
**3a — General category audit:** Manually review a 25–30 headline sample from the ~913 General-labelled records. Measure how many clearly belong to a specific category. If 30%+, rewrite the prompt and re-run classification on just that subset.

**3b — Neutral sentiment review:** Pull a sample of Neutral headlines and check if any are obviously Positive/Negative. The tie-breaking prompt fix from Phase 3a may already help here.

**Why third:** Clean data before trusting visualisations. Charts in Phase 4 must reflect real findings.

### Phase 4 — Code Quality & Notebook Clean-up
Clear all outputs from every notebook and re-run top-to-bottom on a clean kernel. Remove the `reason` column from `tz_headlines_labelled.csv`. Remove dead/experimental cells. Add markdown headers and brief explanatory text between code cells.

### Phase 5 — Documentation & Final Review
Write `README.md` (project summary, data sources, how to run in order). Final pass to confirm no raw API keys appear in any committed notebook output. Verify December 2024 is present in both CPI and FX outputs. Tick off the full checklist from Section 7.

---

## 9. Progress Notes

### Phase 1 — Environment & Security
- [x] `.env` file created with all API keys
- [x] `python-dotenv` installed and loading confirmed in all relevant notebooks
- [x] `.gitignore` created covering `.env`, `data/raw/`, and notebook outputs
- **Notes:** Completed. Jupyter confirmed compatible with dotenv. Keys load via `os.getenv()`. `.gitignore` covers `.env`, `data/raw/`, CSV files, and `.ipynb_checkpoints/`.

### Phase 2 — File & Folder Restructure
- [x] Folder structure created locally
- [x] Notebooks being written clean and numbered from scratch (rebuild approach)
- [x] Data will populate naturally as each notebook runs in order
- **Notes:** Decided on clean rebuild rather than cleaning old notebooks. Paths baked in correctly from the start. A cleaning notebook (`02_cleaning.ipynb`) was added to the pipeline after scraping — this shifted all subsequent notebook numbers by one, making visualisation `06_` rather than `05_`. Phase considered complete by design.

### Notebook Build Progress
- [x] `01_scraper.ipynb` — complete. Scrapes Daily News and The Citizen (2022–2024). IPP Media excluded: archive only covers 2024 and category filter is Livewire-driven (URL-invisible). Per-source output CSVs: `dailynews_raw.csv`, `citizen_raw.csv`. Checkpoint every 30 pages. Live inline logging with end-of-run skipped/failed summary. Each source has a test cell and a full scrape cell.
- [x] `02_cleaning.ipynb` — complete. Merges `dailynews_raw.csv` and `citizen_raw.csv` into a single DataFrame. Parses and normalises dates, removes duplicates, drops malformed or empty rows. Output: `tz_headlines_clean.csv` in `data/processed/`.
- [x] `03_benchmarking.ipynb` — complete and confirmed running. Tests TextBlob, VADER, FinBERT, GPT-4o-mini, Llama 3.1 8b, Llama 3.3 70b. Outputs `benchmarking_results.csv` to `data/processed/`. Fixed system prompt mismatch (Negative definition was copy-pasted from Neutral in original). Groq accessed via OpenAI SDK with custom base URL.
- [x] `04_classifier.ipynb` — complete. Single-pass 3-in-1 classifier (relevance, category, sentiment) via Groq free tier (`llama-3.3-70b-versatile`). Batch size 25, temperature 0, max 3 retries. Output: `tz_headlines_labelled.csv` in `data/processed/`.
- [x] `05_consolidation.ipynb` — complete. Aggregates FX, CPI, and labelled headlines to monthly level. Merges on `YearMonth` key. Corrected file paths (`../data/raw/`, `../data/processed/`), removed redundant `.copy()`, fixed broken rename key, one `head()` per major step. Output: `Visualization_Data.csv` in `data/processed/`.
- [x] `06_visualisation.ipynb` — complete. Reads from both `tz_headlines_labelled.csv` and `Visualization_Data.csv`. Engineers `Net_Sentiment` feature on load. 8 sections: raw data summary (relevance split donut + category-over-time stacked bar), monthly overview, sentiment distribution (stacked bar + Net Sentiment bar), economic indicators, dual-axis sentiment vs economy pairs (Positive/Negative vs Inflation side-by-side, Positive/Negative vs USD/TZS side-by-side, Net Sentiment vs Rate_Change_%), Pearson correlation matrix heatmap, Pearson r and p-value table with significance flags, and a limitations markdown section.

### Phase 3 — Data Quality Fixes
- [ ] 3a: General category sample audit completed (target: 25–30 headlines)
- [ ] 3a: Mislabelling rate estimated; decision made on whether to re-run
- [ ] 3a: Prompt updated with tie-breaking rule (if re-run warranted)
- [ ] 3a: General subset re-classified
- [ ] 3b: Neutral sample reviewed
- [ ] 3b: Neutral prompt fix applied (if warranted)
- **Notes:**

### Phase 4 — Code Quality & Notebook Clean-up
- [ ] All notebook outputs cleared
- [ ] All notebooks run top-to-bottom clean on fresh kernel
- [ ] `reason` column removed from `tz_headlines_labelled.csv`
- [ ] Dead/experimental cells removed from all notebooks
- [x] Markdown headers and explanatory text — addressed via `docs/` documentation layer (pipeline notebooks stay execution-focused by design)
- **Notes:** Six documentation notebooks in `EF-02/docs/` provide the explanatory prose originally planned for a separate docs folder. Production notebooks (`01_`–`06_`) retain section headers only.

### Phase 5 — Documentation & Final Review
- [x] `README.md` written
- [x] `docs/` documentation notebooks created (`00_pipeline_overview` + five feature demos)
- [ ] Final check: no API keys in any committed notebook output
- [ ] December 2024 verified in CPI and FX outputs
- [ ] Full Section 7 checklist ticked off
- **Notes:** Documentation layer rebuilt June 2026. Each doc notebook maps to one production notebook and uses small runnable demos (1 scrape page, 3 LLM headlines, 10-row DataFrame slices) rather than re-running the full pipeline.
