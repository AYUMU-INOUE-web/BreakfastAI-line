import json
import os
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

import pytest


def _fake_anthropic_response(dishes: list[dict]):
    text_block = SimpleNamespace(type="text", text=json.dumps({"dishes": dishes}, ensure_ascii=False))
    return SimpleNamespace(content=[text_block])


def test_suggester_returns_validated_dishes(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "dummy")
    import importlib
    from app import config, ai_suggester
    importlib.reload(config)
    importlib.reload(ai_suggester)

    dishes = [
        {
            "name": "ゆで卵",
            "category": "protein",
            "unit": "個",
            "calories_per_unit": 90,
            "default_portion": 1,
            "min_portion": 1,
            "max_portion": 2,
            "uses_ingredients": ["卵"],
            "description": "沸騰したお湯で8分茹でる。",
        },
        {
            "name": "しゃけ茶漬け",
            "category": "main",
            "unit": "杯",
            "calories_per_unit": 320,
            "default_portion": 1,
            "min_portion": 1,
            "max_portion": 1,
            "uses_ingredients": ["しゃけ", "梅干し", "ごはん"],
            "description": "ごはんに焼き鮭と梅干しを乗せ熱いお茶をかける。",
        },
    ]

    class FakeMessages:
        def create(self, **kwargs):
            assert kwargs["model"].startswith("claude-")
            # output_config で format スキーマが渡っていること
            assert kwargs["output_config"]["format"]["type"] == "json_schema"
            return _fake_anthropic_response(dishes)

    class FakeClient:
        def __init__(self, api_key=None):
            self.messages = FakeMessages()

    with patch.object(ai_suggester.anthropic, "Anthropic", FakeClient):
        result = ai_suggester.suggest_dishes(["卵", "しゃけ", "梅干し", "ごはん"], n=2)

    assert len(result) == 2
    assert result[0]["name"] == "ゆで卵"
    assert result[1]["category"] == "main"


def test_suggester_rejects_invalid_category(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "dummy")
    import importlib
    from app import config, ai_suggester
    importlib.reload(config)
    importlib.reload(ai_suggester)

    dishes = [
        {
            "name": "変な料理",
            "category": "dessert",  # 不正
            "unit": "皿", "calories_per_unit": 100,
            "default_portion": 1, "min_portion": 1, "max_portion": 1,
            "uses_ingredients": [], "description": "",
        },
        {
            "name": "ちゃんとした料理",
            "category": "main",
            "unit": "皿", "calories_per_unit": 200,
            "default_portion": 1, "min_portion": 1, "max_portion": 1,
            "uses_ingredients": [], "description": "",
        },
    ]

    class FakeMessages:
        def create(self, **kwargs):
            return _fake_anthropic_response(dishes)

    class FakeClient:
        def __init__(self, api_key=None):
            self.messages = FakeMessages()

    with patch.object(ai_suggester.anthropic, "Anthropic", FakeClient):
        result = ai_suggester.suggest_dishes(["x"], n=2)

    assert len(result) == 1
    assert result[0]["name"] == "ちゃんとした料理"


def test_suggester_without_api_key_raises(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    import importlib
    from app import config, ai_suggester
    importlib.reload(config)
    importlib.reload(ai_suggester)

    with pytest.raises(ai_suggester.AISuggesterUnavailableError):
        ai_suggester.suggest_dishes(["卵"], n=1)


def test_admin_api_status_and_suggest(monkeypatch):
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

    dishes = [{
        "name": "目玉焼き",
        "category": "protein",
        "unit": "個", "calories_per_unit": 110,
        "default_portion": 1, "min_portion": 1, "max_portion": 2,
        "uses_ingredients": ["卵"],
        "description": "フライパンで卵を焼く。",
    }]

    class FakeMessages:
        def create(self, **kwargs):
            return _fake_anthropic_response(dishes)

    class FakeClient:
        def __init__(self, api_key=None):
            self.messages = FakeMessages()

    with patch.object(ai_suggester.anthropic, "Anthropic", FakeClient):
        app = admin.create_app()
        app.testing = True
        with app.test_client() as c:
            assert c.get("/api/ai/status").get_json() == {"available": True}
            res = c.post("/api/ai/suggest", json={"ingredients": ["卵"], "n": 1})
            assert res.status_code == 200
            assert res.get_json()["dishes"][0]["name"] == "目玉焼き"

    os.unlink(tmp.name)
