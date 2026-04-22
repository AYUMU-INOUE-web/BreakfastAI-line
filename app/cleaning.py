"""掃除当番機能。

- 担当者(Cleaner)と掃除場所(CleaningLocation)を管理する
- 毎週土曜 8:00 JST に、担当者ごとにランダムに掃除場所を割り当てて LINE 配信
- 担当者ごとに掃除場所の点数を加算していく
- LINE の文面はユーザー編集可能なテンプレートに委譲
"""
from __future__ import annotations

import logging
import random
from dataclasses import dataclass
from datetime import date as date_cls
from types import SimpleNamespace
from typing import Optional, Sequence

from jinja2 import TemplateError
from jinja2.sandbox import SandboxedEnvironment
from sqlalchemy.orm import Session

from app.line_notifier import send_line_text
from app.models import Cleaner, CleaningHistory, CleaningLocation, MessageTemplate

logger = logging.getLogger(__name__)

DEFAULT_CLEANING_TEMPLATE_NAME = "既定テンプレート (掃除)"
DEFAULT_CLEANING_TEMPLATE_BODY = """🧹 今週の掃除当番 ({{ date }})
{% for a in assignments %}
━━━━━━━━━━━━━
【{{ a.cleaner_name }}】
📍 {{ a.location_name }} ({{ a.points }}pt)
{%- if a.notes %}
やること: {{ a.notes }}
{%- endif %}
{% endfor %}

今週もよろしくお願いします!"""

AVAILABLE_VARIABLES = [
    ("date", "配信日 YYYY-MM-DD"),
    ("assignments", "割り当てのリスト"),
    ("assignments[i].cleaner_name", "担当者の名前"),
    ("assignments[i].location_name", "掃除場所の名前"),
    ("assignments[i].points", "その場所の点数"),
    ("assignments[i].notes", "その場所の備考(実施内容)"),
]

_env = SandboxedEnvironment(autoescape=False, trim_blocks=False, lstrip_blocks=False)


@dataclass
class CleaningAssignment:
    cleaner_id: int
    cleaner_name: str
    location_id: int
    location_name: str
    points: int
    notes: str

    def to_payload(self) -> dict:
        return {
            "cleaner_id": self.cleaner_id,
            "cleaner_name": self.cleaner_name,
            "location_id": self.location_id,
            "location_name": self.location_name,
            "points": self.points,
            "notes": self.notes,
        }


def _build_context(
    assignments: Sequence[CleaningAssignment],
    today: Optional[date_cls] = None,
) -> dict:
    today = today or date_cls.today()
    return {
        "date": today.isoformat(),
        "assignments": [
            SimpleNamespace(
                cleaner_name=a.cleaner_name,
                location_name=a.location_name,
                points=a.points,
                notes=a.notes,
            )
            for a in assignments
        ],
    }


def render(body: str, assignments: Sequence[CleaningAssignment], today: Optional[date_cls] = None) -> str:
    ctx = _build_context(assignments, today)
    try:
        return _env.from_string(body).render(**ctx)
    except TemplateError:
        logger.exception("Cleaning template render failed; falling back to default template")
        return _env.from_string(DEFAULT_CLEANING_TEMPLATE_BODY).render(**ctx)


def strict_render(body: str, assignments: Sequence[CleaningAssignment], today: Optional[date_cls] = None) -> str:
    ctx = _build_context(assignments, today)
    return _env.from_string(body).render(**ctx)


def sample_assignments() -> list[CleaningAssignment]:
    """プレビュー用サンプル。"""
    return [
        CleaningAssignment(1, "太郎", 1, "キッチン", 3, "コンロまわりとシンクを磨く"),
        CleaningAssignment(2, "花子", 2, "お風呂", 5, "浴槽と床、排水口まで"),
        CleaningAssignment(3, "次郎", 3, "トイレ", 2, "便器と床、壁も軽く"),
    ]


def ensure_default_cleaning_template(session: Session) -> None:
    exists = (
        session.query(MessageTemplate)
        .filter(MessageTemplate.kind == "cleaning")
        .first()
    )
    if exists is not None:
        return
    session.add(
        MessageTemplate(
            name=DEFAULT_CLEANING_TEMPLATE_NAME,
            body=DEFAULT_CLEANING_TEMPLATE_BODY,
            is_active=True,
            kind="cleaning",
        )
    )


def get_active_cleaning_body(session: Session) -> str:
    row = (
        session.query(MessageTemplate)
        .filter(MessageTemplate.kind == "cleaning")
        .filter(MessageTemplate.is_active.is_(True))
        .order_by(MessageTemplate.updated_at.desc())
        .first()
    )
    return row.body if row else DEFAULT_CLEANING_TEMPLATE_BODY


def generate_assignments(
    session: Session,
    today: Optional[date_cls] = None,
    *,
    shuffle: bool = True,
) -> list[CleaningAssignment]:
    """有効な担当者に、有効な掃除場所をランダムに割り当てる。

    - 担当者が 0 人 or 場所が 0 件 の場合は空リストを返す
    - 場所は「重複なし優先」で割り当てるが、担当者 > 場所 の場合は循環利用する
    - 重複なし優先のためシャッフルしてから順番に割り当てる
    """
    cleaners = (
        session.query(Cleaner)
        .filter(Cleaner.active.is_(True))
        .order_by(Cleaner.id)
        .all()
    )
    locations = (
        session.query(CleaningLocation)
        .filter(CleaningLocation.active.is_(True))
        .order_by(CleaningLocation.id)
        .all()
    )
    if not cleaners or not locations:
        return []

    loc_pool = list(locations)
    if shuffle:
        random.shuffle(loc_pool)
    cleaner_pool = list(cleaners)
    if shuffle:
        random.shuffle(cleaner_pool)

    assignments: list[CleaningAssignment] = []
    for idx, cleaner in enumerate(cleaner_pool):
        loc = loc_pool[idx % len(loc_pool)]
        assignments.append(
            CleaningAssignment(
                cleaner_id=cleaner.id,
                cleaner_name=cleaner.name,
                location_id=loc.id,
                location_name=loc.name,
                points=loc.points,
                notes=loc.notes,
            )
        )
    return assignments


def save_history_and_update_points(
    session: Session,
    assignments: Sequence[CleaningAssignment],
    assigned_on: Optional[date_cls] = None,
) -> list[CleaningHistory]:
    assigned_on = assigned_on or date_cls.today()
    records: list[CleaningHistory] = []
    for a in assignments:
        # 点数加算
        cleaner = session.get(Cleaner, a.cleaner_id)
        if cleaner is not None:
            cleaner.total_points = (cleaner.total_points or 0) + int(a.points)
        record = CleaningHistory(
            assigned_on=assigned_on,
            cleaner_id=a.cleaner_id,
            cleaner_name=a.cleaner_name,
            location_id=a.location_id,
            location_name=a.location_name,
            points=a.points,
            notes=a.notes,
        )
        session.add(record)
        records.append(record)
    session.flush()
    return records


def send_cleaning(
    assignments: Sequence[CleaningAssignment],
    template_body: str | None = None,
) -> str:
    body = template_body if template_body is not None else DEFAULT_CLEANING_TEMPLATE_BODY
    text = render(body, assignments)
    send_line_text(text, context="cleaning")
    return text
