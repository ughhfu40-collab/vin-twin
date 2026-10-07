"""Durable bounded snapshot store shared by workers on the same SQLite volume."""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import sqlite3
import time

@contextmanager
def connection():
    path=Path(os.getenv('VIN_STATE_PATH', str(Path(__file__).parent/'data/runtime/snapshots.sqlite3')))
    path.parent.mkdir(parents=True,exist_ok=True)
    conn=sqlite3.connect(path,timeout=10)
    try:
        conn.execute('CREATE TABLE IF NOT EXISTS snapshots (id TEXT PRIMARY KEY, created REAL NOT NULL, body TEXT NOT NULL)')
        with conn:
            yield conn
    finally:
        conn.close()

def save_snapshot(snapshot):
    with connection() as conn:
        conn.execute('INSERT OR REPLACE INTO snapshots VALUES (?,?,?)',(snapshot['snapshot_id'],time.time(),json.dumps(snapshot,ensure_ascii=False)))
        conn.execute('DELETE FROM snapshots WHERE id NOT IN (SELECT id FROM snapshots ORDER BY created DESC LIMIT 200)')

def read_snapshot(id):
    with connection() as conn:
        row=conn.execute('SELECT body FROM snapshots WHERE id=?',(id,)).fetchone()
    return json.loads(row[0]) if row else None
