from app.line_notifier import format_breakfast
from app.menu_generator import GeneratedMenu, MenuItem


def _rule_based_two_profiles():
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
        source="rule",
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
        source="rule",
    )
    return [big, small]


def test_format_breakfast_rule_based_uses_python_format():
    text = format_breakfast(_rule_based_two_profiles())
    assert "きょうの朝ごはん" in text
    assert "700kcal" in text and "300kcal" in text
    assert "テスト700" in text and "テスト300" in text
    assert "食パン: 1枚" in text
    assert "牛乳: 200ml" in text
    assert "474 kcal" in text
    assert "228 kcal" in text


def test_format_breakfast_marks_fallback_per_menu():
    menus = _rule_based_two_profiles()
    menus[1].is_fallback = True
    text = format_breakfast(menus)
    assert "代替" in text


def test_format_breakfast_uses_ai_line_text_verbatim():
    menus = [
        GeneratedMenu(
            profile_name="700kcal",
            menu_name="AI 献立 A",
            items=[MenuItem(None, "しゃけ茶漬け", 1, "杯", 420)],
            total_calories=420,
            source="ai",
            line_text="【700kcal】🍣 しゃけ茶漬け\n・しゃけ 1切れ\n・梅干し 1個\n合計 420kcal",
        ),
        GeneratedMenu(
            profile_name="300kcal",
            menu_name="AI 献立 B",
            items=[MenuItem(None, "トースト", 1, "枚", 160)],
            total_calories=160,
            source="ai",
            line_text="【300kcal】🍞 トーストセット\n・食パン 1枚\n合計 160kcal",
        ),
    ]
    text = format_breakfast(menus)
    # AI が書いた文面がそのまま含まれる
    assert "🍣 しゃけ茶漬け" in text
    assert "🍞 トーストセット" in text
    # ルールベース用の《...》はつかない(テンプレ由来の空要素も無い)
    assert "《" not in text
    assert "きょうの朝ごはん" in text
    assert "今日も一日がんばろう" in text


def test_format_breakfast_empty_fallback_shows_menu_name():
    menus = [
        GeneratedMenu(
            profile_name="700kcal",
            menu_name="登録済みの食材だけでは献立が組めませんでした",
            items=[],
            total_calories=0,
            is_fallback=True,
        )
    ]
    text = format_breakfast(menus)
    assert "代替" in text
    assert "献立が組めませんでした" in text
