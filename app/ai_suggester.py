"""AI による朝食献立の生成。

- 登録済みの素材(食材)と プロファイル(目標カロリー)を Claude に渡す
- Claude は `submit_menu` ツールを強制呼び出しで返す
- 返却を `GeneratedMenu` に変換する
- 生成が失敗した場合は None を返し、呼び出し側でルールベースにフォールバック

  素材: 卵、しゃけ、梅干し、ごはん … → AI → 料理: しゃけ茶漬け、ゆで卵、味噌汁 …
"""
from __future__ import annotations

import logging
from dataclasses import asdict
from typing import Optional, Sequence

import anthropic
from sqlalchemy.orm import Session

from app.config import AI_MODEL, ANTHROPIC_API_KEY
from app.menu_generator import (
    GeneratedMenu,
    MenuItem,
    MenuProfile,
)
from app.models import Ingredient

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "あなたは家庭の朝食を得意とする料理アシスタントです。"
    "ユーザーが持っている素材(食材)から、現実的に作れる朝食の献立を組み立てます。"
    "出力は必ず submit_menu ツールで返してください。"
    "・料理は日本の家庭で毎朝作るような、現実的で簡単なものに限る\n"
    "・各料理は 1 人分の分量・概算カロリーを含める\n"
    "・ごく一般的な調味料(塩、しょうゆ、砂糖、油など)は、素材に載っていなくても使ってよい\n"
    "・料理の合計カロリーが、指定されたターゲットの許容範囲に収まるようにする\n"
    "・1 献立は 2〜5 品で構成し、主食・主菜・副菜・飲み物がバランスよく入るとよい\n"
    "・直近で提供した献立と同じ構成にならないようにする\n"
    "・すべて日本語で記述する"
)

MENU_TOOL = {
    "name": "submit_menu",
    "description": "ユーザー向けの朝食献立を提出する。",
    "input_schema": {
        "type": "object",
        "properties": {
            "menu_name": {
                "type": "string",
                "description": "献立全体の名前(例: しゃけ茶漬け中心の和朝食)",
            },
            "dishes": {
                "type": "array",
                "minItems": 1,
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "料理名(例: しゃけ茶漬け)"},
                        "portion": {"type": "number", "description": "1 人分の分量(数値)"},
                        "unit": {"type": "string", "description": "料理の単位(例: 杯, 皿, 個)"},
                        "calories": {"type": "number", "description": "1 人分の概算カロリー(kcal)"},
                        "ingredients_used": {
                            "type": "array",
                            "description": "この料理で使う素材の一覧",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "name": {"type": "string"},
                                    "portion": {"type": "number"},
                                    "unit": {"type": "string"},
                                },
                                "required": ["name", "portion", "unit"],
                            },
                        },
                        "description": {"type": "string", "description": "1〜2 文の作り方メモ"},
                    },
                    "required": [
                        "name",
                        "portion",
                        "unit",
                        "calories",
                        "ingredients_used",
                        "description",
                    ],
                },
            },
        },
        "required": ["menu_name", "dishes"],
    },
}


class AISuggesterUnavailableError(RuntimeError):
    """API キー未設定などで AI 機能が利用不可。"""


def is_available() -> bool:
    return bool(ANTHROPIC_API_KEY)


def _format_ingredients(ingredients: Sequence[Ingredient]) -> str:
    lines = []
    for ing in ingredients:
        cat = {
            "main": "主食",
            "protein": "たんぱく",
            "side": "副菜",
            "drink": "飲み物",
        }.get(ing.category, ing.category)
        lines.append(
            f"- {ing.name}: 1{ing.unit} あたり {ing.calories_per_unit:g} kcal"
            f" / 目安 {ing.default_portion:g}{ing.unit}"
            f" / 範囲 {ing.min_portion:g}〜{ing.max_portion:g}{ing.unit}"
            f" / カテゴリ {cat}"
        )
    return "\n".join(lines)


def _format_exclusions(exclude_signatures: Optional[set[tuple]]) -> str:
    if not exclude_signatures:
        return "(なし)"
    out = []
    for sig in exclude_signatures:
        names = " + ".join(name for name, _ in sig)
        if names:
            out.append(f"- {names}")
    return "\n".join(out) if out else "(なし)"


