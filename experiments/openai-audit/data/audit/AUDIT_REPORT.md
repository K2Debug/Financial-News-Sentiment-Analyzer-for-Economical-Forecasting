# Label Reliability Audit Report

Groq (`llama-3.1-8b-instant`) vs OpenAI (`gpt-4o-mini`) on shared `tz_headlines_clean.csv` input.

## 1. Data quality scorecard

| Metric | Groq | OpenAI |
|--------|------|--------|
| Relevant rows | 5163 (82.8%) | 4691 (75.2%) |
| Relevant + null sentiment | **428** | 13 |
| Relevant + null category | 0 | **81** |
| Positive % of relevant | 42.0% | **82.2%** |
| Neutral % of relevant | 41.9% | 9.6% |
| Positive-bias alarm (>70%) | False | True |

**Groq anomaly:** 428 relevant headlines lack sentiment — likely incomplete retry after relabeling. These distort monthly sentiment aggregates until fixed.

**OpenAI anomaly:** 81 relevant rows lost category after schema enforcement; 82.2% positive rate vs Groq's 42.0% suggests systematic positive upgrading.

## 2. Disagreement anatomy

| Bucket | Count |
|--------|-------|
| Groq relevant only | 644 |
| OpenAI relevant only | 172 |
| Neutral → Positive | 1409 |
| Negative → Positive | 25 |
| Groq null → OpenAI Positive | 264 |
| Category disagree (both relevant) | 1299 |
| Full agreement (rel + cat + sent) | 1925 |

Manual review sample: `disagreement_review_sample.csv` (~100 stratified rows).

## 3. Gold-set 3-in-1 evaluation (`project_testing.csv`)

| Metric | Groq | OpenAI |
|--------|------|--------|
| Relevance accuracy | 0.9901 | 0.9524 |
| Sentiment accuracy | 0.8679 | 0.8954 |
| Category accuracy | 0.7862 | 0.8138 |
| Strict 3-in-1 accuracy | 0.6939 | 0.728 |
| Pred positive % | 43.6% | 57.7% |

## 4. Correlation robustness (36 months)

### Groq monthly data
- Negative % vs USD/TZS_Rate: r=-0.293, p=0.0831
- Net_Sentiment vs USD/TZS_Rate: r=0.254, p=0.1348
- Positive % vs USD/TZS_Rate: r=0.139, p=0.4185
- Net_Sentiment vs Inflation %: r=-0.083, p=0.6304

### OpenAI monthly data
- Negative % vs USD/TZS_Rate: r=-0.435, p=0.008 *
- Net_Sentiment vs USD/TZS_Rate: r=0.438, p=0.0076 *
- Positive % vs USD/TZS_Rate: r=0.422, p=0.0104 *
- Net_Sentiment vs Inflation %: r=-0.211, p=0.2158

### Agreement-only labels (both models agree on relevance + sentiment)
- Negative % vs USD/TZS_Rate: r=-0.409, p=0.0133 *
- Net_Sentiment vs USD/TZS_Rate: r=0.386, p=0.02 *
- Positive % vs USD/TZS_Rate: r=0.324, p=0.0537
- Net_Sentiment vs Inflation %: r=-0.16, p=0.352

## 5. Production recommendation rubric

| Criterion | Weight | Groq | OpenAI |
|-----------|--------|------|--------|
| Schema completeness | High | Poor (428 null sentiments) | Moderate (81 null categories) |
| Sentiment plausibility | High | Good (~42.0% positive) | Poor (82.2% positive) |
| Gold 3-in-1 accuracy | High | 0.6939 | 0.728 |
| FX correlation stability | Medium | Not significant | 3 significant pairs (suspect) |
| Agreement-only FX signal | Medium | — | 2 significant pairs |

## 6. Recommendation

**Do not switch production to GPT-4o-mini based on FX correlations alone.** OpenAI significance (3 pairs) likely reflects positive-label inflation (1409 Neutral→Positive flips), not a truer economic signal.

**Short-term production path:**
1. **Fix Groq** — re-run retry in `EF-02/notebooks/04_classifier.ipynb` Section 5 to clear 428 null sentiments, then re-consolidate.
2. **Keep Groq as production classifier** unless gold eval shows OpenAI clearly wins strict 3-in-1 accuracy AND manual review favours its labels.
3. **Report framing** — present OpenAI run as sensitivity analysis; note that agreement-only consolidation still shows significant FX correlations, indicating some shared signal.

Fill `your_*` columns in `disagreement_review_sample.csv` and re-run the scoring cell in `04_label_audit.ipynb` to refine this recommendation with human agreement rates.
