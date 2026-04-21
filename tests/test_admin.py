import os
import tempfile

import pytest


@pytest.fixture
def client(monkeypatch):
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp.name}")
    # 環境変数の反映のためモジュール再読み込み
    import importlib
    from app import config, database, admin
    importlib.reload(config)
    importlib.reload(database)
    importlib.reload(admin)
    app = admin.create_app()
    app.testing = True
    with app.test_client() as c:
        yield c
    os.unlink(tmp.name)


def test_create_list_update_delete_ingredient(client):
    payload = {
        "name": "食パン",
        "category": "main",
        "unit": "枚",
        "calories_per_unit": 160,
        "default_portion": 1,
        "min_portion": 1,
        "max_portion": 2,
    }
    res = client.post("/api/ingredients", json=payload)
    assert res.status_code == 201
    ingredient_id = res.get_json()["id"]

    res = client.get("/api/ingredients")
    assert res.status_code == 200
    assert any(i["name"] == "食パン" for i in res.get_json())

    payload["calories_per_unit"] = 170
    res = client.put(f"/api/ingredients/{ingredient_id}", json=payload)
    assert res.status_code == 200
    assert res.get_json()["calories_per_unit"] == 170

    res = client.delete(f"/api/ingredients/{ingredient_id}")
    assert res.status_code == 204

    res = client.get("/api/ingredients")
    assert res.get_json() == []


def test_invalid_category_rejected(client):
    res = client.post("/api/ingredients", json={
        "name": "x", "category": "dessert", "unit": "g",
        "calories_per_unit": 1, "default_portion": 1, "min_portion": 1, "max_portion": 1,
    })
    assert res.status_code == 400
