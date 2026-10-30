"""Make the `src/` layout importable during tests without an editable install."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest  # noqa: E402


@pytest.fixture()
async def db_env(tmp_path, monkeypatch):
    """Point the app at a throwaway SQLite DB (schemas attached) + fixed master key."""
    from cryptography.fernet import Fernet

    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path}/t.db")
    monkeypatch.setenv("AIA_MASTER_KEY", Fernet.generate_key().decode())
    from aia.config import get_settings

    get_settings.cache_clear()
    from aia.db import base as dbbase

    dbbase.get_engine.cache_clear()
    dbbase.get_sessionmaker.cache_clear()
    from aia.db import models

    engine = dbbase.get_engine()
    # SQLite has no server-side schemas; attach the same file under each
    # logical schema name so models with schema="core" etc. resolve.
    from sqlalchemy import event

    @event.listens_for(engine.sync_engine, "connect")
    def _attach(dbapi_conn, _rec):
        cur = dbapi_conn.cursor()
        for schema in ("core", "business", "health"):
            cur.execute(f"ATTACH DATABASE '{tmp_path}/t.db' AS {schema}")
        cur.close()

    async with engine.begin() as conn:
        await conn.run_sync(models.Base.metadata.create_all)
    yield
    await engine.dispose()
    dbbase.get_engine.cache_clear()
    dbbase.get_sessionmaker.cache_clear()
    get_settings.cache_clear()
