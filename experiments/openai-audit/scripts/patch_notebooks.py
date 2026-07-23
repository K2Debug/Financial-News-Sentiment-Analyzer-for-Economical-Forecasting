"""One-off script to adapt forked notebooks for OpenAI pipeline."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NB = ROOT / "notebooks"

CLEAN_IN = "../../research/data/processed/tz_headlines_clean.csv"
LABEL_OUT = "../data/processed/tz_headlines_labelled.csv"
TEST_OUT = "../data/processed/tz_headlines_test.csv"
VIZ_OUT = "../data/processed/Visualization_Data.csv"
CPI_IN = "../../research/data/raw/tanzania_cpi_2022_2024.csv"
FX_IN = "../../research/data/raw/usd_tzs_2022_2024.csv"
GROQ_LABEL = "../../research/data/processed/tz_headlines_labelled.csv"
GROQ_VIZ = "../../research/data/processed/Visualization_Data.csv"
ENV_PATH = "../../research/.env"


def patch_classifier():
    path = NB / "01_classifier.ipynb"
    nb = json.loads(path.read_text(encoding="utf-8"))

    title = {
        "cell_type": "markdown",
        "metadata": {},
        "source": [
            "# 01: Classifier (GPT-4o-mini)\n",
            "\n",
            "OpenAI parallel pipeline — classifies headlines from the shared clean dataset "
            "using `gpt-4o-mini`. Outputs are written locally under `experiments/openai-audit/data/processed/`."
        ],
    }
    nb["cells"].insert(0, title)

    setup = nb["cells"][2]["source"]
    setup = [
        "import pandas as pd\n",
        "import json\n",
        "import time\n",
        "import re\n",
        "from openai import OpenAI\n",
        "from dotenv import load_dotenv\n",
        "import os\n",
        "\n",
        f'load_dotenv("{ENV_PATH}")\n',
        "\n",
        'client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))\n',
        "\n",
        'MODEL = "gpt-4o-mini"\n',
        "BATCH_SIZE = 25\n",
        "SLEEP_SEC  = 0.15  # OpenAI paid tier — much faster than Groq free tier\n",
        "\n",
        "VALID_CATEGORIES = {\n",
        '    "Forex", "Policy", "Banking", "Trade",\n',
        '    "Agriculture", "Energy", "Transport", "Investment",\n',
        '    "Markets", "Tourism", "Inflation"\n',
        "}\n",
        'VALID_SENTIMENTS = {"Positive", "Negative", "Neutral"}',
    ]
    nb["cells"][2]["source"] = setup

  # classify_batch cell — add validation after pop pos
    classify_src = "".join(nb["cells"][5]["source"])
    old = "                result.pop('pos', None)\n"
    new = (
        "                result.pop('pos', None)\n"
        "                if result.get('relevant') is True:\n"
        "                    cat = result.get('category')\n"
        "                    sent = result.get('sentiment')\n"
        "                    if cat not in VALID_CATEGORIES:\n"
        "                        result['category'] = None\n"
        "                    if sent not in VALID_SENTIMENTS:\n"
        "                        result['sentiment'] = None\n"
    )
    if old in classify_src:
        classify_src = classify_src.replace(old, new)
        nb["cells"][5]["source"] = [classify_src]

    text = json.dumps(nb, ensure_ascii=False, indent=1)
    text = text.replace("../data/processed/tz_headlines_clean.csv", CLEAN_IN)
    text = text.replace("../data/processed/tz_headlines_labelled.csv", LABEL_OUT)
    text = text.replace("../data/processed/tz_headlines_test.csv", TEST_OUT)
    path.write_text(text, encoding="utf-8")
    print("Patched 01_classifier.ipynb")


def patch_consolidation():
    path = NB / "02_consolidation.ipynb"
    nb = json.loads(path.read_text(encoding="utf-8"))

    title = {
        "cell_type": "markdown",
        "metadata": {},
        "source": [
            "# 02: Consolidation (OpenAI pipeline)\n",
            "\n",
            "Aggregates GPT-4o-mini labelled headlines with shared CPI and FX data."
        ],
    }
    nb["cells"].insert(0, title)

    text = json.dumps(nb, ensure_ascii=False, indent=1)
    text = text.replace("../data/raw/usd_tzs_2022_2024.csv", FX_IN)
    text = text.replace("../data/raw/tanzania_cpi_2022_2024.csv", CPI_IN)
    text = text.replace("../data/processed/tz_headlines_labelled.csv", LABEL_OUT)
    text = text.replace("../data/processed/Visualization_Data.csv", VIZ_OUT)
    path.write_text(text, encoding="utf-8")
    print("Patched 02_consolidation.ipynb")


def patch_visualisation():
    path = NB / "03_visualisation.ipynb"
    nb = json.loads(path.read_text(encoding="utf-8"))

    # Update title cell
    nb["cells"][0]["source"] = [
        "# 03: Visualisation and Correlation Analysis (GPT-4o-mini)\n",
        "\n",
        "This notebook presents findings from the **OpenAI GPT-4o-mini** parallel pipeline. "
        "It reads classified headline data and the monthly aggregated dataset produced under "
        "`experiments/openai-audit/`, and compares results against the original Groq run in `research/`."
    ]

    # Patch setup cell paths
    setup_idx = 1
    for i, cell in enumerate(nb["cells"]):
        if cell["cell_type"] == "code" and "Visualization_Data.csv" in "".join(cell.get("source", [])):
            setup_idx = i
            break

    src = "".join(nb["cells"][setup_idx]["source"])
    src = src.replace(
        'pd.read_csv("../data/processed/Visualization_Data.csv")',
        f'pd.read_csv("{VIZ_OUT}")',
    )
    src = src.replace(
        'pd.read_csv("../data/processed/tz_headlines_labelled.csv")',
        f'pd.read_csv("{LABEL_OUT}")',
    )
    nb["cells"][setup_idx]["source"] = [src]

    comparison_md = {
        "cell_type": "markdown",
        "metadata": {},
        "source": [
            "## Section 10: Groq vs OpenAI Comparison\n",
            "\n",
            "Side-by-side comparison of the Groq (`llama-3.1-8b-instant`) production run "
            "and this GPT-4o-mini run on the same clean headline input."
        ],
    }
    comparison_code = {
        "cell_type": "code",
        "metadata": {},
        "source": [
            "from scipy import stats\n",
            "\n",
            f'groq_hdl = pd.read_csv("{GROQ_LABEL}")\n',
            f'groq_viz = pd.read_csv("{GROQ_VIZ}")\n',
            f'oai_hdl = pd.read_csv("{LABEL_OUT}")\n',
            f'oai_viz = pd.read_csv("{VIZ_OUT}")\n',
            "\n",
            "def pipeline_summary(name, hdl, viz):\n",
            "    rel = hdl[hdl['relevant'] == True]\n",
            "    print(f'\\n=== {name} ===')\n",
            "    print(f'  Total headlines : {len(hdl)}')\n",
            "    print(f'  Relevant        : {len(rel)} ({len(rel)/len(hdl)*100:.1f}%)')\n",
            "    print(f'  Monthly rows    : {len(viz)} ({viz[\"YearMonth\"].min()} to {viz[\"YearMonth\"].max()})')\n",
            "    print(f'  Avg Positive %  : {viz[\"Positive %\"].mean():.1f}')\n",
            "    print(f'  Avg Negative %  : {viz[\"Negative %\"].mean():.1f}')\n",
            "    top = viz['Top_Category'].value_counts().head(3)\n",
            "    print(f'  Top categories  : {dict(top)}')\n",
            "    pairs = [\n",
            "        ('Negative %', 'USD/TZS_Rate'),\n",
            "        ('Net_Sentiment', 'USD/TZS_Rate'),\n",
            "        ('Positive %', 'USD/TZS_Rate'),\n",
            "        ('Net_Sentiment', 'Inflation %'),\n",
            "    ]\n",
            "    viz = viz.copy()\n",
            "    viz['Net_Sentiment'] = viz['Positive %'] - viz['Negative %']\n",
            "    print('  Top correlations:')\n",
            "    for s, e in pairs:\n",
            "        r, p = stats.pearsonr(viz[s], viz[e])\n",
            "        print(f'    {s} vs {e}: r={r:.3f}, p={p:.4f}')\n",
            "\n",
            "pipeline_summary('Groq (llama-3.1-8b-instant)', groq_hdl, groq_viz)\n",
            "pipeline_summary('OpenAI (gpt-4o-mini)', oai_hdl, oai_viz)\n",
            "\n",
            "# Label agreement on same headlines\n",
            "merged = groq_hdl.merge(oai_hdl, on=['date', 'headline', 'url'], suffixes=('_groq', '_oai'))\n",
            "both_rel = merged[(merged['relevant_groq'] == True) & (merged['relevant_oai'] == True)]\n",
            "agree_rel = (merged['relevant_groq'] == merged['relevant_oai']).mean() * 100\n",
            "agree_sent = (both_rel['sentiment_groq'] == both_rel['sentiment_oai']).mean() * 100\n",
            "agree_cat = (both_rel['category_groq'] == both_rel['category_oai']).mean() * 100\n",
            "print(f'\\n=== Label agreement ({len(merged)} matched rows) ===')\n",
            "print(f'  Relevance agreement : {agree_rel:.1f}%')\n",
            "print(f'  Sentiment agreement : {agree_sent:.1f}% (relevant only)')\n",
            "print(f'  Category agreement  : {agree_cat:.1f}% (relevant only)')\n",
        ],
        "outputs": [],
        "execution_count": None,
    }
    comparison_obs = {
        "cell_type": "markdown",
        "metadata": {},
        "source": [
            "**Observation.** If both runs show non-significant correlations on the full 36-month window, "
            "the weak statistical signal is likely driven by monthly aggregation and sample size rather than "
            "classifier choice alone. Material differences in relevance rate or sentiment mix would indicate "
            "the model is shifting the monthly aggregates enough to change conclusions."
        ],
    }
    nb["cells"].extend([comparison_md, comparison_code, comparison_obs])

    path.write_text(json.dumps(nb, ensure_ascii=False, indent=1), encoding="utf-8")
    print("Patched 03_visualisation.ipynb")


if __name__ == "__main__":
    patch_classifier()
    patch_consolidation()
    patch_visualisation()