def _build_user_prompt(
    profile: MenuProfile,
    ingredients: Sequence[Ingredient],
    exclude_signatures: Optional[set[tuple]],
) -> str:
    return (
        f"## 使える素材\n{_format_ingredients(ingredients)}\n\n"
        f"## ターゲット\n"
        f"合計 {profile.target} kcal(許容範囲 {profile.cal_min}〜{profile.cal_max} kcal)\n"
        f"プロファイル: {profile.name}\n\n"
        f"## 避けたい直近献立\n{_format_exclusions(exclude_signatures)}\n\n"
        f"上の素材から作れる朝食の献立を組み立ててください。"
        f"submit_menu ツールで献立名と料理の配列を返してください。"
    )


def generate_ai_menu(
    session: Session,
    profile: MenuProfile,
    exclude_signatures: Optional[set[tuple]] = None,
) -> Optional[GeneratedMenu]:
    """登録済みの素材から AI に 1 プロファイル分の献立を組み立ててもらう。

    成功: GeneratedMenu を返す
    失敗: None(API 未設定、API エラー、構造不正時)
    """
    if not ANTHROPIC_API_KEY:
        return None
    ingredients = (
        session.query(Ingredient).filter(Ingredient.active.is_(True)).all()
    )
    if not ingredients:
        return None

    try:
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        response = client.messages.create(
            model=AI_MODEL,
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            tools=[MENU_TOOL],
            tool_choice={"type": "tool", "name": "submit_menu"},
            messages=[
                {
                    "role": "user",
                    "content": _build_user_prompt(
                        profile, ingredients, exclude_signatures
                    ),
                }
            ],
        )
    except Exception:  # noqa: BLE001
        logger.exception("AI menu generation failed for profile %s", profile.name)
        return None

    tool_block = next(
        (
            b
            for b in response.content
            if getattr(b, "type", None) == "tool_use"
            and getattr(b, "name", None) == "submit_menu"
        ),
        None,
    )
    if tool_block is None or not isinstance(tool_block.input, dict):
        logger.warning(
            "AI returned no submit_menu tool_use (stop_reason=%s)",
            getattr(response, "stop_reason", None),
        )
        return None

    payload = tool_block.input
    raw_dishes = payload.get("dishes")
    if not isinstance(raw_dishes, list) or not raw_dishes:
        logger.warning("AI returned empty dishes list")
        return None

    # 素材名 → Ingredient の逆引き
    by_name = {i.name: i for i in ingredients}

    items: list[MenuItem] = []
    for d in raw_dishes:
        if not isinstance(d, dict):
            continue
        name = str(d.get("name") or "").strip()
        portion = float(d.get("portion", 0) or 0)
        unit = str(d.get("unit") or "").strip()
        calories = float(d.get("calories", 0) or 0)
        description = str(d.get("description") or "").strip()
        raw_used = d.get("ingredients_used") or []
        used_clean: list[dict] = []
        if isinstance(raw_used, list):
            for u in raw_used:
                if not isinstance(u, dict):
                    continue
                used_clean.append(
                    {
                        "name": str(u.get("name") or "").strip(),
                        "portion": float(u.get("portion", 0) or 0),
                        "unit": str(u.get("unit") or "").strip(),
                    }
                )
        if not name or calories <= 0 or portion <= 0:
            continue

        # 最初に使われた素材の id を残しておく(履歴との多少の紐付け用)
        ingredient_id = None
        for used in used_clean:
            ing = by_name.get(used["name"])
            if ing is not None:
                ingredient_id = ing.id
                break

        items.append(
            MenuItem(
                ingredient_id=ingredient_id,
                name=name,
                portion=portion,
                unit=unit,
                calories=calories,
                ingredients_used=used_clean,
                description=description,
            )
        )

    if not items:
        return None

    menu_name = str(payload.get("menu_name") or items[0].name).strip()
    total = sum(i.calories for i in items)
    return GeneratedMenu(
        menu_name=menu_name,
        items=items,
        total_calories=total,
        is_fallback=False,
        profile_name=profile.name,
    )


__all__ = [
    "AISuggesterUnavailableError",
    "MENU_TOOL",
    "generate_ai_menu",
    "is_available",
]
