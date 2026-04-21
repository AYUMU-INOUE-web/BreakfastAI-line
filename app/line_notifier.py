"""LINE Messaging API への配信。

スマホで読みやすいよう、テキストを以下のフォーマットで整形する:
  きょうの朝ごはん (合計 692 kcal)
  ─────────────
  ・食パン(6枚切): 1枚 (160 kcal)
  ・目玉焼き: 1個 (90 kcal)
  ...
"""
from __future__ import annotations

import logging

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


def format_menu(menu: GeneratedMenu) -> str:
    header = "🍳 きょうの朝ごはん"
    if menu.is_fallback:
        header += "(代替メニュー)"
    lines = [
        header,
        f"《{menu.menu_name}》",
        f"合計カロリー: {round(menu.total_calories)} kcal",
        "─────────────",
    ]
    for item in menu.items:
        portion = item.portion
        portion_str = f"{int(portion)}" if portion == int(portion) else f"{portion:g}"
        lines.append(f"・{item.name}: {portion_str}{item.unit} ({round(item.calories)} kcal)")
    lines.append("")
    lines.append("今日も一日がんばろう!")
    return "\n".join(lines)


def send_menu(menu: GeneratedMenu) -> None:
    if not LINE_CHANNEL_ACCESS_TOKEN or not LINE_USER_ID:
        logger.warning("LINE credentials are not configured; skipping push.")
        logger.info("Would have sent:\n%s", format_menu(menu))
        return

    text = format_menu(menu)
    config = Configuration(access_token=LINE_CHANNEL_ACCESS_TOKEN)
    with ApiClient(config) as client:
        api = MessagingApi(client)
        api.push_message(
            PushMessageRequest(
                to=LINE_USER_ID,
                messages=[TextMessage(text=text)],
            )
        )
    logger.info("Pushed today's menu to LINE user %s", LINE_USER_ID)
