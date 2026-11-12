"""Koneksi database (SQLAlchemy 2.0)."""
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings

_connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}

engine = create_engine(settings.database_url, connect_args=_connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    """Base class untuk semua model ORM."""


def get_db() -> Iterator[Session]:
    """Dependency FastAPI: satu session per request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
