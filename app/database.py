from contextlib import contextmanager
import logging

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

from app.config import DATABASE_URL
from app.models import Base

logger = logging.getLogger(__name__)


def _normalize_url(url: str) -> str:
    # Neon/Heroku 等が返す postgres:// を SQLAlchemy 向けに正規化
    if url.startswith("postgres://"):
        return "postgresql://" + url[len("postgres://"):]
    return url


_url = _normalize_url(DATABASE_URL)
_engine_kwargs: dict = {"future": True}
if _url.startswith("postgresql"):
    # Serverless(Vercel)で毎呼び出し新プロセスになることを想定し
    # 接続はリクエストごとに捨てる(NullPool)
    _engine_kwargs["poolclass"] = NullPool
    _engine_kwargs["pool_pre_ping"] = True

_engine = create_engine(_url, **_engine_kwargs)
SessionLocal = sessionmaker(bind=_engine, autoflush=False, autocommit=False, future=True)


def _apply_simple_migrations() -> None:
    """Alembic を使わない軽量な列追加マイグレーション。冪等。"""
    try:
        inspector = inspect(_engine)
        names = inspector.get_table_names()
        if "menu_history" in names:
            cols = {c["name"] for c in inspector.get_columns("menu_history")}
            if "profile_name" not in cols:
                with _engine.begin() as conn:
                    conn.execute(text(
                        "ALTER TABLE menu_history ADD COLUMN profile_name VARCHAR(64)"
                    ))
                logger.info("Added profile_name column to menu_history")
        if "message_templates" in names:
            cols = {c["name"] for c in inspector.get_columns("message_templates")}
            if "kind" not in cols:
                with _engine.begin() as conn:
                    conn.execute(text(
                        "ALTER TABLE message_templates ADD COLUMN kind VARCHAR(32)"
                    ))
                    conn.execute(text(
                        "UPDATE message_templates SET kind = 'breakfast' WHERE kind IS NULL"
                    ))
                logger.info("Added kind column to message_templates")
    except Exception:
        logger.exception("Simple migration failed; continuing")


def init_db() -> None:
    Base.metadata.create_all(_engine)
    _apply_simple_migrations()


@contextmanager
def session_scope():
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
