from app.line_notifier import format_breakfast
from app.menu_generator import GeneratedMenu, MenuItem


def _two_profiles():
    big = GeneratedMenu(
        profile_name="700kcal",
        menu_name="テスト700",
        items=[
            MenuItem(1, "食パン", 1, "枚", 160),
            MenuItem(2, "ゆで卵", 1, "個", 90),
            MenuItem(3, "バナナ", 1, "本", 90),
            MenuItem(4, "牛乳", 200, "ml", 134),
        ],
        total_calories=474,
    )
    small = GeneratedMenu(
        profile_name="300kcal",
        menu_name="テスト300",
        items=[
            MenuItem(5, "食パン", 1, "枚", 160),
            MenuItem(6, "ヨーグルト", 100, "g", 62),
            MenuItem(7, "コーヒー", 150, "ml", 6),
        ],
        total_calories=228,
    )
    return [big, small]


def test_format_breakfast_contains_both_profiles():
    text = format_breakfast(_two_profiles())
    assert "きょうの朝ごはん" in text
    assert "700kcal" in text
    assert "300kcal" in text
    assert "テスト700" in text
    assert "テスト300" in text
    assert "食パン: 1枚" in text
    assert "牛乳: 200ml" in text
    assert "474 kcal" in text
    assert "228 kcal" in text


def test_format_breakfast_marks_fallback_per_menu():
    menus = _two_profiles()
    menus[1].is_fallback = True
    text = format_breakfast(menus)
    assert "代替" in text
