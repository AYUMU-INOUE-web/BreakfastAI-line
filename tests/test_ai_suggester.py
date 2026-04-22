import tempfile
import os
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.menu_generator import DEFAULT_PROFILES
from app.models import Ingredient


def _tool_response(menu_name: str, dishes: list[dict]):
    block = SimpleNamespace(
        type="tool_use",
        name="submit_menu",
        input={"menu_name": menu_name, "dishes": dishes},
        id="toolu_1",
    )
    return SimpleNamespace(content=[block], stop_reason="tool_use")


@pytest.fixture
def ai_session(session, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "dummy")
    # 素材を数種類投入
    session.add_all([
        Ingredient(name="卵", category="protein", unit="個", calories_per_unit=80,
                   default_portion=1, min_portion=1, max_portion=3, active=True),
        Ingredient(name="しゃけ", category="protein", unit="切れ", calories_per_unit=150,
                   default_portion=1, min_portion=1, max_portion=2, active=True),
        Ingredient(name="梅干し", category="side", unit="個", calories_per_unit=5,
                   default_portion=1, min_portion=1, max_portion=3, active=True),
        Ingredient(name="ごはん", category="main", unit="g", calories_per_unit=1.68,
                   default_portion=150, min_portion=100, max_portion=200, active=True),
        Ingredient(name="緑茶", category="drink", unit="ml", calories_per_unit=0.02,
                   default_portion=200, min_portion=150, max_portion=250, active=True),
        Ingredient(name="牛乳", category="drink", unit="ml", calories_per_unit=0.67,
                   default_portion=200, min_portion=150, max_portion=250, active=True),
    ])
    session.commit()

    # config モジュールを再読み込みして ANTHROPIC_API_KEY を反映
    import importlib
    from app import config, ai_suggester
    importlib.reload(config)
    importlib.reload(ai_suggester)
    return session, ai_suggester


def test_generate_ai_menu_returns_menu_with_dishes(ai_session):
    session, ai_suggester = ai_session
    profile = DEFAULT_PROFILES[0]

    dishes = [
        {
            "name": "しゃけ茶漬け",
            "portion": 1, "unit": "杯", "calories": 420,
            "ingredients_used": [
                {"name": "しゃけ", "portion": 1, "unit": "切れ"},
                {"name": "梅干し", "portion": 1, "unit": "個"},
                {"name": "ごはん", "portion": 150, "unit": "g"},
                {"name": "緑茶", "portion": 200, "unit": "ml"},
            ],
            "description": "ごはんに焼き鮭と梅干しを乗せ熱い緑茶をかける",
        },
        {
            "name": "ゆで卵",
            "portion": 1, "unit": "個", "calories": 80,
            "ingredients_used": [{"name": "卵", "portion": 1, "unit": "個"}],
            "description": "沸騰したお湯で 8 分茹でる",
        },
        {
            "name": "牛乳",
            "portion": 200, "unit": "ml", "calories": 134,
            "ingredients_used": [{"name": "牛乳", "portion": 200, "unit": "ml"}],
            "description": "温めても冷やしても",
        },
    ]

    class FakeMessages:
        def create(self, **kwargs):
            assert kwargs["tool_choice"] == {"type": "tool", "name": "submit_menu"}
            assert kwargs["tools"][0]["name"] == "submit_menu"
            assert "卵" in kwargs["messages"][0]["content"]
            return _tool_response("しゃけ茶漬け中心の和朝食", dishes)

    class FakeClient:
        def __init__(self, api_key=None):
            self.messages = FakeMessages()

    with patch.object(ai_suggester.anthropic, "Anthropic", FakeClient):
        menu = ai_suggester.generate_ai_menu(session, profile, exclude_signatures=set())

    assert menu is not None
    assert menu.profile_name == "700kcal"
    assert menu.menu_name == "しゃけ茶漬け中心の和朝食"
    assert [i.name for i in menu.items] == ["しゃけ茶漬け", "ゆで卵", "牛乳"]
    assert menu.total_calories == 634
    # 使用素材が各料理に紐付いている
    assert menu.items[0].ingredients_used[0]["name"] == "しゃけ"
    assert "緑茶" in [u["name"] for u in menu.items[0].ingredients_used]
    assert menu.items[1].description.startswith("沸騰")


def test_generate_ai_menu_returns_none_without_api_key(session, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    import importlib
    from app import config, ai_suggester
    importlib.reload(config)
    importlib.reload(ai_suggester)

    assert ai_suggester.generate_ai_menu(session, DEFAULT_PROFILES[0]) is None


def test_generate_ai_menu_returns_none_without_ingredients(monkeypatch):
    import importlib
    from app import config, ai_suggester
    monkeypatch.setenv("ANTHROPIC_API_KEY", "dummy")
    importlib.reload(config)
    importlib.reload(ai_suggester)

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.models import Base
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine, future=True)()

    assert ai_suggester.generate_ai_menu(s, DEFAULT_PROFILES[0]) is None


