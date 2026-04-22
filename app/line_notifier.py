"""LINE Messaging API への配信。

朝ごはんの文面はテンプレートを使わず、AI が出力した `line_text` をそのまま
結合して送る。ルールベース献立や空の fallback メニューは、Python で
シンプルに整形する(テンプレート編集なし)。
"""
from __future__ import annotations

import logging
from datetime import date as date_cls
from typing import Sequence

from linebot.v3.messaging import (
    ApiClient,
    Configuration,
    MessagingApi,
    PushMessageRequest,
    TextMessage,
)

from app.config import LINE_CHANNEL_ACCESS_TOKEN, LINE_USER_ID
from app.menu_generator import GeneratedMenu

logger = logging.getLogger(__name__)

SEPARATOR = "━━━━━━━━━━━━━"


def _portion_display(value: float) -> str:
    return f"{int(value)}" if value == int(value) else f"{value:g}"


def _format_rule_based_block(menu: GeneratedMenu) -> str:
    header = f"【{menu.profile_name}】" + (" (代替)" if menu.is_fallback else "")
    lines: list[str] = [header, f"《{menu.menu_name}》"]
    if menu.items:
        lines.append(f"合計 {round(menu.total_calories)} kcal")
        for item in menu.items:
            lines.append(
                f"・{item.name}: {_portion_display(item.portion)}{item.unit}"
                f" ({round(item.calories)} kcal)"
            )
    return "\n".join(lines)


def format_breakfast(menus: Sequence[GeneratedMenu]) -> str:
    today = date_cls.today()
    parts: list[str] = [f"🍳 きょうの朝ごはん ({today.isoformat()})"]
    for menu in menus:
        parts.append("")
        parts.append(SEPARATOR)
        if menu.line_text:
            # AI が用意した LINE テキストをそのまま使う(テンプレート不使用)
            parts.append(menu.line_text.strip())
        else:
            parts.append(_format_rule_based_block(menu))
    parts.append("")
    parts.append("今日も一日がんばろう!")
    return "\n".join(parts)


def send_line_text(text: str, context: str = "") -> None:
    """プッシュ通知の汎用関数。宛先は LINE_USER_ID 固定。"""
    if not LINE_CHANNEL_ACCESS_TOKEN or not LINE_USER_ID:
        logger.warning("LINE credentials are not configured; skipping push.")
        logger.info("Would have sent (%s):\n%s", context or "line", text)
        return

    config = Configuration(access_token=LINE_CHANNEL_ACCESS_TOKEN)
    with ApiClient(config) as client:
        api = MessagingApi(client)
        api.push_message(
            PushMessageRequest(
                to=LINE_USER_ID,
                messages=[TextMessage(text=text)],
            )
        )
    logger.info("Pushed %s to LINE target %s", context or "message", LINE_USER_ID)


def send_breakfast(menus: Sequence[GeneratedMenu]) -> None:
    send_line_text(format_breakfast(menus), context="breakfast")
