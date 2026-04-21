import os
import tempfile

import pytest


@pytest.fixture
def client(monkeypatch):
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp.name}")
    monkeypatch.setenv("AUTO_SEED", "0")
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


def test_template_get_returns_default_on_first_access(client):
    res = client.get("/api/template")
    assert res.status_code == 200
    data = res.get_json()
    assert "きょうの朝ごはん" in data["body"]
    assert any(v["name"] == "items" for v in data["variables"])


def test_template_update_and_fetch(client):
    body = "テスト 合計 {{ total_calories_int }} kcal"
    res = client.put("/api/template", json={"body": body})
    assert res.status_code == 200
    assert res.get_json()["body"] == body

    res = client.get("/api/template")
    assert res.get_json()["body"] == body


def test_template_update_rejects_invalid_syntax(client):
    res = client.put("/api/template", json={"body": "{{ broken("})
    assert res.status_code == 400


def test_template_update_rejects_empty_body(client):
    res = client.put("/api/template", json={"body": "   "})
    assert res.status_code == 400


def test_template_preview_uses_supplied_body(client):
    res = client.post(
        "/api/template/preview",
        json={"body": "合計 {{ total_calories_int }}kcal"},
    )
    assert res.status_code == 200
    assert "合計 494kcal" == res.get_json()["preview"]


def test_template_reset_restores_default(client):
    client.put("/api/template", json={"body": "変更済み"})
    res = client.post("/api/template/reset")
    assert res.status_code == 200
    body = client.get("/api/template").get_json()["body"]
    assert "きょうの朝ごはん" in body


@pytest.fixture
def client_with_cron_secret(monkeypatch):
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp.name}")
    monkeypatch.setenv("AUTO_SEED", "1")
    monkeypatch.setenv("CRON_SECRET", "s3cret")
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


def test_cron_rejects_without_bearer(client_with_cron_secret):
    res = client_with_cron_secret.get("/api/cron/send")
    assert res.status_code == 401


def test_cron_accepts_correct_bearer(client_with_cron_secret):
    res = client_with_cron_secret.get(
        "/api/cron/send", headers={"Authorization": "Bearer s3cret"}
    )
    assert res.status_code == 200
    assert res.get_json()["sent"] is True


def test_basic_auth_required_when_password_set(monkeypatch):
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp.name}")
    monkeypatch.setenv("AUTO_SEED", "0")
    monkeypatch.setenv("ADMIN_PASSWORD", "letmein")
    import importlib
    from app import config, database, admin
    importlib.reload(config)
    importlib.reload(database)
    importlib.reload(admin)
    app = admin.create_app()
    app.testing = True
    with app.test_client() as c:
        assert c.get("/api/ingredients").status_code == 401
        import base64
        creds = base64.b64encode(b"x:letmein").decode()
        assert c.get(
            "/api/ingredients", headers={"Authorization": f"Basic {creds}"}
        ).status_code == 200
    os.unlink(tmp.name)
