"""SQLite engine and session management.

Single-user, single-file. `check_same_thread=False` is required because FastAPI runs
sync endpoints in a threadpool, and SQLAlchemy hands connections across those threads.
WAL mode lets a read (a search) proceed while a write (an application log) is in flight,
which matters once tailoring and browsing overlap.
"""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    pass


_settings = get_settings()

engine = create_engine(
    f"sqlite:///{_settings.db_path}",
    connect_args={"check_same_thread": False},
    future=True,
)


@event.listens_for(engine, "connect")
def _set_sqlite_pragmas(dbapi_connection, _connection_record) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def init_db() -> None:
    """Create tables. Import models first so they register on Base.metadata."""
    from app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    _migrate_application_workflow_columns()


def _migrate_application_workflow_columns() -> None:
    """Add lightweight workflow columns to databases created before background jobs.

    SimplyApply intentionally has no migration framework: it is a local, single-file
    application. Additive SQLite migrations keep existing trackers intact without asking
    users to recreate their data volume.
    """
    existing = {column["name"] for column in inspect(engine).get_columns("applications")}
    additions = {
        "workflow_status": "VARCHAR(20) NOT NULL DEFAULT 'completed'",
        "workflow_step": "VARCHAR(40) NOT NULL DEFAULT 'completed'",
        "workflow_progress": "INTEGER NOT NULL DEFAULT 100",
        "workflow_detail": "TEXT NOT NULL DEFAULT 'Resume ready.'",
        "workflow_log": "TEXT NOT NULL DEFAULT '[]'",
        "workflow_error": "TEXT",
        "tailoring_json": "TEXT",
        "pdf_error": "TEXT",
        "llm_provider": "VARCHAR(40) NOT NULL DEFAULT ''",
        "llm_model": "VARCHAR(120) NOT NULL DEFAULT ''",
        "llm_requests": "INTEGER NOT NULL DEFAULT 0",
        "input_tokens": "INTEGER NOT NULL DEFAULT 0",
        "cached_input_tokens": "INTEGER NOT NULL DEFAULT 0",
        "cache_write_input_tokens": "INTEGER NOT NULL DEFAULT 0",
        "output_tokens": "INTEGER NOT NULL DEFAULT 0",
        "reasoning_tokens": "INTEGER NOT NULL DEFAULT 0",
        "estimated_cost_usd": "FLOAT",
    }
    with engine.begin() as connection:
        for name, definition in additions.items():
            if name not in existing:
                connection.execute(
                    text(f"ALTER TABLE applications ADD COLUMN {name} {definition}")
                )


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
