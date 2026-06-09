from __future__ import annotations

from typing import Iterator
from functools import lru_cache
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from contextlib import contextmanager
from sqlalchemy.orm import Session, sessionmaker

from hcc_common.config import get_settings


@lru_cache
def get_engine() -> Engine:
    settings = get_settings()
    return create_engine(
        settings.db.url,
        pool_size=10,
        max_overflow=20,
        pool_pre_ping=True,      # survive Postgres restarts / idle drops
        pool_recycle=1800,
        future=True,
    )

@lru_cache
def get_sessionmaker() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), expire_on_commit=False, future=True)

@contextmanager
def session_scope() -> Iterator[Session]:
    session = get_sessionmaker()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()