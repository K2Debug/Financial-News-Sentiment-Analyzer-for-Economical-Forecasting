MODEL = "gpt-4o-mini"
BATCH_SIZE = 25
RETRY_BATCH_SIZE = 10
SLEEP_SEC = 0.15

VALID_CATEGORIES = {
    "Forex", "Policy", "Banking", "Trade",
    "Agriculture", "Energy", "Transport", "Investment",
    "Markets", "Tourism", "Inflation",
}
VALID_SENTIMENTS = {"Positive", "Negative", "Neutral"}

SYSTEM_PROMPT = """You are a financial news classifier for Tanzania.
You return ONLY a valid JSON array. No preamble, no explanation, no markdown fences.
Every object in the array must be complete and the array must be properly closed with ]."""
