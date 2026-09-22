from collections.abc import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import make_url
from sqlalchemy.pool import NullPool
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings


class Base(DeclarativeBase):
    pass


def _connect_args(url: str) -> dict:
    if url.startswith("sqlite"):
        return {"check_same_thread": False}
    return {}


def _engine_options(url: str) -> dict:
    options = {"connect_args": _connect_args(url)}
    parsed = make_url(url)
    if parsed.get_backend_name() == "sqlite" and parsed.database not in (None, "", ":memory:"):
        # File SQLite connections are inexpensive. A small QueuePool can strand
        # request workers waiting for connections held by other requests.
        # Close each connection on return; retain SQLite's default memory pool.
        options["poolclass"] = NullPool
    return options


settings = get_settings()
engine = create_engine(settings.database_url, **_engine_options(settings.database_url))


if settings.database_url.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def _configure_sqlite(connection, _record) -> None:
        cursor = connection.cursor()
        try:
            # WAL lets dashboard reads and small metric updates continue while
            # background workers are using the database. The busy timeout
            # turns brief writer overlap into a retry instead of an immediate
            # `database is locked` failure.
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA busy_timeout=15000")
            cursor.execute("PRAGMA synchronous=NORMAL")
        finally:
            cursor.close()

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
