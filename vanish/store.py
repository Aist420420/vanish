"""SQLite-хранилище: результаты разбора почты, решения и игровой прогресс."""

from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);

-- Одна строка на письмо (kind=0 — входящее от сервиса, kind=1 — моё письмо на домен,
-- kind=2 — письмо с домена сервиса, попавшее в «Спам»: признак спамера, не сервис).
-- Хранится только хеш идентификатора, домен, дата и признаки — не текст письма.
CREATE TABLE IF NOT EXISTS messages (
    hash    TEXT PRIMARY KEY,
    domain  TEXT NOT NULL,
    kind    INTEGER NOT NULL DEFAULT 0,
    ts      INTEGER,
    unsub   INTEGER NOT NULL DEFAULT 0,
    signal  INTEGER NOT NULL DEFAULT 0,
    sender  TEXT NOT NULL DEFAULT '',
    topic   TEXT NOT NULL DEFAULT '',
    purchase INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS messages_domain ON messages(domain, kind);
CREATE INDEX IF NOT EXISTS messages_sender ON messages(sender);

CREATE TABLE IF NOT EXISTS my_addresses (
    address TEXT PRIMARY KEY
);

-- Сводка по домену, пересчитывается после каждого импорта.
CREATE TABLE IF NOT EXISTS domain_stats (
    domain     TEXT PRIMARY KEY,
    count      INTEGER NOT NULL,
    first_ts   INTEGER,
    last_ts    INTEGER,
    unsub      INTEGER NOT NULL,
    strong     INTEGER NOT NULL,
    weak       INTEGER NOT NULL,
    sent_to    INTEGER NOT NULL,
    confidence TEXT NOT NULL,
    purchases  INTEGER NOT NULL DEFAULT 0,
    topic      TEXT NOT NULL DEFAULT '',
    spam       INTEGER NOT NULL DEFAULT 0
);

-- Данные для отображения: примеры тем и имя отправителя.
CREATE TABLE IF NOT EXISTS domain_info (
    domain        TEXT PRIMARY KEY,
    samples       TEXT NOT NULL DEFAULT '[]',
    display_name  TEXT NOT NULL DEFAULT '',
    google_linked INTEGER NOT NULL DEFAULT 0,
    -- https-ссылка отписки из самого свежего письма с List-Unsubscribe и дата этого письма.
    unsub_url     TEXT NOT NULL DEFAULT '',
    unsub_ts      INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS google_access (
    subject TEXT PRIMARY KEY
);

-- Мои решения. Никогда не перезаписываются импортом почты.
CREATE TABLE IF NOT EXISTS services (
    domain      TEXT PRIMARY KEY,
    name        TEXT NOT NULL DEFAULT '',
    site        TEXT NOT NULL DEFAULT '',
    manual      INTEGER NOT NULL DEFAULT 0,
    decision    TEXT,
    status      TEXT,
    unsub_done  INTEGER NOT NULL DEFAULT 0,
    note        TEXT NOT NULL DEFAULT '',
    decided_at  TEXT,
    finished_at TEXT,
    xp_decision INTEGER NOT NULL DEFAULT 0,
    xp_finish   INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT
);

CREATE TABLE IF NOT EXISTS actions (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    ts      TEXT NOT NULL,
    day     TEXT NOT NULL,
    kind    TEXT NOT NULL,
    domain  TEXT NOT NULL,
    before  TEXT NOT NULL,
    undone  INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS activity (
    day   TEXT PRIMARY KEY,
    count INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS achievements (
    id          TEXT PRIMARY KEY,
    unlocked_at TEXT NOT NULL
);
"""


def connect(path: Path) -> sqlite3.Connection:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(SCHEMA)
    _migrate(conn)
    return conn


# Колонки, добавленные после первой версии: (таблица, колонка, определение).
MIGRATIONS = [
    ("messages", "topic", "TEXT NOT NULL DEFAULT ''"),
    ("messages", "purchase", "INTEGER NOT NULL DEFAULT 0"),
    ("domain_stats", "purchases", "INTEGER NOT NULL DEFAULT 0"),
    ("domain_stats", "topic", "TEXT NOT NULL DEFAULT ''"),
    ("domain_stats", "spam", "INTEGER NOT NULL DEFAULT 0"),
    ("domain_info", "unsub_url", "TEXT NOT NULL DEFAULT ''"),
    ("domain_info", "unsub_ts", "INTEGER NOT NULL DEFAULT 0"),
]


def _migrate(conn: sqlite3.Connection) -> None:
    for table, column, ddl in MIGRATIONS:
        columns = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
        if column not in columns:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")
    conn.commit()


def get_meta(conn: sqlite3.Connection, key: str, default: str | None = None) -> str | None:
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


def set_meta(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO meta(key, value) VALUES(?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )
