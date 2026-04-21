"""LINE Messaging API への配信(2人分対応)。"""
from __future__ import annotations

import logging
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
from app.template_renderer import DEFAULT_TEMPLATE_BODY, render

logger = logging.getLogger(__name__)


def format_breakfast(menus: Sequence[GeneratedMenu], template_body: str | None = None) -> str:
    body = template_body if template_body is not None else DEFAULT_TEMPLATE_BODY
    return render(body, menus)


def send_breakfast(menus: Sequence[GeneratedMenu], template_body: str | None = None) -> None:
    text = format_breakfast(menus, template_body)
    if not LINE_CHANNEL_ACCESS_TOKEN or not LINE_USER_ID:
        logger.warning("LINE credentials are not configured; skipping push.")
        logger.info("Would have sent:\n%s", text)
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
    logger.info("Pushed today's menu to LINE target %s", LINE_USER_ID)
