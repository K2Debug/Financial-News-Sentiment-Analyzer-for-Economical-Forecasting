"""Update 03_visualisation.ipynb markdown with OpenAI pipeline results."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
path = ROOT / "notebooks" / "03_visualisation.ipynb"
nb = json.loads(path.read_text(encoding="utf-8"))

# Find markdown cells by content prefix and update
updates = {
    "Of the 6,235 scraped headlines": (
        "Of the 6,235 scraped headlines, 4,691 (75.2%) were classified as economically relevant "
        "to Tanzania and carried forward for analysis. The remaining 24.8% were filtered out as outside scope."
    ),
    "Before examining monthly aggregates": (
        "Before examining monthly aggregates, this section looks at the unaggregated classified headline data. "
        "The GPT-4o-mini classifier processed 6,235 headlines collected from Daily News and The Citizen "
        "across 2022–2024. Each headline was assessed for relevance, assigned a category, and given a sentiment label."
    ),
    "**Observation.** Monthly headline volume fluctuates": (
        "**Observation.** Monthly headline volume fluctuates around a mean of roughly 130 relevant headlines per month "
        "(lower than the Groq run due to stricter relevance filtering). Policy and Banking are the most frequent "
        "dominant categories month-to-month."
    ),
    "Neutral and Positive sentiment are closely balanced": (
        "Positive sentiment dominates across most months (averaging ~81% of relevant headlines), with Neutral and "
        "Negative shares much smaller. The Net Sentiment Index remains positive in every month. Compared to the Groq "
        "run, GPT-4o-mini labels headlines substantially more positively."
    ),
    "**Observation.** With the full 36-month dataset, no sentiment": (
        "**Observation.** On the full 36-month window, correlations cluster around the USD/TZS rate level and reach "
        "conventional significance: **Negative % vs USD/TZS Rate** (r=-0.435, p=0.008) and **Net Sentiment vs USD/TZS Rate** "
        "(r=0.438, p=0.008). Inflation pairs remain non-significant."
    ),
}

for cell in nb["cells"]:
    if cell["cell_type"] != "markdown":
        continue
    text = "".join(cell["source"])
    for prefix, replacement in updates.items():
        if prefix in text:
            cell["source"] = [replacement]

# Replace Section 8 conclusions entirely
for i, cell in enumerate(nb["cells"]):
    if cell["cell_type"] == "markdown" and "## Section 8: Conclusions" in "".join(cell["source"]):
        nb["cells"][i]["source"] = [
            "## Section 8: Conclusions\n",
            "\n",
            "This analysis tested whether Tanzanian financial news sentiment correlates with macroeconomic movement "
            "at the monthly level using **GPT-4o-mini** labels. Across **36 months (January 2022 to December 2024)**, "
            "sentiment correlates **significantly with the USD/TZS exchange rate** but not with inflation.\n",
            "\n",
            "### Statistical significance\n",
            "\n",
            "Note: *r* = correlation coefficient; *p* = p-value\n",
            "\n",
            "- **Highly significant (p ≤ 0.01):**\n",
            "  - **Net Sentiment vs USD/TZS Rate** (r=0.438, p=0.008)\n",
            "  - **Negative % vs USD/TZS Rate** (r=-0.435, p=0.008)\n",
            "- **Significant at 5% (p ≤ 0.05):**\n",
            "  - **Positive % vs USD/TZS Rate** (r=0.422, p=0.010)\n",
            "- **Not significant:** all inflation and rate-change pairs (e.g. Net Sentiment vs Inflation %: r=-0.212, p=0.216)\n",
            "\n",
            "### Interpretation\n",
            "\n",
            "Unlike the Groq 8B run on the same headlines, GPT-4o-mini produces a **statistically significant concurrent link** "
            "between net sentiment and TZS depreciation. The model also filters fewer headlines as relevant (75.2% vs 82.8%) "
            "and assigns far higher positive shares (~81% vs ~45%), which materially shifts monthly aggregates.\n",
            "\n",
            "Inflation shows no meaningful association with sentiment under either model on the full 36-month window. "
            "The exchange-rate result should be interpreted as **concurrent co-movement**, not a leading indicator.\n",
            "\n",
            "See Section 10 for a direct Groq vs OpenAI comparison.\n",
        ]
        break

# Update Section 9 limitations - coverage note
for i, cell in enumerate(nb["cells"]):
    if cell["cell_type"] == "markdown" and "## Section 9: Limitations" in "".join(cell["source"]):
        src = "".join(cell["source"])
        src = src.replace(
            "**Coverage.** The consolidated dataset now spans all 36 months from January 2022 through December 2024, following the relabeled headline set and the addition of December 2024 CPI data.",
            "**Coverage.** This run uses the full 36-month window (Jan 2022 – Dec 2024) with shared CPI/FX data from `EF-02/`. Labels are produced by GPT-4o-mini and stored separately under `EF-02-openai/data/processed/`.",
        )
        src = src.replace(
            "**Sentiment balance.** Neutral and Positive sentiment are closely matched",
            "**Sentiment balance.** GPT-4o-mini assigns a much higher positive share than Groq 8B (~81% vs ~45% avg Positive %). This compresses neutral/negative signal and may inflate correlation magnitudes. The Groq run showed no significant correlations on the same 36-month window",
        )
        nb["cells"][i]["source"] = [src]
        break

# Update Section 10 observation with actual numbers
for i, cell in enumerate(nb["cells"]):
    if cell["cell_type"] == "markdown" and "Section 10: Groq vs OpenAI" in "".join(cell.get("source", [])):
        continue
    if cell["cell_type"] == "markdown" and "**Observation.** If both runs show non-significant" in "".join(cell.get("source", [])):
        nb["cells"][i]["source"] = [
            "**Observation.** On the same 36-month window, Groq 8B yields **no significant** sentiment–FX correlations "
            "(best: Negative % vs FX, r=-0.293, p=0.083), while GPT-4o-mini yields **two significant** FX pairs "
            "(|r|≈0.44, p<0.01). Relevance agreement is 86.9% but sentiment agreement is only 57.8% on jointly relevant "
            "headlines — classifier choice materially changes monthly sentiment aggregates and therefore conclusions."
        ]
        break

path.write_text(json.dumps(nb, ensure_ascii=False, indent=1), encoding="utf-8")
print("Updated 03_visualisation.ipynb conclusions")
