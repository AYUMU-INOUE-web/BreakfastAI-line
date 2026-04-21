from app.menu_generator import GeneratedMenu, MenuItem
from app.models import MessageTemplate
from app.template_renderer import (
    DEFAULT_TEMPLATE_BODY,
    ensure_default_template,
    get_active_body,
    render,
    sample_menus,
)


def _two_menus():
    return [
        GeneratedMenu(
            profile_name="700kcal",
            menu_name="テスト700",
            items=[
                MenuItem(None, "食パン", 1, "枚", 160),
                MenuItem(None, "目玉焼き", 1, "個", 110),
            ],
            total_calories=270,
        ),
        GeneratedMenu(
            profile_name="300kcal",
            menu_name="テスト300",
            items=[MenuItem(None, "ヨーグルト", 100, "g", 62)],
            total_calories=62,
        ),
    ]


def test_default_template_renders_each_profile_block():
    text = render(DEFAULT_TEMPLATE_BODY, _two_menus())
    assert "700kcal" in text
    assert "300kcal" in text
    assert "テスト700" in text
    assert "テスト300" in text
    assert "食パン: 1枚" in text
    assert "270 kcal" in text
    assert "62 kcal" in text


def test_fallback_marker_shown_per_menu():
    menus = _two_menus()
    menus[1].is_fallback = True
    text = render(DEFAULT_TEMPLATE_BODY, menus)
    assert "(代替)" in text


def test_broken_template_falls_back_to_default():
    broken = "{{ unknown_func(  "  # 構文エラー
    text = render(broken, _two_menus())
    assert "きょうの朝ごはん" in text
    assert "食パン: 1枚" in text


def test_sandbox_blocks_attribute_access_on_internals():
    malicious = "{{ ''.__class__.__mro__ }}"
    text = render(malicious, _two_menus())
    assert "きょうの朝ごはん" in text


def test_get_active_body_returns_default_when_empty(session):
    assert get_active_body(session) == DEFAULT_TEMPLATE_BODY


def test_ensure_default_template_seeds_once(session):
    ensure_default_template(session)
    session.commit()
    ensure_default_template(session)
    session.commit()
    rows = session.query(MessageTemplate).all()
    assert len(rows) == 1
    assert rows[0].is_active is True
    assert rows[0].body == DEFAULT_TEMPLATE_BODY


def test_sample_menus_are_renderable():
    text = render(DEFAULT_TEMPLATE_BODY, sample_menus())
    assert "食パン" in text
    assert "700kcal" in text
    assert "300kcal" in text
