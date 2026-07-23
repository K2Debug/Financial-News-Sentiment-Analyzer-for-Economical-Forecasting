# EF-02 Decision Log
**Project:** Tanzania Financial News Sentiment Analyser  
**Programme:** BSc Data Science and AI, Ardhi University  
**Author:** K2 | Group 8

This document is a living record of key decisions made across all working sessions. It is provided at the start of each new session so context is never lost. Each session adds one section. Keep entries concise — decisions and reasoning only, not implementation detail.

---

## Session 01 — Project Finalisation Setup & Benchmarking Notebook

**Focus:** Finalisation roadmap, environment security, and rebuilding the benchmarking notebook clean.

### Decision: Rebuild notebooks from scratch rather than clean existing ones
The original notebooks were scattered across multiple files with inconsistent naming, exposed API keys, dead cells, and no clear pipeline order. Rather than patching them, the decision was made to rebuild each notebook clean in numbered order (`01_` through `05_`). This produces more readable, reproducible work and avoids carrying forward structural debt.

### Decision: Secure API keys via `.env` before anything else
All API keys were moved out of notebooks into a `.env` file loaded via `python-dotenv`. This was prioritised above all other work because any notebook run before this fix risked committing a live key. `.gitignore` was set up to cover `.env`, raw data files, and notebook checkpoints.

### Decision: TextBlob and VADER rejected early — not suitable for financial domain
Both are rule-based models built on general English vocabulary. TextBlob scored ~28% and VADER ~50% on the synthetic dataset. Neither understands financial or East African economic language. Retained in the benchmarking notebook for documentation purposes but not considered for production.

### Decision: FinBERT rejected despite financial domain training
FinBERT was trained on Western financial text (earnings calls, analyst reports) and scored ~67%. It struggles with Tanzanian and East African economic phrasing. Accuracy was not sufficient for production use, though it represented a meaningful improvement over rule-based models.

### Decision: LLM-based classification chosen for production — Groq free tier via Llama 3.3 70b
LLMs (GPT-4o-mini, Llama 3.1 8b, Llama 3.3 70b) all scored ~92% on the synthetic dataset. Groq's free tier provides sufficient throughput for the project's scale. Llama 3.3 70b on Groq was selected for the production classifier as it matches GPT-4o-mini accuracy at no cost.

### Decision: Classify by implied economic outcome, not emotional tone
The system prompt was designed to classify headlines by their likely economic effect — growth, contraction, stability — rather than the surface sentiment of the language used. This is more meaningful for correlation with macroeconomic indicators and reduces misclassification of neutral-sounding but economically significant headlines.

### Decision: Fixed system prompt mismatch from original notebooks
The original `gpt_notebook.ipynb` had a copy-paste error where the Negative label definition was identical to the Neutral definition. This was corrected in `02_benchmarking.ipynb` using the accurate definition from `v2_sentiment_analyser.ipynb`. All LLM models in the benchmarking notebook now use a single consistent corrected prompt.

### Decision: Groq accessed via OpenAI SDK with custom base URL
Rather than importing both the `openai` and `groq` packages separately, Groq's API is accessed through the OpenAI SDK pointed at Groq's base URL. This keeps the codebase consistent and reduces dependencies.

### Outcome
- Phase 1 (environment security) complete
- Phase 2 (folder restructure) complete by design — clean rebuild approach
- `02_benchmarking.ipynb` built, confirmed running end-to-end

---

## Session 02 — Scraper Notebook Rebuild

**Focus:** Rebuilding `01_scraper.ipynb` clean from scratch as an execution-only notebook.

### Decision: Execution-only notebook with section markdown only
`01_scraper.ipynb` contains no explanatory prose. Section headers (`## Daily News`, `## The Citizen`) are included for navigation. All conceptual documentation goes in `docs/demo_scraper_logic.ipynb`.

### Decision: Per-source self-contained cells
Each source has two cells: a config + test cell (3–5 pages, prints sample headlines) and a full scrape cell. All selectors, URL pattern, and base domain live in the config dict in the same cell as the call — no scrolling to a master config at the top.

### Decision: Separate output CSVs per source
Each source writes to its own file (`dailynews_raw.csv`, `citizen_raw.csv`) rather than a shared output. Merging across sources is deferred to `04_consolidation.ipynb`.

### Decision: Checkpoint every 30 pages
Previous scraper checkpointed every 20–50 pages. Given Tanzanian internet instability and the volume of pages to scrape across two sources, 30 was chosen as the balance between safety and checkpoint file churn.

### Decision: Live inline logging with end-of-run error summary
Successful pages overwrite a single terminal line between checkpoints using `end="\r"`. At each checkpoint the line is permanently printed and reset. Skipped pages (no articles) and failed pages (connection errors) accumulate silently across the entire run and print once as a summary at the end — they do not interrupt the live feed.

