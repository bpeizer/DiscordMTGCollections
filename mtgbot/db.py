"""SQLite storage. Collections are stored per server (guild), per member."""
import sqlite3
import time
from typing import Iterable

from .names import front_face, normalize

SCHEMA = """
CREATE TABLE IF NOT EXISTS links (
    guild_id    INTEGER NOT NULL,
    user_id     INTEGER NOT NULL,
    source      TEXT NOT NULL,       -- 'moxfield', 'archidekt' or 'csv'
    url         TEXT,
    last_synced REAL,
    last_error  TEXT,
    PRIMARY KEY (guild_id, user_id)
);
CREATE TABLE IF NOT EXISTS cards (
    guild_id   INTEGER NOT NULL,
    user_id    INTEGER NOT NULL,
    name       TEXT NOT NULL,
    norm_name  TEXT NOT NULL,
    norm_front TEXT NOT NULL,
    qty        INTEGER NOT NULL,
    PRIMARY KEY (guild_id, user_id, norm_name)
);
CREATE INDEX IF NOT EXISTS cards_lookup ON cards (guild_id, norm_name);
CREATE INDEX IF NOT EXISTS cards_front  ON cards (guild_id, norm_front);
"""


class Store:
    def __init__(self, path: str):
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)

    # ---- collections -------------------------------------------------
    def replace_collection(self, guild_id: int, user_id: int, source: str,
                           url: str | None, cards: dict[str, int]) -> int:
        """Replace a member's whole collection. Returns distinct card count."""
        merged: dict[str, tuple[str, int]] = {}
        for name, qty in cards.items():
            key = normalize(name)
            if not key or qty <= 0:
                continue
            prev = merged.get(key)
            merged[key] = (name, qty + (prev[1] if prev else 0))
        with self.conn:
            self.conn.execute("DELETE FROM cards WHERE guild_id=? AND user_id=?",
                              (guild_id, user_id))
            self.conn.executemany(
                "INSERT INTO cards VALUES (?,?,?,?,?,?)",
                [(guild_id, user_id, name, key, normalize(front_face(name)), qty)
                 for key, (name, qty) in merged.items()])
            self.conn.execute(
                "INSERT INTO links VALUES (?,?,?,?,?,NULL) "
                "ON CONFLICT(guild_id,user_id) DO UPDATE SET source=excluded.source,"
                " url=excluded.url, last_synced=excluded.last_synced, last_error=NULL",
                (guild_id, user_id, source, url, time.time()))
        return len(merged)

    def record_error(self, guild_id: int, user_id: int, error: str) -> None:
        with self.conn:
            self.conn.execute("UPDATE links SET last_error=? WHERE guild_id=? AND user_id=?",
                              (error[:500], guild_id, user_id))

    def clear(self, guild_id: int, user_id: int) -> None:
        with self.conn:
            self.conn.execute("DELETE FROM cards WHERE guild_id=? AND user_id=?", (guild_id, user_id))
            self.conn.execute("DELETE FROM links WHERE guild_id=? AND user_id=?", (guild_id, user_id))

    def link(self, guild_id: int, user_id: int):
        return self.conn.execute("SELECT * FROM links WHERE guild_id=? AND user_id=?",
                                 (guild_id, user_id)).fetchone()

    def stats(self, guild_id: int, user_id: int) -> tuple[int, int]:
        row = self.conn.execute(
            "SELECT COUNT(*), COALESCE(SUM(qty),0) FROM cards WHERE guild_id=? AND user_id=?",
            (guild_id, user_id)).fetchone()
        return row[0], row[1]

    def links_due(self, older_than: float) -> Iterable[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM links WHERE source != 'csv' AND (last_synced IS NULL OR last_synced < ?)",
            (older_than,)).fetchall()

    # ---- lookup ------------------------------------------------------
    def who_has(self, guild_id: int, card_name: str) -> list[sqlite3.Row]:
        """Members owning a card. Matches full name or the front face of a
        double-faced card, so 'Delver of Secrets' finds 'Delver ... // ...'."""
        key = normalize(card_name)
        front = normalize(front_face(card_name))
        return self.conn.execute(
            "SELECT user_id, SUM(qty) AS qty, MIN(name) AS name FROM cards "
            "WHERE guild_id=? AND (norm_name=? OR norm_front=? OR norm_name=?) "
            "GROUP BY user_id ORDER BY qty DESC",
            (guild_id, key, front, front)).fetchall()

    def suggest(self, guild_id: int, prefix: str, limit: int = 25) -> list[str]:
        """Card names in this server's collections, for autocomplete."""
        key = normalize(prefix)
        rows = self.conn.execute(
            "SELECT name FROM cards WHERE guild_id=? AND norm_name LIKE ? "
            "GROUP BY norm_name ORDER BY name LIMIT ?",
            (guild_id, f"%{key}%", limit)).fetchall()
        return [r[0] for r in rows]

    def all_names(self, guild_id: int) -> list[str]:
        return [r[0] for r in self.conn.execute(
            "SELECT MIN(name) FROM cards WHERE guild_id=? GROUP BY norm_name", (guild_id,))]
