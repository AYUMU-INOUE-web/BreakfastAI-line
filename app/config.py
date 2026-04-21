import os
from dotenv import load_dotenv

load_dotenv()

LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")
LINE_USER_ID = os.getenv("LINE_USER_ID", "")

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///breakfast.db")

NOTIFY_HOUR = int(os.getenv("NOTIFY_HOUR", "7"))
NOTIFY_MINUTE = int(os.getenv("NOTIFY_MINUTE", "0"))
TIMEZONE = os.getenv("TIMEZONE", "Asia/Tokyo")

ADMIN_HOST = os.getenv("ADMIN_HOST", "0.0.0.0")
ADMIN_PORT = int(os.getenv("ADMIN_PORT", "5000"))

CALORIE_TARGET = 700
CALORIE_MIN = 650
CALORIE_MAX = 750
HISTORY_DAYS_TO_AVOID = 3
GENERATION_ATTEMPTS = 200
