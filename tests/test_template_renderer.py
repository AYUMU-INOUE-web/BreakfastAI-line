from app.menu_generator import GeneratedMenu, MenuItem
from app.template_renderer import (
    DEFAULT_TEMPLATE_BODY,
    ensure_default_template,
    get_active_body,
    render,
    sample_menu,
)
from app.models import MessageTemplate


def _menu():
    return GeneratedMenu(
        menu_name="テスト献立",
        items=[
            MenuItem(None, "食パン", 1, "枚", 160),
            MenuItem(None, "目玉焼き", 1, "個", 110),
        ],
        total_calories=270,
        is_fallback=False,
    )


def test_default_template_renders_all_items():
    text = render(DEFAULT_TEMPLATE_BODY, _menu())
    assert "テスト献立" in text
    assert "食パン: 1枚" in text
    assert "目玉焼き: 1個" in text
    assert "270 kcal" in text
    assert "代替メニュー" not in text


def test_fallback_marker_shown_for_fallback_menu():
    menu = _menu()
    menu.is_fallback = True
    text = render(DEFAULT_TEMPLATE_BODY, menu)
    assert "代替メニュー" in text


def test_broken_template_falls_back_to_default():
    broken = "{{ unknown_func(  "  # 構文エラー
    text = render(broken, _menu())
    # 既定テンプレが描画されていること
    assert "きょうの朝ごはん" in text
    assert "食パン: 1枚" in text


def test_sandbox_blocks_attribute_access_on_internals():
    malicious = "{{ ''.__class__.__mro__ }}"
    text = render(malicious, _menu())
    # 既定テンプレに fall back されること
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


def test_sample_menu_is_renderable():
    text = render(DEFAULT_TEMPLATE_BODY, sample_menu())
    assert "食パン" in text
