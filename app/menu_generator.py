"""献立自動生成ロジック(2人分対応)。

- 複数の「プロファイル」(目標カロリー+構成+許容範囲)を並べて生成する
- 既定: 700kcal(たっぷり/4品) と 300kcal(ひかえめ/3品) の2人分
- プロファイルごとに直近3日と同じ食材組合せを避ける
- 生成に失敗した場合はプロファイル別の固定代替メニューを返す
"""
from __future__ import annotations

import json
import random
from dataclasses import dataclass, asdict, field
from datetime import date, timedelta
from typing import Iterable, Sequence

from sqlalchemy.orm import Session

from app.config import GENERATION_ATTEMPTS, HISTORY_DAYS_TO_AVOID
from app.models import Ingredient, MenuHistory


@dataclass(frozen=True)
class MenuProfile:
    name: str                              # 表示名 (例: "700kcal")
    target: int                            # 目標カロリー
    cal_min: int                           # 許容下限
    cal_max: int                           # 許容上限
    template: tuple[tuple[str, int], ...]  # ((category, count), ...)
    fallback_items: tuple[tuple[str, float, str, float], ...]  # (name, portion, unit, kcal)
    fallback_name: str


DEFAULT_PROFILES: tuple[MenuProfile, ...] = (
    MenuProfile(
        name="700kcal",
        target=700, cal_min=650, cal_max=750,
        template=(("main", 1), ("protein", 1), ("side", 1), ("drink", 1)),
        fallback_name="定番トースト朝食(代替)",
        fallback_items=(
            ("食パン(6枚切)", 1.0, "枚", 160.0),
            ("ゆで卵",       1.0, "個", 90.0),
            ("ヨーグルト",   100.0, "g", 65.0),
            ("バナナ",       1.0, "本", 90.0),
            ("牛乳",         200.0, "ml", 134.0),
            ("りんご",       0.5, "個", 60.0),
            ("サラダ油",     5.0, "g", 45.0),
        ),
    ),
    MenuProfile(
        name="300kcal",
        target=300, cal_min=250, cal_max=350,
        template=(("main", 1), ("protein", 1), ("drink", 1)),
        fallback_name="軽め朝食(代替)",
        fallback_items=(
            ("食パン(6枚切)",     1.0, "枚", 160.0),
            ("ヨーグルト(無糖)", 100.0, "g", 62.0),
            ("コーヒー(ブラック)", 150.0, "ml", 6.0),
        ),
    ),
)


@dataclass
class MenuItem:
    ingredient_id: int | None
    name: str
    portion: float
    unit: str
    calories: float
    # AI が組み立てた料理のときだけ値が入る(ルールベース時は空)
    ingredients_used: list[dict] = field(default_factory=list)
    description: str = ""


@dataclass
class GeneratedMenu:
    menu_name: str
    items: list[MenuItem] = field(default_factory=list)
    total_calories: float = 0.0
    is_fallback: bool = False
    profile_name: str = ""
    # "ai" = Claude 生成 / "rule" = ルールベース生成
    source: str = "rule"

    def to_payload(self) -> dict:
        return {
            "profile_name": self.profile_name,
            "menu_name": self.menu_name,
            "items": [asdict(i) for i in self.items],
            "total_calories": round(self.total_calories, 1),
            "is_fallback": self.is_fallback,
            "source": self.source,
        }

    def signature(self) -> tuple:
        return tuple(sorted((i.name, round(i.portion, 2)) for i in self.items))


def _portion_options(ingredient: Ingredient) -> list[float]:
    lo, hi = ingredient.min_portion, ingredient.max_portion
    if lo >= hi:
        return [round(ingredient.default_portion, 2)]
    steps = 5
    span = hi - lo
    raw = [lo + span * k / (steps - 1) for k in range(steps)]
    if ingredient.unit in ("個", "枚", "本"):
        return sorted({round(v) for v in raw if round(v) > 0}) or [int(round(ingredient.default_portion))]
    return [round(v, 1) for v in raw]


def _build_menu_name(items: Sequence[MenuItem]) -> str:
    main = next((i.name for i in items if i.name), "朝食")
    return f"{main}を中心とした朝ごはん"


