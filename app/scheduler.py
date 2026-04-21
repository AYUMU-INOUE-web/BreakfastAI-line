"""毎朝 7:00 に献立を生成して LINE 配信するスケジューラ。"""
from __future__ import annotations

import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.config import NOTIFY_HOUR, NOTIFY_MINUTE, TIMEZONE
from app.database import session_scope
from app.line_notifier import send_menu
from app.menu_generator import generate_menu, save_history

logger = logging.getLogger(__name__)


def deliver_breakfast() -> None:
    """献立を生成し、履歴に保存し、LINE に配信する。"""
    try:
        with session_scope() as s:
            menu = generate_menu(s)
            save_history(s, menu)
        send_menu(menu)
        logger.info(
            "Delivered menu '%s' (%.0f kcal, fallback=%s)",
            menu.menu_name,
            menu.total_calories,
            menu.is_fallback,
        )
    except Exception:
        logger.exception("Failed to deliver breakfast menu")
        raise


def build_scheduler() -> BackgroundScheduler:
    scheduler = BackgroundScheduler(timezone=TIMEZONE)
    scheduler.add_job(
        deliver_breakfast,
        trigger=CronTrigger(hour=NOTIFY_HOUR, minute=NOTIFY_MINUTE),
        id="daily_breakfast",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    return scheduler
