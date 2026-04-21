"""LINE配信テンプレートのレンダリング。

- Jinja2 の SandboxedEnvironment を使ってユーザー編集可能なテンプレートを安全に展開する
- テンプレートの構文/実行エラーは握り潰してデフォルト文面に戻す
- 管理UIのプレビュー用に、実献立が無くてもサンプル値で描画できる
"""
from __future__ import annotations

import logging
from dataclasses import asdict
from datetime import date as date_cls
from typing import Optional

from jinja2 import TemplateError
from jinja2.sandbox import SandboxedEnvironment
from sqlalchemy.orm import Session

from app.menu_generator import GeneratedMenu, MenuItem
from app.models import MessageTemplate

logger = logging.getLogger(__name__)

DEFAULT_TEMPLATE_NAME = "既定テンプレート"
DEFAULT_TEMPLATE_BODY = """🍳 きょうの朝ごはん{% if is_fallback %}(代替メニュー){% endif %}
《{{ menu_name }}》
合計カロリー: {{ total_calories_int }} kcal
─────────────
{% for item in items -%}
・{{ item.name }}: {{ item.portion_display }}{{ item.unit }} ({{ item.calories_int }} kcal)
{% endfor %}
今日も一日がんばろう!"""

AVAILABLE_VARIABLES = [
    ("menu_name", "献立の名前(例: 食パンを中心とした朝ごはん)"),
    ("total_calories", "合計カロリー(小数)"),
    ("total_calories_int", "合計カロリー(整数丸め)"),
    ("is_fallback", "代替メニューかどうか(真偽値)"),
    ("items", "食材のリスト。name / portion / portion_display / unit / calories / calories_int"),
    ("date", "配信日 YYYY-MM-DD"),
]

_env = SandboxedEnvironment(autoescape=False, trim_blocks=False, lstrip_blocks=False)


def _portion_display(value: float) -> str:
    return f"{int(value)}" if value == int(value) else f"{value:g}"


def _build_context(menu: GeneratedMenu, today: Optional[date_cls] = None) -> dict:
    today = today or date_cls.today()
    items = []
    for item in menu.items:
        items.append(
            {
                "name": item.name,
                "portion": item.portion,
                "portion_display": _portion_display(item.portion),
                "unit": item.unit,
                "calories": item.calories,
                "calories_int": round(item.calories),
            }
        )
    return {
        "menu_name": menu.menu_name,
        "total_calories": menu.total_calories,
        "total_calories_int": round(menu.total_calories),
        "is_fallback": menu.is_fallback,
        "items": items,
        "date": today.isoformat(),
    }


def render(body: str, menu: GeneratedMenu, today: Optional[date_cls] = None) -> str:
    """本文を描画。テンプレ不正時は既定文面にフォールバック。"""
    ctx = _build_context(menu, today)
    try:
        return _env.from_string(body).render(**ctx)
    except TemplateError:
        logger.exception("Template render failed; falling back to default template")
        return _env.from_string(DEFAULT_TEMPLATE_BODY).render(**ctx)


def strict_render(body: str, menu: GeneratedMenu, today: Optional[date_cls] = None) -> str:
    """保存前のバリデーション用。構文/実行エラーをそのまま投げる。"""
    ctx = _build_context(menu, today)
    return _env.from_string(body).render(**ctx)


def get_active_body(session: Session) -> str:
    """DBで is_active なテンプレートの本文を返す。無ければ既定文面。"""
    row = (
        session.query(MessageTemplate)
        .filter(MessageTemplate.is_active.is_(True))
        .order_by(MessageTemplate.updated_at.desc())
        .first()
    )
    return row.body if row else DEFAULT_TEMPLATE_BODY


def sample_menu() -> GeneratedMenu:
    """プレビュー用のサンプル献立。"""
    return GeneratedMenu(
        menu_name="食パンを中心とした朝ごはん",
        items=[
            MenuItem(None, "食パン(6枚切)", 1, "枚", 160),
            MenuItem(None, "目玉焼き", 1, "個", 110),
            MenuItem(None, "バナナ", 1, "本", 90),
            MenuItem(None, "牛乳", 200, "ml", 134),
        ],
        total_calories=494,
        is_fallback=False,
    )


def ensure_default_template(session: Session) -> None:
    """一切テンプレが無い場合、既定を1件挿入してアクティブにする。"""
    exists = session.query(MessageTemplate).first()
    if exists is not None:
        return
    session.add(
        MessageTemplate(
            name=DEFAULT_TEMPLATE_NAME,
            body=DEFAULT_TEMPLATE_BODY,
            is_active=True,
        )
    )