def _historic_signatures(session: Session, days: int, profile_name: str | None = None) -> set[tuple]:
    cutoff = date.today() - timedelta(days=days)
    q = session.query(MenuHistory).filter(MenuHistory.served_on >= cutoff)
    if profile_name is not None:
        # profile_name 列が存在しない/未設定の古い行も対象外にしないよう、None 一致は許容
        q = q.filter(
            (MenuHistory.profile_name == profile_name) | (MenuHistory.profile_name.is_(None))
        )
    sigs: set[tuple] = set()
    for row in q.all():
        try:
            items = json.loads(row.items_json)
        except (TypeError, ValueError):
            continue
        sigs.add(tuple(sorted((i["name"], round(float(i["portion"]), 2)) for i in items)))
    return sigs


def _candidate(profile: MenuProfile, grouped: dict[str, list[Ingredient]]) -> GeneratedMenu | None:
    items: list[MenuItem] = []
    for category, count in profile.template:
        pool = grouped.get(category, [])
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
        profile_name=profile.name,
    )


def _group_by_category(ingredients: Iterable[Ingredient]) -> dict[str, list[Ingredient]]:
    grouped: dict[str, list[Ingredient]] = {}
    for ing in ingredients:
        if not ing.active:
            continue
        grouped.setdefault(ing.category, []).append(ing)
    return grouped


def _fallback(profile: MenuProfile) -> GeneratedMenu:
    items = [MenuItem(None, n, p, u, c) for (n, p, u, c) in profile.fallback_items]
    total = sum(i.calories for i in items)
    return GeneratedMenu(
        menu_name=profile.fallback_name,
        items=items,
        total_calories=total,
        is_fallback=True,
        profile_name=profile.name,
    )


def generate_menu_for_profile(
    session: Session,
    profile: MenuProfile,
    today: date | None = None,
    exclude_signatures: set[tuple] | None = None,
) -> GeneratedMenu:
    today = today or date.today()
    ingredients = session.query(Ingredient).filter(Ingredient.active.is_(True)).all()
    grouped = _group_by_category(ingredients)
    required_categories = [c for c, _ in profile.template]
    if not all(grouped.get(c) for c in required_categories):
        return _fallback(profile)

    history = _historic_signatures(session, HISTORY_DAYS_TO_AVOID, profile.name)
    if exclude_signatures:
        history = history | exclude_signatures

    best: GeneratedMenu | None = None
    best_distance = float("inf")
    for _ in range(GENERATION_ATTEMPTS):
        cand = _candidate(profile, grouped)
        if cand is None:
            return _fallback(profile)
        if cand.signature() in history:
            continue
        if profile.cal_min <= cand.total_calories <= profile.cal_max:
            return cand
        distance = abs(cand.total_calories - profile.target)
        if distance < best_distance:
            best = cand
            best_distance = distance

    if best is not None and abs(best.total_calories - profile.target) <= profile.target * 0.15:
        return best
    return _fallback(profile)


def generate_breakfast(
    session: Session,
    today: date | None = None,
    profiles: Sequence[MenuProfile] = DEFAULT_PROFILES,
) -> list[GeneratedMenu]:
    """全プロファイル分の献立をまとめて返す。

    まず AI に素材から料理を組み立てさせる。AI が使えない / 失敗した場合は
    ルールベース生成にフォールバックする。同日の他プロファイルとシグネチャが
    完全一致しないよう互いに避ける。
    """
    # 遅延 import で循環依存を避ける(ai_suggester も menu_generator を import する)
    from app.ai_suggester import generate_ai_menu

    produced: list[GeneratedMenu] = []
    used_signatures: set[tuple] = set()
    # 履歴シグネチャもまとめて取得し AI のプロンプトに渡す
    history_sigs = _historic_signatures(session, HISTORY_DAYS_TO_AVOID)

    for profile in profiles:
        excluded = used_signatures | history_sigs
        menu = generate_ai_menu(session, profile, exclude_signatures=excluded)
        if menu is None:
            menu = generate_menu_for_profile(
                session, profile, today=today, exclude_signatures=used_signatures
            )
        produced.append(menu)
        used_signatures.add(menu.signature())
    return produced


def save_history(
    session: Session,
    menus: Sequence[GeneratedMenu],
    served_on: date | None = None,
) -> list[MenuHistory]:
    served_on = served_on or date.today()
    records: list[MenuHistory] = []
    for menu in menus:
        record = MenuHistory(
            served_on=served_on,
            profile_name=menu.profile_name or None,
            menu_name=menu.menu_name,
            items_json=json.dumps([asdict(i) for i in menu.items], ensure_ascii=False),
            total_calories=menu.total_calories,
            is_fallback=menu.is_fallback,
        )
        session.add(record)
        records.append(record)
    session.flush()
    return records
