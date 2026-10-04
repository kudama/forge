import fcntl
import json
import os
import sqlite3
import time
from pathlib import Path
from uuid import uuid4

TERMINAL = {"succeeded", "failed", "cancelled"}


class Store:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        # One process owns the queue; prevent two workers recovering each other's tasks.
        self.lock = open(str(path) + ".lock", "a")
        os.chmod(self.lock.name, 0o600)
        try:
            fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.lock.close()
            raise RuntimeError("Database already owned by another controller") from None
        self.db = sqlite3.connect(path)
        os.chmod(path, 0o600)
        version = self.db.execute("PRAGMA user_version").fetchone()[0]
        if version not in {0, 1}:
            self.close()
            raise RuntimeError("Unsupported database schema version")
        self.db.execute("PRAGMA journal_mode=DELETE")
        self.db.execute("""CREATE TABLE IF NOT EXISTS tasks (
            id TEXT PRIMARY KEY, owner TEXT NOT NULL, agent TEXT NOT NULL,
            status TEXT NOT NULL, created REAL NOT NULL, updated REAL NOT NULL,
            result TEXT, error TEXT, audit TEXT NOT NULL DEFAULT '[]')""")
        self.db.execute("PRAGMA user_version=1")
        self.db.execute("UPDATE tasks SET status='failed', error='interrupted', updated=? WHERE status IN ('queued','running')", (time.time(),))
        self.db.commit()

    def create(self, owner, agent):
        task_id, now = uuid4().hex, time.time()
        self.db.execute("INSERT INTO tasks (id,owner,agent,status,created,updated) VALUES (?,?,?,'queued',?,?)", (task_id, owner, agent, now, now))
        self.db.commit()
        return task_id

    def get(self, task_id):
        row = self.db.execute("SELECT id,owner,agent,status,created,updated,result,error,audit FROM tasks WHERE id=?", (task_id,)).fetchone()
        if not row:
            return None
        result = dict(zip(["id", "owner", "agent", "status", "created", "updated", "result", "error", "audit"], row))
        result["audit"] = json.loads(result["audit"])
        return result

    def update(self, task_id, status, result=None, error=None, audit=None):
        self.db.execute("UPDATE tasks SET status=?,updated=?,result=?,error=?,audit=? WHERE id=? AND status IN ('queued','running')", (status, time.time(), result, error, json.dumps(audit or []), task_id))
        self.db.commit()

    def close(self):
        self.db.close()
        self.lock.close()
