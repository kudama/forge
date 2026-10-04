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
        if version not in {0, 1, 2}:
            self.close()
            raise RuntimeError("Unsupported database schema version")
        self.db.execute("PRAGMA journal_mode=DELETE")
        self.db.execute("PRAGMA secure_delete=ON")
        self.db.execute("""CREATE TABLE IF NOT EXISTS tasks (
            id TEXT PRIMARY KEY, owner TEXT NOT NULL, agent TEXT NOT NULL,
            status TEXT NOT NULL, created REAL NOT NULL, updated REAL NOT NULL,
            result TEXT, error TEXT, audit TEXT NOT NULL DEFAULT '[]')""")
        self.db.execute("""CREATE TABLE IF NOT EXISTS work_orders (
            owner TEXT NOT NULL, order_id TEXT NOT NULL, task_id TEXT NOT NULL UNIQUE,
            order_json TEXT, sources_json TEXT, PRIMARY KEY(owner, order_id))""")
        self.db.execute("PRAGMA user_version=2")
        self.db.execute("UPDATE tasks SET status='failed', error='interrupted', updated=? WHERE status IN ('queued','running')", (time.time(),))
        self.db.commit()

    def create(self, owner, agent, binding=None):
        task_id, now = uuid4().hex, time.time()
        self.db.execute("INSERT INTO tasks (id,owner,agent,status,created,updated) VALUES (?,?,?,'queued',?,?)", (task_id, owner, agent, now, now))
        try:
            if binding is not None:
                order, sources = binding
                self.db.execute("INSERT INTO work_orders VALUES (?,?,?,?,?)",
                    (owner,order['work_order_id'],task_id,json.dumps(order),json.dumps(sources)))
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        return task_id

    def get(self, task_id):
        row = self.db.execute("SELECT id,owner,agent,status,created,updated,result,error,audit FROM tasks WHERE id=?", (task_id,)).fetchone()
        if not row:
            return None
        result = dict(zip(["id", "owner", "agent", "status", "created", "updated", "result", "error", "audit"], row))
        result["audit"] = json.loads(result["audit"])
        binding = self.db.execute('SELECT order_json FROM work_orders WHERE task_id=?',(task_id,)).fetchone()
        if binding and binding[0]:
            order = json.loads(binding[0])
            result['work_order_id'] = order['work_order_id']
            result['snapshot'] = order['source']
            result['validation'] = {'structure_valid':result['status']=='succeeded',
                                    'source_valid':result['status']=='succeeded','review_required':True}
        return result

    def has_order(self, owner, order_id):
        return self.db.execute('SELECT 1 FROM work_orders WHERE owner=? AND order_id=?',(owner,order_id)).fetchone() is not None

    def forget_snapshot(self, task_id):
        self.db.execute('UPDATE work_orders SET order_json=NULL,sources_json=NULL WHERE task_id=?',(task_id,))

    def update(self, task_id, status, result=None, error=None, audit=None):
        self.db.execute("UPDATE tasks SET status=?,updated=?,result=?,error=?,audit=? WHERE id=? AND status IN ('queued','running')", (status, time.time(), result, error, json.dumps(audit or []), task_id))
        self.db.commit()

    def close(self):
        self.db.close()
        self.lock.close()
