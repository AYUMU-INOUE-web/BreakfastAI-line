"""毎朝 7:00 に献立を生成して LINE 配信するスケジューラ(2人分対応)。"""
from __future__ import annotations

import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.config import NOTIFY_HOUR, NOTIFY_MINUTE, TIMEZONE
from app.database import session_scope
from app.line_notifier import send_breakfast
from app.menu_generator import generate_breakfast, save_history

logger = logging.getLogger(__name__)


def deliver_breakfast() -> None:
    try:
        with session_scope() as s:
            menus = generate_breakfast(s)
            save_history(s, menus)
        send_breakfast(menus)
        for m in menus:
            logger.info(
                "Delivered %s: %s (%.0f kcal, fallback=%s)",
                m.profile_name, m.menu_name, m.total_calories, m.is_fallback,
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
