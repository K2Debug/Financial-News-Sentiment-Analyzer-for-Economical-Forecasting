"""Classifier prompts — defaults from 04_classifier.ipynb."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

NOTEBOOK_SYSTEM_PROMPT = """You are a financial news classifier for Tanzania.
You return ONLY a valid JSON array. No preamble, no explanation, no markdown fences.
Every object in the array must be complete and the array must be properly closed with ]."""

NOTEBOOK_USER_PROMPT_TEMPLATE = """You classify Tanzanian financial headlines. Output ONLY a valid JSON array.

Schema: [{{"pos":1,"relevant":true,"category":"Forex","sentiment":"Positive"}}, ...]{reason_field}

STEP 0 — RELEVANCE:
relevant true → Tanzania economy, finance, business, trade, banking, currency, energy, agriculture
relevant false → sports, crime, entertainment, foreign-only news, opinion/lifestyle; if false set category/sentiment null

STEP 1 — pick ONE category:
Forex(shilling,dollar,reserves) | Policy(BOT,IMF,budget,tax,debt,GDP,NBS,rates) | Banking(banks,loans,fintech,insurance) | Trade(imports,exports,tariffs,ports,AfCFTA) | Agriculture(crops,farming,food) | Energy(TANESCO,fuel,power) | Transport(SGR,rail,roads,logistics) | Investment(FDI,factories,PPP,crowdfunding) | Markets(DSE,CMSA,equity,bonds,turnover) | Tourism(hotels,arrivals) | Inflation(CPI,food/cement price spikes)

Disambiguation: DSE/CMSA→Markets | BOT rate/GDP→Policy | food/cement price spike→Inflation | hotels→Tourism

STEP 2 — SENTIMENT (economic outcome not tone):
Positive=growth,profit up,shilling firms,easing inflation,launches | Negative=decline,loss,miss target,weakening,rising inflation | Neutral=steady,guidelines,reviews,no clear direction
Falling inflation=Positive. Rising inflation=Negative.

Headlines:
{headlines}"""


@dataclass
class ClassifierSettings:
    model: str = "gpt-4o-mini"
    batch_size: int = 25
    retry_batch_size: int = 10
    sleep_sec: float = 0.15
    system_prompt: str = field(default_factory=lambda: NOTEBOOK_SYSTEM_PROMPT)
    user_prompt_template: str = field(default_factory=lambda: NOTEBOOK_USER_PROMPT_TEMPLATE)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict | None) -> ClassifierSettings:
        if not data:
            return notebook_defaults()
        defaults = notebook_defaults()
        return cls(
            model=data.get("model", defaults.model),
            batch_size=int(data.get("batch_size", defaults.batch_size)),
            retry_batch_size=int(data.get("retry_batch_size", defaults.retry_batch_size)),
            sleep_sec=float(data.get("sleep_sec", defaults.sleep_sec)),
            system_prompt=data.get("system_prompt", defaults.system_prompt),
            user_prompt_template=data.get("user_prompt_template", defaults.user_prompt_template),
        )


def notebook_defaults() -> ClassifierSettings:
    return ClassifierSettings()


def build_user_prompt(batch: list[dict], settings: ClassifierSettings, include_reason: bool = False) -> str:
    lines = "\n".join(f"{i+1}. {item['headline']}" for i, item in enumerate(batch))
    reason_field = ""
    if include_reason:
        reason_field = '\nAdd "reason": 4-6 words explaining your decision (debugging only).'
    return settings.user_prompt_template.format(headlines=lines, reason_field=reason_field)
