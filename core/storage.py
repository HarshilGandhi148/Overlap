"""Primary Watch/Play source catalogs. Shared decisions remain in session state."""
from contextlib import contextmanager
import json
import os
import sqlite3
from core.contracts import CategorySearchError
from core.services import ROOT


class Store:
    def __init__(self, url=None, path=None):
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env", override=False)
        self.url = os.getenv("DATABASE_URL", "") if url is None else url
        self.path = path or ROOT / ".runtime" / "overlap.sqlite3"

    @property
    def label(self):
        return "PostgreSQL" if self.url else "SQLite local demo"

    @contextmanager
    def connection(self):
        conn = None
        try:
            if self.url:
                import psycopg
                conn = psycopg.connect(self.url, connect_timeout=3)
            else:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                conn = sqlite3.connect(self.path)
            conn.execute("CREATE TABLE IF NOT EXISTS overlap_catalog (mode TEXT NOT NULL, id TEXT NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(mode,id))")
            yield conn
            conn.commit()
        except Exception as exc:
            if conn:
                conn.rollback()
            raise CategorySearchError("Saved storage is unavailable. Check DATABASE_URL or the local .runtime folder. Existing data was retained.") from exc
        finally:
            if conn:
                conn.close()

    def sql(self, statement):
        return statement.replace("?", "%s") if self.url else statement

    def upsert_catalog(self, mode, records):
        with self.connection() as conn:
            for record in records:
                conn.execute(self.sql("INSERT INTO overlap_catalog VALUES (?,?,?) ON CONFLICT(mode,id) DO UPDATE SET payload=excluded.payload"),
                             (mode, str(record["id"]), json.dumps(record)))

    def catalog(self, mode):
        with self.connection() as conn:
            rows = conn.execute(self.sql("SELECT payload FROM overlap_catalog WHERE mode=? ORDER BY id"), (mode,)).fetchall()
        return [json.loads(row[0]) for row in rows]
