"""SQLite veritabani baglantisi ve oturum yonetimi."""

from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

# backend/data/crash.db
_DATA_DIR = Path(__file__).resolve().parent.parent / "data"
_DATA_DIR.mkdir(parents=True, exist_ok=True)
_GEOM_DIR = _DATA_DIR / "geometries"
_GEOM_DIR.mkdir(parents=True, exist_ok=True)

DB_PATH = _DATA_DIR / "crash.db"
DATABASE_URL = os.environ.get("CRASH_DATABASE_URL", f"sqlite:///{DB_PATH}")

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {},
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def init_db() -> None:
    from . import db_models  # noqa: F401

    Base.metadata.create_all(bind=engine)


def get_geom_dir() -> Path:
    return _GEOM_DIR
