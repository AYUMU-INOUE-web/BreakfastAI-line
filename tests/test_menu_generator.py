import json
from dataclasses import asdict
from datetime import date, timedelta

import pytest

from app.menu_generator import (
    DEFAULT_PROFILES,
    GeneratedMenu,
    MenuItem,
    MenuProfile,
    generate_breakfast,
    generate_menu_for_profile,
    save_history,
)
from app.models import Ingredient, MenuHistory


def test_generate_breakfast_produces_one_menu_per_profile(populated_session):
    menus = generate_breakfast(populated_session, today=date(2026, 4, 21))
    assert len(menus) == len(DEFAULT_PROFILES)
    assert [m.profile_name for m in menus] == [p.name for p in DEFAULT_PROFILES]


def test_700kcal_profile_hits_its_range(populated_session):
    profile = DEFAULT_PROFILES[0]
    menu = generate_menu_for_profile(populated_session, profile, today=date(2026, 4, 21))
    assert profile.name == "700kcal"
    # non-fallback の場合はレンジ内、fallback でも近い値
    if not menu.is_fallback:
        assert profile.cal_min <= menu.total_calories <= profile.cal_max
    assert len(menu.items) == sum(cnt for _, cnt in profile.template)


def test_300kcal_profile_respects_its_range(populated_session):
    profile = DEFAULT_PROFILES[1]
    menu = generate_menu_for_profile(populated_session, profile, today=date(2026, 4, 21))
    assert profile.name == "300kcal"
    if not menu.is_fallback:
        assert profile.cal_min <= menu.total_calories <= profile.cal_max
    # 3 品構成
    assert len(menu.items) == sum(cnt for _, cnt in profile.template)


def test_generate_menu_falls_back_when_no_ingredients(session):
    menus = generate_breakfast(session, today=date(2026, 4, 21))
    # 登録素材が無ければ空の fallback メニュー(未登録の既定料理は使わない)
    assert all(m.is_fallback for m in menus)
    assert all(m.items == [] for m in menus)
    assert all("献立が組めませんでした" in m.menu_name for m in menus)


def test_generate_menu_falls_back_when_category_missing(session):
    session.add(Ingredient(name="食パン", category="main", unit="枚",
                            calories_per_unit=160, default_portion=1,
                            min_portion=1, max_portion=2, active=True))
    session.commit()
    menus = generate_breakfast(session, today=date(2026, 4, 21))
    assert all(m.is_fallback for m in menus)


def test_generate_menu_avoids_recent_history(populated_session, monkeypatch):
    fixed_items = [
        MenuItem(1, "食パン", 1, "枚", 160),
        MenuItem(3, "ゆで卵", 1, "個", 90),
        MenuItem(5, "バナナ", 1, "本", 90),
        MenuItem(7, "牛乳", 200, "ml", 134),
    ]

    from app import menu_generator as mg

    def _fixed_candidate(profile, grouped):
        return GeneratedMenu(
            menu_name="テスト献立",
            items=[MenuItem(i.ingredient_id, i.name, i.portion, i.unit, i.calories) for i in fixed_items],
            total_calories=474,
            profile_name=profile.name,
        )

    monkeypatch.setattr(mg, "_candidate", _fixed_candidate)

    populated_session.add(MenuHistory(
        served_on=date.today() - timedelta(days=1),
        profile_name="700kcal",
        menu_name="テスト献立",
        items_json=json.dumps([asdict(i) for i in fixed_items], ensure_ascii=False),
        total_calories=474,
        is_fallback=False,
    ))
    populated_session.commit()

    menu = generate_menu_for_profile(populated_session, DEFAULT_PROFILES[0])
    assert menu.is_fallback


def test_save_history_persists_all_menus(populated_session):
    menus = generate_breakfast(populated_session, today=date(2026, 4, 21))
    records = save_history(populated_session, menus, served_on=date(2026, 4, 21))
    populated_session.commit()
    assert len(records) == len(menus)
    for record, menu in zip(records, menus):
        assert record.id is not None
        assert record.profile_name == menu.profile_name
        items = json.loads(record.items_json)
        assert len(items) == len(menu.items)


def test_fallback_metadata_still_defines_backup_items():
    # fallback_items はプロファイルに残っているが、runtime では使われない。
    # (将来的な手動参照用に残す)
    for profile in DEFAULT_PROFILES:
        assert profile.fallback_items is not None
        assert profile.fallback_name
