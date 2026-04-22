import os
import random
import tempfile
from datetime import date
from unittest.mock import patch

import pytest

from app import cleaning as cleaning_mod
from app.cleaning import (
    CleaningAssignment,
    DEFAULT_CLEANING_TEMPLATE_BODY,
    generate_assignments,
    render,
    sample_assignments,
    save_history_and_update_points,
)
from app.models import Cleaner, CleaningHistory, CleaningLocation, MessageTemplate


@pytest.fixture(autouse=True)
def _seed_random():
    random.seed(7)


@pytest.fixture
def filled_session(session):
    session.add_all([
        Cleaner(name="太郎", total_points=0, active=True),
        Cleaner(name="花子", total_points=0, active=True),
        Cleaner(name="次郎", total_points=5, active=True),
    ])
    session.add_all([
        CleaningLocation(name="キッチン", points=3, notes="コンロを磨く", active=True),
        CleaningLocation(name="お風呂", points=5, notes="浴槽と床", active=True),
        CleaningLocation(name="トイレ", points=2, notes="便器と床", active=True),
    ])
    session.commit()
    return session


def test_generate_assignments_covers_each_cleaner(filled_session):
    assignments = generate_assignments(filled_session)
    assert len(assignments) == 3
    cleaner_names = {a.cleaner_name for a in assignments}
    assert cleaner_names == {"太郎", "花子", "次郎"}
    # 3 担当者 × 3 場所 → ユニーク割り当てになるはず
    location_names = {a.location_name for a in assignments}
    assert len(location_names) == 3


def test_generate_assignments_cycles_when_cleaners_more_than_locations(session):
    session.add(Cleaner(name="A", active=True))
    session.add(Cleaner(name="B", active=True))
    session.add(Cleaner(name="C", active=True))
    session.add(CleaningLocation(name="玄関", points=1, notes="", active=True))
    session.commit()

    assignments = generate_assignments(session)
    assert len(assignments) == 3
    # 1 箇所しか無いので、全員が玄関になる
    assert all(a.location_name == "玄関" for a in assignments)


def test_generate_assignments_empty_when_no_data(session):
    assert generate_assignments(session) == []


def test_generate_assignments_ignores_inactive(session):
    session.add(Cleaner(name="有効", active=True))
    session.add(Cleaner(name="無効", active=False))
    session.add(CleaningLocation(name="A", points=1, notes="", active=True))
    session.add(CleaningLocation(name="B", points=1, notes="", active=False))
    session.commit()

    assignments = generate_assignments(session)
    assert len(assignments) == 1
    assert assignments[0].cleaner_name == "有効"
    assert assignments[0].location_name == "A"


def test_save_history_increments_cleaner_points(filled_session):
    assignments = [
        CleaningAssignment(1, "太郎", 1, "キッチン", 3, "コンロ"),
        CleaningAssignment(3, "次郎", 2, "お風呂", 5, "浴槽"),
    ]
    save_history_and_update_points(filled_session, assignments, assigned_on=date(2026, 4, 25))
    filled_session.commit()

    taro = filled_session.query(Cleaner).filter_by(name="太郎").one()
    jiro = filled_session.query(Cleaner).filter_by(name="次郎").one()
    hana = filled_session.query(Cleaner).filter_by(name="花子").one()
    assert taro.total_points == 3
    assert jiro.total_points == 10  # 元々 5 + 5
    assert hana.total_points == 0

    rows = filled_session.query(CleaningHistory).all()
    assert len(rows) == 2
    assert {r.cleaner_name for r in rows} == {"太郎", "次郎"}


def test_default_template_renders_each_assignment():
    text = render(DEFAULT_CLEANING_TEMPLATE_BODY, sample_assignments(), today=date(2026, 4, 25))
    assert "今週の掃除当番" in text
    assert "2026-04-25" in text
    assert "太郎" in text and "キッチン" in text
    assert "花子" in text and "お風呂" in text
    assert "5pt" in text
    assert "コンロまわり" in text


def test_render_falls_back_on_bad_template():
    text = render("{{ broken(", sample_assignments())
    assert "今週の掃除当番" in text


def _make_client(monkeypatch, *, with_cron_secret=False):
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp.name}")
    monkeypatch.setenv("AUTO_SEED", "0")
    if with_cron_secret:
        monkeypatch.setenv("CRON_SECRET", "s3cret")
    import importlib
    from app import config, database, admin
    importlib.reload(config)
    importlib.reload(database)
    importlib.reload(admin)
    app = admin.create_app()
    app.testing = True
    return app.test_client(), tmp.name


