from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from app.config import settings


Base = declarative_base()


def _database_url() -> str:
    if settings.database_url:
        if settings.database_url.startswith("postgres://"):
            return settings.database_url.replace("postgres://", "postgresql+psycopg://", 1)
        if settings.database_url.startswith("postgresql://"):
            return settings.database_url.replace("postgresql://", "postgresql+psycopg://", 1)
        return settings.database_url
    return "sqlite:///./data/processed/kommunenytt.sqlite3"


engine = create_engine(_database_url(), pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    from db import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
