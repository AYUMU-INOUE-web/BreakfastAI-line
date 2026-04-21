from app.line_notifier import format_menu
from app.menu_generator import GeneratedMenu, MenuItem


def test_format_menu_lists_items_and_total():
    menu = GeneratedMenu(
        menu_name="テスト",
        items=[
            MenuItem(1, "食パン", 1, "枚", 160),
            MenuItem(2, "ゆで卵", 1, "個", 90),
            MenuItem(3, "バナナ", 1, "本", 90),
            MenuItem(4, "牛乳", 200, "ml", 134),
        ],
        total_calories=474,
        is_fallback=False,
    )
    text = format_menu(menu)
    assert "きょうの朝ごはん" in text
    assert "テスト" in text
    assert "食パン: 1枚" in text
    assert "牛乳: 200ml" in text
    assert "474 kcal" in text


def test_format_menu_marks_fallback():
    menu = GeneratedMenu(menu_name="代替", items=[], total_calories=600, is_fallback=True)
    text = format_menu(menu)
    assert "代替メニュー" in text
