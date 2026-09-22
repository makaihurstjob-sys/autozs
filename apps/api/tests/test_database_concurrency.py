from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from sqlalchemy import create_engine, text

from app.core.database import _engine_options


def test_file_sqlite_handles_more_than_default_pool_capacity(tmp_path):
    url = "sqlite:///" + (tmp_path / "concurrency.db").as_posix()
    engine = create_engine(url, **_engine_options(url))
    barrier = Barrier(24, timeout=5)

    def read(_):
        with engine.connect() as connection:
            barrier.wait()
            return connection.execute(text("SELECT 1")).scalar_one()

    try:
        with ThreadPoolExecutor(max_workers=24) as workers:
            assert list(workers.map(read, range(24))) == [1] * 24
        with engine.connect() as connection:
            assert connection.execute(text("SELECT 1")).scalar_one() == 1
    finally:
        engine.dispose()


def test_memory_and_remote_databases_keep_default_pool():
    assert "poolclass" not in _engine_options("sqlite:///:memory:")
    assert "poolclass" not in _engine_options("sqlite://")
    assert "poolclass" not in _engine_options("postgresql://localhost/test")
