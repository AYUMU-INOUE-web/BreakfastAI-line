"""アプリのエントリーポイント。

使い方:
  python main.py serve     # 管理 UI + スケジューラを常駐起動
  python main.py send-now  # 献立を生成し LINE に送る (cron からも利用可)
  python main.py seed      # サンプル食材を投入
"""
from __future__ import annotations

import argparse
import logging
import sys

from app.admin import create_app
from app.config import ADMIN_HOST, ADMIN_PORT
from app.database import init_db
from app.scheduler import build_scheduler, deliver_breakfast


def _serve() -> None:
    app = create_app()
    scheduler = build_scheduler()
    scheduler.start()
    try:
        app.run(host=ADMIN_HOST, port=ADMIN_PORT, use_reloader=False)
    finally:
        scheduler.shutdown(wait=False)


def _send_now() -> None:
    init_db()
    deliver_breakfast()


def _seed() -> None:
    from app.seed_data import seed_default_ingredients

    init_db()
    inserted = seed_default_ingredients()
    print(f"Seeded {inserted} ingredients.")


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    parser = argparse.ArgumentParser(description="Breakfast menu LINE notifier")
    parser.add_argument("command", choices=["serve", "send-now", "seed"])
    args = parser.parse_args(argv)

    if args.command == "serve":
        _serve()
    elif args.command == "send-now":
        _send_now()
    elif args.command == "seed":
        _seed()
    return 0


if __name__ == "__main__":
    sys.exit(main())
