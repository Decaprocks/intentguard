"""Persistent local registry plus optimistic concurrency control."""

import json
import sqlite3
from pathlib import Path


class Conflict(ValueError):
    pass


class SQLiteStore:
    def __init__(self, path="data/intentguard.db"):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS intents (resource_id TEXT PRIMARY KEY, body TEXT)"
        )
        self.db.execute("CREATE TABLE IF NOT EXISTS audit (event_id TEXT PRIMARY KEY, body TEXT)")
        self.db.commit()

    def get(self, resource_id):
        row = self.db.execute(
            "SELECT body FROM intents WHERE resource_id=?", (resource_id,)
        ).fetchone()
        return json.loads(row[0]) if row else None

    def save(self, item, expected_version=0):
        item = {**item, "version": expected_version + 1}
        with self.db:
            if expected_version == 0:
                try:
                    self.db.execute(
                        "INSERT INTO intents VALUES (?,?)", (item["resource_id"], json.dumps(item))
                    )
                except sqlite3.IntegrityError as exc:
                    raise Conflict("Record changed; refresh and retry") from exc
            else:
                cursor = self.db.execute(
                    "UPDATE intents SET body=? WHERE resource_id=? AND json_extract(body,'$.version')=?",
                    (json.dumps(item), item["resource_id"], expected_version),
                )
                if cursor.rowcount != 1:
                    raise Conflict("Record changed; refresh and retry")
        return item

    def list(self):
        return [
            json.loads(r[0])
            for r in self.db.execute("SELECT body FROM intents ORDER BY resource_id")
        ]

    def audit(self, event):
        with self.db:
            self.db.execute(
                "INSERT INTO audit VALUES (?,?)", (event["event_id"], json.dumps(event))
            )

    def history(self):
        return [
            json.loads(r[0])
            for r in self.db.execute("SELECT body FROM audit ORDER BY rowid DESC LIMIT 200")
        ]
