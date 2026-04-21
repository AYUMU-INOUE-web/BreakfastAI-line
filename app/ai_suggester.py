"""AI による料理提案機能。

- 登録済み食材(または自由入力の食材名リスト)を Claude に渡し
  朝食で作れる簡単な料理の候補を JSON 配列で受け取る
- 返却された料理は Ingredient テーブルに「1品 = 1レコード」として
  登録できる形(name / category / unit / calories_per_unit 等)で返す
- 形の固定には「強制 Tool Use」を使う:
  `submit_dishes` という名前のツールを強制呼び出しさせ、その input を解釈する。
  output_config.format は新しい SDK にしか無いのでツール側を採用。
"""
from __future__ import annotations

import logging
from typing import Iterable, Sequence

import anthropic

from app.config import AI_MODEL, ANTHROPIC_API_KEY

logger = logging.getLogger(__name__)

VALID_CATEGORIES = ("main", "protein", "side", "drink")
MAX_SUGGESTIONS = 10

SYSTEM_PROMPT = (
    "あなたは朝食レシピに精通したアシスタントです。"
    "ユーザーが持っている食材リストから、現実的で簡単に作れる朝食の一品を提案します。"
    "各料理は 1 人分の分量・概算カロリー・単位を含め、"
    "カテゴリは main(主食)/protein(たんぱく)/side(副菜)/drink(飲み物) のいずれかに分類してください。"
    "使う食材はユーザーのリストから選ぶことを原則とし、"
    "ごく一般的な調味料や水・氷のみ追加で使って構いません。"
    "日本語で回答し、必ず submit_dishes ツールを呼び出して結果を返してください。"
)

# 強制呼び出し用ツールの input_schema
SUGGESTION_TOOL = {
    "name": "submit_dishes",
    "description": "ユーザーの食材から作れる朝食の料理候補を提出する。",
    "input_schema": {
        "type": "object",
        "properties": {
            "dishes": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "料理名(例: ゆで卵、しゃけ茶漬け)"},
                        "category": {"type": "string", "enum": list(VALID_CATEGORIES)},
                        "unit": {"type": "string", "description": "単位(例: 皿, 個, 杯, g, ml)"},
                        "calories_per_unit": {"type": "number", "description": "1単位あたりのおおよそのカロリー(kcal)"},
                        "default_portion": {"type": "number"},
                        "min_portion": {"type": "number"},
                        "max_portion": {"type": "number"},
                        "uses_ingredients": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "ユーザーリストから使う食材名の配列",
                        },
                        "description": {"type": "string", "description": "1〜2文の作り方メモ"},
                    },
                    "required": [
                        "name",
                        "category",
                        "unit",
                        "calories_per_unit",
                        "default_portion",
                        "min_portion",
                        "max_portion",
                        "uses_ingredients",
                        "description",
                    ],
                },
            }
        },
        "required": ["dishes"],
    },
}


def _build_user_prompt(ingredients: Sequence[str], n: int) -> str:
    listed = "\n".join(f"- {name}" for name in ingredients)
    return (
        f"次の食材を持っています:\n{listed}\n\n"
        f"この中から作れる、朝食向けの簡単な料理を {n} 案、重複しないように挙げてください。"
        "各料理はユーザーが毎日飽きずに食べられるよう、できるだけバラエティを持たせてください。"
        "結果は submit_dishes ツールの dishes 配列で返してください。"
    )


class AISuggesterUnavailableError(RuntimeError):
    """API キー未設定などで AI 機能が利用不可。"""


def is_available() -> bool:
    return bool(ANTHROPIC_API_KEY)


def suggest_dishes(ingredients: Iterable[str], n: int = 5) -> list[dict]:
    """料理候補を n 件返す。呼び出し側は JSON をそのまま UI/永続化に渡せる。"""
    if not ANTHROPIC_API_KEY:
        raise AISuggesterUnavailableError(
            "ANTHROPIC_API_KEY is not configured. Set it in the environment to enable AI suggestions."
        )
    names = [s for s in (raw.strip() for raw in ingredients) if s]
    if not names:
        return []
    n = max(1, min(MAX_SUGGESTIONS, int(n)))

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    response = client.messages.create(
        model=AI_MODEL,
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        tools=[SUGGESTION_TOOL],
        tool_choice={"type": "tool", "name": "submit_dishes"},
        messages=[{"role": "user", "content": _build_user_prompt(names, n)}],
    )

    tool_block = next(
        (b for b in response.content if getattr(b, "type", None) == "tool_use" and b.name == "submit_dishes"),
        None,
    )
    if tool_block is None:
        logger.warning("AI suggester returned no tool_use block (stop_reason=%s)", response.stop_reason)
        return []
    dishes = tool_block.input.get("dishes", []) if isinstance(tool_block.input, dict) else []

    cleaned: list[dict] = []
    for d in dishes:
        if not isinstance(d, dict):
            continue
        if d.get("category") not in VALID_CATEGORIES:
            continue
        if d.get("min_portion", 0) > d.get("max_portion", 0):
            d["min_portion"], d["max_portion"] = d["max_portion"], d["min_portion"]
        cleaned.append(d)
    return cleaned
