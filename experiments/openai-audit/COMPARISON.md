# Groq vs OpenAI Pipeline Comparison

Generated after running `scripts/run_pipeline.py` on the shared `tz_headlines_clean.csv` input.

## Setup

| | Groq (`research/`) | OpenAI (`experiments/openai-audit/`) |
|---|---|---|
| Model | llama-3.1-8b-instant | gpt-4o-mini |
| Input | tz_headlines_clean.csv (6,235 rows) | same |
| Macro data | CPI + FX (36 months) | same |
| Output months | 36 (2022-01 – 2024-12) | 36 |

## Labeling differences

| Metric | Groq | OpenAI |
|--------|------|--------|
| Relevant headlines | 5,163 (82.8%) | 4,691 (75.2%) |
| Avg Positive % (monthly) | 45.2 | 81.1 |
| Avg Negative % (monthly) | 9.3 | 9.1 |
| Dominant top categories | Trade (16 mo), Policy (13) | Policy (11), Banking (10), Investment (9) |

## Label agreement (6,235 matched rows)

- Relevance agreement: **86.9%**
- Sentiment agreement: **57.8%** (jointly relevant only)
- Category agreement: **71.3%** (jointly relevant only)

## Correlations (36 monthly observations)

| Pair | Groq r | Groq p | OpenAI r | OpenAI p |
|------|--------|--------|----------|----------|
| Negative % vs USD/TZS | -0.293 | 0.083 | -0.435 | **0.008** |
| Net Sentiment vs USD/TZS | 0.254 | 0.135 | 0.438 | **0.008** |
| Positive % vs USD/TZS | 0.139 | 0.419 | 0.422 | **0.010** |
| Net Sentiment vs Inflation | -0.083 | 0.630 | -0.212 | 0.216 |

## Conclusion delta

- **Groq 8B on full 36 months:** no statistically significant sentiment–macro correlations.
- **GPT-4o-mini on same window:** three significant FX correlations (p ≤ 0.05), still no inflation link.
- The difference is driven mainly by **labeling behaviour** (stricter relevance filter, much higher positive share), not different macro inputs.
- Null Groq correlations are therefore **not proof of no relationship** — they may reflect classifier noise and aggregate sensitivity. Conversely, OpenAI significance should be treated cautiously given the positive-label skew and multiple comparisons across 12 pairs.

## How to re-run

```bash
# From experiments/openai-audit — delete outputs to force re-classification
rm data/processed/*.csv
python scripts/run_pipeline.py
```

Or run notebooks in order: `01_classifier.ipynb` → `02_consolidation.ipynb` → `03_visualisation.ipynb`.