def test_landing_page(monkeypatch):
    client, path = _make_client(monkeypatch)
    try:
        res = client.get("/")
        assert res.status_code == 200
        html = res.data.decode()
        assert "朝ごはん" in html and "/breakfast" in html
        assert "掃除当番" in html and "/cleaning" in html

        # /breakfast と /cleaning それぞれ 200
        assert client.get("/breakfast").status_code == 200
        assert client.get("/cleaning").status_code == 200
    finally:
        os.unlink(path)


def test_cleaner_and_location_crud(monkeypatch):
    client, path = _make_client(monkeypatch)
    try:
        # cleaner 作成
        r = client.post("/api/cleaners", json={"name": "太郎"})
        assert r.status_code == 201
        cid = r.get_json()["id"]

        # 一覧
        assert any(c["name"] == "太郎" for c in client.get("/api/cleaners").get_json())

        # 更新
        r = client.put(f"/api/cleaners/{cid}", json={"name": "太郎改", "active": False})
        assert r.status_code == 200
        assert r.get_json()["active"] is False

        # 削除
        assert client.delete(f"/api/cleaners/{cid}").status_code == 204
        assert client.get("/api/cleaners").get_json() == []

        # location 作成
        r = client.post(
            "/api/cleaning_locations",
            json={"name": "キッチン", "points": 3, "notes": "コンロ掃除"},
        )
        assert r.status_code == 201
        lid = r.get_json()["id"]

        # points validation
        r = client.post(
            "/api/cleaning_locations",
            json={"name": "x", "points": -1, "notes": ""},
        )
        assert r.status_code == 400

        # 削除
        assert client.delete(f"/api/cleaning_locations/{lid}").status_code == 204
    finally:
        os.unlink(path)


def test_cleaning_template_endpoints(monkeypatch):
    client, path = _make_client(monkeypatch)
    try:
        data = client.get("/api/cleaning_template").get_json()
        assert "今週の掃除当番" in data["body"]
        assert any(v["name"] == "assignments" for v in data["variables"])

        r = client.put("/api/cleaning_template", json={"body": "{{ broken("})
        assert r.status_code == 400

        r = client.put("/api/cleaning_template", json={"body": "hello {{ date }}"})
        assert r.status_code == 200

        preview = client.post(
            "/api/cleaning_template/preview",
            json={"body": "件数 {{ assignments|length }}"},
        ).get_json()
        assert "件数 3" == preview["preview"]

        client.post("/api/cleaning_template/reset")
        assert "今週の掃除当番" in client.get("/api/cleaning_template").get_json()["body"]
    finally:
        os.unlink(path)


def test_cleaning_preview_and_send_now(monkeypatch):
    client, path = _make_client(monkeypatch)
    try:
        # 担当者と場所を投入
        client.post("/api/cleaners", json={"name": "太郎"})
        client.post("/api/cleaners", json={"name": "花子"})
        client.post(
            "/api/cleaning_locations",
            json={"name": "キッチン", "points": 3, "notes": "コンロ"},
        )
        client.post(
            "/api/cleaning_locations",
            json={"name": "お風呂", "points": 5, "notes": "浴槽"},
        )

        prev = client.post("/api/cleaning_preview").get_json()
        assert len(prev["assignments"]) == 2
        assert "今週の掃除当番" in prev["rendered"]

        sent = client.post("/api/cleaning_send_now").get_json()
        assert len(sent["assignments"]) == 2

        # ポイントが加算されている
        cleaners = {c["name"]: c["total_points"] for c in client.get("/api/cleaners").get_json()}
        total = sum(cleaners.values())
        # 2 割り当ての点数合計は 3 + 5 = 8(各担当者は場所の点数を1回もらう)
        assert total == 8
    finally:
        os.unlink(path)


def test_cleaning_cron_requires_bearer(monkeypatch):
    client, path = _make_client(monkeypatch, with_cron_secret=True)
    try:
        # 担当者と場所を投入
        client.post("/api/cleaners", json={"name": "太郎"})
        client.post(
            "/api/cleaning_locations",
            json={"name": "キッチン", "points": 3, "notes": ""},
        )

        assert client.get("/api/cron/cleaning").status_code == 401
        r = client.get("/api/cron/cleaning", headers={"Authorization": "Bearer s3cret"})
        assert r.status_code == 200
        body = r.get_json()
        assert body["sent"] is True
        assert len(body["assignments"]) == 1
    finally:
        os.unlink(path)


def test_cleaning_cron_no_data_returns_sent_false(monkeypatch):
    client, path = _make_client(monkeypatch)
    try:
        r = client.get("/api/cron/cleaning")
        assert r.status_code == 200
        assert r.get_json() == {"sent": False, "assignments": []}
    finally:
        os.unlink(path)