def test_generate_ai_menu_drops_dishes_with_unregistered_ingredients(ai_session):
    """AI が登録外の素材(例: しょうゆ)を使った料理は採用されない。"""
    session, ai_suggester = ai_session
    dishes = [
        {
            "name": "OK料理",
            "portion": 1, "unit": "皿", "calories": 100,
            "ingredients_used": [{"name": "卵", "portion": 1, "unit": "個"}],
            "description": "",
        },
        {
            "name": "NG料理",
            "portion": 1, "unit": "皿", "calories": 100,
            "ingredients_used": [
                {"name": "卵", "portion": 1, "unit": "個"},
                {"name": "しょうゆ", "portion": 5, "unit": "ml"},  # 未登録
            ],
            "description": "",
        },
    ]

    class FakeMessages:
        def create(self, **kwargs):
            return _tool_response("mix", dishes)

    class FakeClient:
        def __init__(self, api_key=None):
            self.messages = FakeMessages()

    with patch.object(ai_suggester.anthropic, "Anthropic", FakeClient):
        menu = ai_suggester.generate_ai_menu(session, DEFAULT_PROFILES[0])

    assert menu is not None
    assert [i.name for i in menu.items] == ["OK料理"]


def test_generate_ai_menu_returns_none_if_all_dishes_have_unregistered(ai_session):
    session, ai_suggester = ai_session
    dishes = [
        {
            "name": "NG",
            "portion": 1, "unit": "皿", "calories": 100,
            "ingredients_used": [{"name": "しょうゆ", "portion": 5, "unit": "ml"}],
            "description": "",
        }
    ]

    class FakeMessages:
        def create(self, **kwargs):
            return _tool_response("all ng", dishes)

    class FakeClient:
        def __init__(self, api_key=None):
            self.messages = FakeMessages()

    with patch.object(ai_suggester.anthropic, "Anthropic", FakeClient):
        menu = ai_suggester.generate_ai_menu(session, DEFAULT_PROFILES[0])

    # 有効料理が 0 件になるので None
    assert menu is None


def test_generate_ai_menu_handles_api_error(ai_session):
    session, ai_suggester = ai_session

    class FakeMessages:
        def create(self, **kwargs):
            raise RuntimeError("network down")

    class FakeClient:
        def __init__(self, api_key=None):
            self.messages = FakeMessages()

    with patch.object(ai_suggester.anthropic, "Anthropic", FakeClient):
        menu = ai_suggester.generate_ai_menu(session, DEFAULT_PROFILES[0])
    assert menu is None


def test_generate_breakfast_uses_ai_then_falls_back(populated_session, monkeypatch):
    """AI が成功したら AI 結果、失敗したらルールベース、を両方カバーする。"""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "dummy")
    import importlib
    from app import config, ai_suggester, menu_generator
    importlib.reload(config)
    importlib.reload(ai_suggester)
    importlib.reload(menu_generator)

    # populated_session は 食パン/ごはん/ゆで卵/ヨーグルト/バナナ/サラダ/牛乳/コーヒー を持つ
    dishes = [
        {"name": "トースト", "portion": 1, "unit": "枚", "calories": 160,
         "ingredients_used": [{"name": "食パン", "portion": 1, "unit": "枚"}],
         "description": "パンを焼く"},
        {"name": "ヨーグルト", "portion": 100, "unit": "g", "calories": 62,
         "ingredients_used": [{"name": "ヨーグルト", "portion": 100, "unit": "g"}],
         "description": "そのまま"},
    ]

    call_count = {"n": 0}

    class FakeMessages:
        def create(self, **kwargs):
            call_count["n"] += 1
            # 1 回目(700kcal)は成功、2 回目(300kcal)は失敗
            if call_count["n"] == 1:
                return _tool_response("AI 献立", dishes)
            raise RuntimeError("down")

    class FakeClient:
        def __init__(self, api_key=None):
            self.messages = FakeMessages()

    with patch.object(ai_suggester.anthropic, "Anthropic", FakeClient):
        menus = menu_generator.generate_breakfast(populated_session)

    assert len(menus) == 2
    # 700kcal は AI 結果(menu_name が "AI 献立", dish 単位)
    assert menus[0].profile_name == "700kcal"
    assert menus[0].menu_name == "AI 献立"
    assert menus[0].items[0].name == "トースト"
    # 300kcal は AI 失敗 → ルールベース(カテゴリ由来の名前になる)
    assert menus[1].profile_name == "300kcal"
    assert menus[1].menu_name != "AI 献立"


def test_admin_ai_status_endpoint(monkeypatch):
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp.name}")
    monkeypatch.setenv("AUTO_SEED", "0")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "dummy")

    import importlib
    from app import config, database, ai_suggester, admin
    importlib.reload(config)
    importlib.reload(database)
    importlib.reload(ai_suggester)
    importlib.reload(admin)

    app = admin.create_app()
    app.testing = True
    with app.test_client() as c:
        assert c.get("/api/ai/status").get_json() == {"available": True}
        # 旧 /api/ai/suggest は廃止 → 404
        assert c.post("/api/ai/suggest", json={"ingredients": []}).status_code == 404

    os.unlink(tmp.name)