### Decision: IPP Media excluded from the scraper
Two blockers ruled out IPP Media / The Guardian Tanzania: (1) their search archive only has records from 2024, not the full 2022–2024 range required; (2) their category filter is a Livewire component that filters dynamically without modifying the URL, making it inaccessible to a `requests`-based scraper without a headless browser. Adding one year of data from a third source would also skew monthly headline counts and introduce an asymmetry into the sentiment–economic correlation analysis. Daily News and The Citizen together cover the full 2022–2024 range.

### Outcome
- `01_scraper.ipynb` complete: Daily News and The Citizen, test + full scrape cells per source, checkpoint every 30 pages, live logging
- `EF02_Architecture_and_Restructuring_Plan.md` updated to reflect new scraper design and IPP Media exclusion rationale

---

## Session 03 — Consolidation Notebook Rebuild & Architecture Plan Update

**Focus:** Rebuilding `05_consolidation.ipynb` clean, and updating the architecture plan to reflect the actual on-disk project state.

### Decision: Light tidy rather than full overhaul for consolidation notebook
The original `data_consolidation.ipynb` had sound logic and a clean step structure. A full rebuild was not warranted. Instead, targeted fixes were applied: corrected file paths, removed a redundant `.copy()`, fixed a broken rename key, and kept one `head()` per major step.

### Decision: File paths corrected to `../data/raw/` and `../data/processed/`
The original notebook used flat paths (`data/filename.csv`). All paths updated to the correct relative paths per the architecture plan. FX source file (`usd_tzs_2022_2024.csv`) reads from `../data/raw/`; CPI and labelled headlines read from `../data/processed/`.

### Decision: Redundant `.copy()` removed
A `.copy()` call mid-processing in the headlines step was dropped. The DataFrame had just been created from a column slice, which already returns a copy in modern pandas. The call served no purpose.

### Decision: Broken rename key removed from merge step
The original notebook dropped `all_items_index` from the CPI DataFrame in Step 2 but then included it as a key in the rename dict in the merge step, where it would silently do nothing. The broken key was removed; the rename dict now only references columns that are actually present.

### Decision: `02_cleaning.ipynb` documented — pipeline renumbered
A cleaning notebook existed on disk but was not reflected in the architecture plan. It merges `dailynews_raw.csv` and `citizen_raw.csv`, normalises dates, removes duplicates, and outputs `tz_headlines_clean.csv`. Its addition shifted all subsequent notebook numbers by one: benchmarking is now `03_`, classifier `04_`, consolidation `05_`, and visualisation will be `06_`.

### Decision: `docs/` folder dropped from architecture plan
The planned `docs/` demo notebook folder does not exist on disk and was not built during the rebuild. It was removed from the project structure in the architecture plan to keep the document accurate.

### Decision: Architecture plan updated to reflect actual on-disk state
Section 6 (project structure), Section 4 (component breakdown), the notebook build progress log, and the pre-finalisation checklist were all updated to match the real file layout — including files present on disk that were not in the original plan (`project_testing.csv`, `tz_headlines_test.csv`, `tz_headlines_clean.csv`).

### Outcome
- `05_consolidation.ipynb` rebuilt and complete
- `EF02_Architecture_and_Restructuring_Plan.md` updated: pipeline renumbered, cleaning notebook documented, file structure corrected, docs folder removed, checklist and progress notes brought up to date
- Five of six notebooks now complete; `06_visualisation.ipynb` is the remaining build task

---

## Session 04 — Visualisation Notebook Build

**Focus:** Designing and building `06_visualisation.ipynb` from scratch.

### Decision: Read from both labelled CSV and aggregated CSV
The visualisation notebook reads from `tz_headlines_labelled.csv` (unaggregated) in addition to `Visualization_Data.csv` (monthly aggregates). This allows a raw data summary section that shows information never repeated in the aggregated analysis — specifically the relevance split and the category-over-time distribution at the headline level.

### Decision: Include a raw data summary section before monthly aggregates
A Section 2 was added to summarise the unaggregated headline data. The argument against repetition was rejected: the visualisation notebook should be readable as a standalone document by an examiner who has not opened any other notebook. Two charts were chosen that are genuinely non-redundant with later sections: a relevance split donut (never shown elsewhere) and a stacked bar of category share over time at the headline level (distinct from the monthly-aggregate category chart that follows).

### Decision: Model benchmarking results not included
Model performance figures belong in `03_benchmarking.ipynb`, which is concerned with methodology. The visualisation notebook's purpose is to present findings from the data, not justify how the data was produced. Including benchmarking results here would conflate methodology with analysis.

