"""献立自動生成ロジック。

カテゴリ別にランダムに食材を組み合わせ、許容カロリー範囲(650-750kcal)に
収まる現実的な分量の献立を作る。直近 N 日と完全に同じ組み合わせは避ける。
失敗した場合は固定の代替メニューを返す。
"""
from __future__ import annotations

import json
import random
from dataclasses import dataclass, asdict, field
from datetime import date, timedelta
from typing import Iterable, Sequence

from sqlalchemy.orm import Session

from app.config import (
    CALORIE_MAX,
    CALORIE_MIN,
    CALORIE_TARGET,
    GENERATION_ATTEMPTS,
    HISTORY_DAYS_TO_AVOID,
)
from app.models import Ingredient, MenuHistory


# 1献立に必要なカテゴリの構成
MENU_TEMPLATE = [
    ("main", 1),     # 主食 1品
    ("protein", 1),  # たんぱく源 1品
    ("side", 1),     # 副菜 1品
    ("drink", 1),    # 飲み物 1品
]

FALLBACK_MENU = {
    "menu_name": "定番トースト朝食(代替)",
    "items": [
        {"name": "食パン(6枚切)", "portion": 1.0, "unit": "枚", "calories": 160.0},
        {"name": "ゆで卵", "portion": 1.0, "unit": "個", "calories": 90.0},
        {"name": "ヨーグルト", "portion": 100.0, "unit": "g", "calories": 65.0},
        {"name": "バナナ", "portion": 1.0, "unit": "本", "calories": 90.0},
        {"name": "牛乳", "portion": 200.0, "unit": "ml", "calories": 134.0},
        {"name": "サラダ油(目玉焼き用)", "portion": 5.0, "unit": "g", "calories": 45.0},
        {"name": "りんご", "portion": 0.5, "unit": "個", "calories": 60.0},
    ],
    "total_calories": 644.0,
}


@dataclass
class MenuItem:
    ingredient_id: int | None
    name: str
    portion: float
    unit: str
    calories: float


@dataclass
class GeneratedMenu:
    menu_name: str
    items: list[MenuItem] = field(default_factory=list)
    total_calories: float = 0.0
    is_fallback: bool = False

    def to_payload(self) -> dict:
        return {
            "menu_name": self.menu_name,
            "items": [asdict(i) for i in self.items],
            "total_calories": round(self.total_calories, 1),
            "is_fallback": self.is_fallback,
        }

    def signature(self) -> tuple:
        """履歴比較に使う食材+分量の正規化キー。"""
        return tuple(sorted((i.name, round(i.portion, 2)) for i in self.items))


def _portion_options(ingredient: Ingredient) -> list[float]:
    """min〜maxを5段階に量子化し、現実的な分量候補を返す。"""
    lo, hi = ingredient.min_portion, ingredient.max_portion
    if lo >= hi:
        return [round(ingredient.default_portion, 2)]
    steps = 5
    span = hi - lo
    raw = [lo + span * k / (steps - 1) for k in range(steps)]
    # 食パン1枚など整数単位を尊重するため、unitに応じて丸める
    if ingredient.unit in ("個", "枚", "本"):
        return sorted({round(v) for v in raw if round(v) > 0}) or [int(round(ingredient.default_portion))]
    return [round(v, 1) for v in raw]


def _build_menu_name(items: Sequence[MenuItem]) -> str:
    main = next((i.name for i in items if i.name), "朝食")
    return f"{main}を中心とした朝ごはん"


def _historic_signatures(session: Session, days: int) -> set[tuple]:
    cutoff = date.today() - timedelta(days=days)
    rows = (
        session.query(MenuHistory)
        .filter(MenuHistory.served_on >= cutoff)
        .all()
    )
    sigs: set[tuple] = set()
    for row in rows:
        try:
            items = json.loads(row.items_json)
        except (TypeError, ValueError):
            continue
        sigs.add(tuple(sorted((i["name"], round(float(i["portion"]), 2)) for i in items)))
    return sigs


def _candidate(ingredients_by_category: dict[str, list[Ingredient]]) -> GeneratedMenu | None:
    items: list[MenuItem] = []
    for category, count in MENU_TEMPLATE:
        pool = ingredients_by_category.get(category, [])
        if len(pool) < count:
            return None
        chosen = random.sample(pool, count)
        for ing in chosen:
            portion = random.choice(_portion_options(ing))
            calories = round(portion * ing.calories_per_unit, 1)
            items.append(MenuItem(ing.id, ing.name, portion, ing.unit, calories))
    total = sum(i.calories for i in items)
    return GeneratedMenu(
        menu_name=_build_menu_name(items),
        items=items,
        total_calories=total,
    )


def _group_by_category(ingredients: Iterable[Ingredient]) -> dict[str, list[Ingredient]]:
    grouped: dict[str, list[Ingredient]] = {}
    for ing in ingredients:
        if not ing.active:
            continue
        grouped.setdefault(ing.category, []).append(ing)
    return grouped


def generate_menu(session: Session, today: date | None = None) -> GeneratedMenu:
    today = today or date.today()
    ingredients = session.query(Ingredient).filter(Ingredient.active.is_(True)).all()
    grouped = _group_by_category(ingredients)

    required_categories = [c for c, _ in MENU_TEMPLATE]
    if not all(grouped.get(c) for c in required_categories):
        return _fallback()

    history = _historic_signatures(session, HISTORY_DAYS_TO_AVOID)

    best: GeneratedMenu | None = None
    best_distance = float("inf")
    for _ in range(GENERATION_ATTEMPTS):
        cand = _candidate(grouped)
        if cand is None:
            return _fallback()
        if cand.signature() in history:
            continue
        if CALORIE_MIN <= cand.total_calories <= CALORIE_MAX:
            return cand
        # 範囲外でも、後のフォールバック判定用にターゲット差が最小の候補を覚えておく
        distance = abs(cand.total_calories - CALORIE_TARGET)
        if distance < best_distance:
            best = cand
            best_distance = distance

    # 範囲外でもベスト候補が ±15% 以内なら採用、それ以外はフォールバック
    if best is not None and abs(best.total_calories - CALORIE_TARGET) <= CALORIE_TARGET * 0.15:
        return best
    return _fallback()


def _fallback() -> GeneratedMenu:
    items = [
        MenuItem(None, i["name"], i["portion"], i["unit"], i["calories"])
        for i in FALLBACK_MENU["items"]
    ]
    return GeneratedMenu(
        menu_name=FALLBACK_MENU["menu_name"],
        items=items,
        total_calories=FALLBACK_MENU["total_calories"],
        is_fallback=True,
    )


def save_history(session: Session, menu: GeneratedMenu, served_on: date | None = None) -> MenuHistory:
    served_on = served_on or date.today()
    record = MenuHistory(
        served_on=served_on,
        menu_name=menu.menu_name,
        items_json=json.dumps([asdict(i) for i in menu.items], ensure_ascii=False),
        total_calories=menu.total_calories,
        is_fallback=menu.is_fallback,
    )
    session.add(record)
    session.flush()
    return record
