"""Local SQLite compare-and-swap state. No simulator calls or raw response storage."""
import json
from pathlib import Path
import sqlite3
from contextlib import contextmanager


class StateConflict(RuntimeError):
    pass


class ReviewStateStore:
    def __init__(self, path, *, scope):
        if not isinstance(scope, str) or not scope.strip():
            raise ValueError('Explicit team/practice state scope required')
        self.path, self.scope = Path(path), scope
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS review_state (scope TEXT PRIMARY KEY, revision INTEGER NOT NULL, payload TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS review_audit (sequence INTEGER PRIMARY KEY, scope TEXT NOT NULL, record TEXT NOT NULL)')

    @contextmanager
    def _connect(self):
        db = sqlite3.connect(self.path, timeout=5)
        try:
            with db:
                yield db
        finally:
            db.close()

    def load(self):
        with self._connect() as db:
            row = db.execute('SELECT revision, payload FROM review_state WHERE scope=?', (self.scope,)).fetchone()
        if row is None:
            return 0, {}
        revision, raw = row
        state = json.loads(raw)
        if not isinstance(state, dict):
            raise ValueError('Stored state is not an object; do not reset automatically')
        return revision, state

    def save(self, expected_revision, state):
        raw = json.dumps(state, ensure_ascii=False, sort_keys=True, allow_nan=False)
        with self._connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT revision FROM review_state WHERE scope=?', (self.scope,)).fetchone()
            actual = row[0] if row else 0
            if actual != expected_revision:
                raise StateConflict('Review state changed in another controller; reload before sending')
            revision = actual + 1
            db.execute('INSERT INTO review_state(scope,revision,payload) VALUES(?,?,?) '
                       'ON CONFLICT(scope) DO UPDATE SET revision=excluded.revision,payload=excluded.payload',
                       (self.scope, revision, raw))
        return revision

    def append_audit(self, record):
        raw = json.dumps(record, ensure_ascii=False, sort_keys=True, allow_nan=False)
        with self._connect() as db:
            db.execute('INSERT INTO review_audit(scope,record) VALUES(?,?)', (self.scope, raw))

    def audit_records(self):
        with self._connect() as db:
            rows = db.execute('SELECT sequence,record FROM review_audit WHERE scope=? ORDER BY sequence', (self.scope,)).fetchall()
        return [dict(sequence=sequence, **json.loads(raw)) for sequence, raw in rows]