### Decision: Net Sentiment engineered as a new column on load
`Net_Sentiment = Positive % − Negative %` is computed at the top of the notebook from the aggregated data. It serves as a single directional signal compressing two noisy series and is used both as a standalone chart and as the left axis in the Rate_Change_% dual-axis chart. This is the most useful pairing for FX volatility because Rate_Change_% is a month-on-month delta (more volatile and economically meaningful than the rate level), which pairs naturally with the net directional sentiment rather than either polarity in isolation.

### Decision: Positive and Negative dual-axis charts shown as side-by-side pairs
Rather than separate figures for Positive vs Inflation and Negative vs Inflation, each economic indicator gets a side-by-side figure with both polarities. This makes comparison immediate without scrolling and keeps the notebook compact. Four dual-axis charts become two figures.

### Decision: Correlation analysis includes both heatmap and Pearson r table
The heatmap gives a visual overview of the full correlation structure across all numeric variables. The Pearson r table provides exact r values and p-values for sentiment vs economic variable pairs specifically, with significance flags (* p<0.05, ** p<0.01, *** p<0.001). Both are necessary: the heatmap is the accessible overview, the table is the academically precise output.

### Decision: Classifier downgrade documented as a limitation
The production classifier used `llama-3.1-8b-instant` rather than the benchmarked `llama-3.3-70b-versatile` due to token limit constraints encountered during the full classification run. This is documented in Section 8 (Limitations) of the visualisation notebook as a known quality concern, with a note that a re-run with the 70B model is planned.

### Decision: No printed DataFrames — all information conveyed through charts or markdown
The visualisation notebook is intended for an audience that should be able to understand findings without effort. Printed DataFrames (other than the Pearson r table, which is a results table rather than raw data display) are avoided. The raw data summary is shown entirely through charts.

### Outcome
- `06_visualisation.ipynb` complete. All six pipeline notebooks are now built.
- `EF02_Architecture_and_Restructuring_Plan.md` updated: Section 4.6 rewritten to reflect the actual 8-section notebook structure; notebook build progress log updated to mark `06_visualisation.ipynb` complete; checklist updated.

---

## Session 05 — Prompt Tuning for Llama 3.1 8b Classifier

**Focus:** Recover classification quality on `llama-3.1-8b-instant` after downgrade from 70b, without exceeding Groq free-tier token limits.

### Decision: Iterative prompt evaluation against `project_testing.csv`
Built `scripts/prompt_eval.py` to batch-classify a labelled sample and score category accuracy (mapped to the 9 production categories), sentiment accuracy, General overuse rate, and Neutral bias. Tested four prompt variants on 100- and 200-headline samples before updating the production notebook.

### Decision: Two-step prompt structure with disambiguation rules and few-shot examples
The winning prompt (v4) replaces the long prose category list with a compact STEP 1 (category) / STEP 2 (sentiment) structure. Key additions: explicit inflation/CPI/GDP → Policy rule, DSE/CMSA → Investment, anti-General guidance (<5%), and worked examples for common failure modes. This targets the three observed 8b failure modes: General overuse, Neutral defaulting, and wrong category on clear headlines.

### Decision: v4 prompt adopted in `04_classifier.ipynb`
On 200-headline sample vs current prompt: category accuracy 59.6% → 79.9%, sentiment accuracy 77.7% → 86.9%, General rate 15.5% → 5.5%, Neutral rate 37.3% → 25.1%. Production re-run with v4 prompt recommended before final submission.

### Outcome
- `scripts/prompt_eval.py` created for repeatable prompt benchmarking
- `04_classifier.ipynb` prompt updated to v4
- Full dataset re-classification pending user decision (uses ~213 batches, fits within daily token limit on 8b)

---

## Session 06 — v5 Schema, TPM Rate Limiting, Relevance Fix

**Focus:** Adopt 11-category schema (drop General), restore relevance rules, pace Groq requests under 6K TPM.

### Decision: 11 categories — add Markets, Tourism, Inflation; remove General
General was absorbing 15–23% of real scrape headlines (DSE, tourism, crowdfunding). Adding explicit buckets targets the root cause rather than prompt warnings alone.

### Decision: GroqRateLimiter for 6,000 TPM / 30 RPM free-tier caps
Fixed `SLEEP_SEC = 1.5` exceeds RPM but blows through TPM (~1,800 tokens/request → ~3 batches/min max). `scripts/groq_rate_limit.py` tracks rolling 60s token usage and enforces 2.1s minimum between requests. Full production run estimated at 75–90 minutes.

### Decision: BATCH_SIZE 20, max_tokens 3000
Reduces JSON truncation failures that caused 400 failed batches in the prior run. Retry cell keeps batch size 10.

### Outcome
- Reverted to simple classifier pacing per architecture plan: `BATCH_SIZE=10`, `SLEEP_SEC=1.5`, `max_tokens=2500`, 3 retries
- Removed `groq_rate_limit.py` and TPM timer logic from notebook
- Kept compact v5 prompt and 11-category schema (Markets, Tourism, Inflation; no General)
