"""LINE配信テンプレートのレンダリング(2人分対応)。

- Jinja2 の SandboxedEnvironment を使う
- テンプレートの構文/実行エラーは握り潰してデフォルト文面に戻す
- プレビュー用にサンプル献立を持つ
"""
from __future__ import annotations

import logging
from datetime import date as date_cls
from types import SimpleNamespace
from typing import Optional, Sequence

from jinja2 import TemplateError
from jinja2.sandbox import SandboxedEnvironment
from sqlalchemy.orm import Session

from app.menu_generator import GeneratedMenu, MenuItem
from app.models import MessageTemplate

logger = logging.getLogger(__name__)

DEFAULT_TEMPLATE_NAME = "既定テンプレート"
DEFAULT_TEMPLATE_BODY = """🍳 きょうの朝ごはん ({{ date }})
{% for menu in menus %}
━━━━━━━━━━━━━
【{{ menu.profile_name }}】{% if menu.is_fallback %} (代替){% endif %}
《{{ menu.menu_name }}》
合計 {{ menu.total_calories_int }} kcal
{% for item in menu.items -%}
・{{ item.name }}: {{ item.portion_display }}{{ item.unit }} ({{ item.calories_int }} kcal)
{% endfor %}
{%- endfor %}
今日も一日がんばろう!"""

AVAILABLE_VARIABLES = [
    ("date", "配信日 YYYY-MM-DD"),
    ("menus", "献立のリスト(プロファイル単位)"),
    ("menus[i].profile_name", "プロファイル名(例: 700kcal)"),
    ("menus[i].menu_name", "献立の名前"),
    ("menus[i].total_calories_int", "合計カロリー(整数)"),
    ("menus[i].is_fallback", "代替メニューかどうか"),
    ("menus[i].items", "食材のリスト。name / portion / portion_display / unit / calories / calories_int"),
]

_env = SandboxedEnvironment(autoescape=False, trim_blocks=False, lstrip_blocks=False)


def _portion_display(value: float) -> str:
    return f"{int(value)}" if value == int(value) else f"{value:g}"


def _item_ns(item: MenuItem) -> SimpleNamespace:
    return SimpleNamespace(
        name=item.name,
        portion=item.portion,
        portion_display=_portion_display(item.portion),
        unit=item.unit,
        calories=item.calories,
        calories_int=round(item.calories),
    )


def _menu_ns(menu: GeneratedMenu) -> SimpleNamespace:
    # SimpleNamespace を使うのは、dict だと `.items` が組み込みの dict.items() と
    # 衝突して Jinja の属性アクセスが壊れるため。
    return SimpleNamespace(
        profile_name=menu.profile_name,
        menu_name=menu.menu_name,
        total_calories=menu.total_calories,
        total_calories_int=round(menu.total_calories),
        is_fallback=menu.is_fallback,
        items=[_item_ns(item) for item in menu.items],
    )


def _build_context(menus: Sequence[GeneratedMenu], today: Optional[date_cls] = None) -> dict:
    today = today or date_cls.today()
    return {
        "date": today.isoformat(),
        "menus": [_menu_ns(m) for m in menus],
    }


def render(body: str, menus: Sequence[GeneratedMenu], today: Optional[date_cls] = None) -> str:
    ctx = _build_context(menus, today)
    try:
        return _env.from_string(body).render(**ctx)
    except TemplateError:
        logger.exception("Template render failed; falling back to default template")
        return _env.from_string(DEFAULT_TEMPLATE_BODY).render(**ctx)


def strict_render(body: str, menus: Sequence[GeneratedMenu], today: Optional[date_cls] = None) -> str:
    ctx = _build_context(menus, today)
    return _env.from_string(body).render(**ctx)


def get_active_body(session: Session) -> str:
    row = (
        session.query(MessageTemplate)
        .filter(MessageTemplate.is_active.is_(True))
        .order_by(MessageTemplate.updated_at.desc())
        .first()
    )
    return row.body if row else DEFAULT_TEMPLATE_BODY


def sample_menus() -> list[GeneratedMenu]:
    """プレビュー用サンプル。2プロファイルを返す。"""
    return [
        GeneratedMenu(
            profile_name="700kcal",
            menu_name="食パンを中心とした朝ごはん",
            items=[
                MenuItem(None, "食パン(6枚切)", 1, "枚", 160),
                MenuItem(None, "目玉焼き", 1, "個", 110),
                MenuItem(None, "バナナ", 1, "本", 90),
                MenuItem(None, "牛乳", 200, "ml", 134),
            ],
            total_calories=494,
        ),
        GeneratedMenu(
            profile_name="300kcal",
            menu_name="ヨーグルトを中心とした朝ごはん",
            items=[
                MenuItem(None, "食パン(6枚切)", 1, "枚", 160),
                MenuItem(None, "ヨーグルト(無糖)", 100, "g", 62),
                MenuItem(None, "コーヒー(ブラック)", 150, "ml", 6),
            ],
            total_calories=228,
        ),
    ]


def ensure_default_template(session: Session) -> None:
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
