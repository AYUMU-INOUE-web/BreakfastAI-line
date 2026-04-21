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

# 任意の Basic 認証(共有運用時に推奨)。空なら認証なし
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")
# Vercel Cron の共有秘密。設定した場合は Authorization ヘッダで検証
CRON_SECRET = os.getenv("CRON_SECRET", "")
# 空のDBに対してサンプル食材を自動投入するか(Vercel初回デプロイ向け)
AUTO_SEED = os.getenv("AUTO_SEED", "1") == "1"
# Anthropic Claude API 連携(料理提案機能)。空なら提案 UI は無効化
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
AI_MODEL = os.getenv("AI_MODEL", "claude-opus-4-7")

CALORIE_TARGET = 700
CALORIE_MIN = 650
CALORIE_MAX = 750
HISTORY_DAYS_TO_AVOID = 3
GENERATION_ATTEMPTS = 200
