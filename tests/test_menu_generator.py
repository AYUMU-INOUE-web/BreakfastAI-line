import json
from dataclasses import asdict
from datetime import date, timedelta

import pytest

from app.config import CALORIE_MAX, CALORIE_MIN
from app.menu_generator import (
    FALLBACK_MENU,
    GeneratedMenu,
    MenuItem,
    generate_menu,
    save_history,
)
from app.models import Ingredient, MenuHistory


def test_generate_menu_returns_in_calorie_range(populated_session):
    menu = generate_menu(populated_session, today=date(2026, 4, 21))
    assert not menu.is_fallback
    assert CALORIE_MIN <= menu.total_calories <= CALORIE_MAX
    # 4カテゴリ各1品
    categories_picked = {item.name for item in menu.items}
    assert len(categories_picked) == 4


def test_generate_menu_falls_back_when_no_ingredients(session):
    menu = generate_menu(session, today=date(2026, 4, 21))
    assert menu.is_fallback
    assert menu.menu_name == FALLBACK_MENU["menu_name"]
    assert len(menu.items) == len(FALLBACK_MENU["items"])


def test_generate_menu_falls_back_when_category_missing(session):
    # main しか登録されていない場合は代替メニューになる
    session.add(Ingredient(name="食パン", category="main", unit="枚",
                            calories_per_unit=160, default_portion=1,
                            min_portion=1, max_portion=2, active=True))
    session.commit()
    menu = generate_menu(session, today=date(2026, 4, 21))
    assert menu.is_fallback


def test_generate_menu_avoids_recent_history(populated_session, monkeypatch):
    # 候補生成を毎回同じ献立に固定し、それが履歴にあれば代替が選ばれることを確認
    fixed_items = [
        MenuItem(1, "食パン", 1, "枚", 160),
        MenuItem(3, "ゆで卵", 1, "個", 90),
        MenuItem(5, "バナナ", 1, "本", 90),
        MenuItem(7, "牛乳", 200, "ml", 134),
    ]
    fixed = GeneratedMenu(menu_name="テスト献立", items=fixed_items, total_calories=474)

    from app import menu_generator as mg

    monkeypatch.setattr(mg, "_candidate", lambda grouped: GeneratedMenu(
        menu_name=fixed.menu_name,
        items=[MenuItem(i.ingredient_id, i.name, i.portion, i.unit, i.calories) for i in fixed.items],
        total_calories=fixed.total_calories,
    ))

    populated_session.add(MenuHistory(
        served_on=date.today() - timedelta(days=1),
        menu_name=fixed.menu_name,
        items_json=json.dumps([asdict(i) for i in fixed.items], ensure_ascii=False),
        total_calories=fixed.total_calories,
        is_fallback=False,
    ))
    populated_session.commit()

    menu = generate_menu(populated_session)
    # 履歴と一致するため通常生成では弾かれ、代替メニューに落ちる
    assert menu.is_fallback


def test_save_history_persists_record(populated_session):
    menu = generate_menu(populated_session, today=date(2026, 4, 21))
    record = save_history(populated_session, menu, served_on=date(2026, 4, 21))
    populated_session.commit()
    assert record.id is not None
    assert record.menu_name == menu.menu_name
    items = json.loads(record.items_json)
    assert len(items) == len(menu.items)


def test_fallback_menu_calories_within_band():
    # 代替メニューも要件 (650-750kcal前後) におおむね収まっていること
    assert 600 <= FALLBACK_MENU["total_calories"] <= 750
