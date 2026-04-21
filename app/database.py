from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

from app.config import DATABASE_URL
from app.models import Base


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


def init_db() -> None:
    Base.metadata.create_all(_engine)


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
