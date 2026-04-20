from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Generator, Iterable, List

from models import Company, NewsItem


DB_PATH = Path(__file__).with_name("news.db")


@contextmanager
def get_connection() -> Generator[sqlite3.Connection, None, None]:
    conn = sqlite3.connect(DB_PATH)
    try:
        yield conn
    finally:
        conn.close()


def init_db() -> None:
    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS news (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                url TEXT NOT NULL UNIQUE,
                source TEXT NOT NULL,
                published_at TEXT,
                summary TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS companies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                source TEXT NOT NULL,
                rank INTEGER,
                year INTEGER,
                url TEXT,
                UNIQUE(name, source, year)
            )
            """
        )
        conn.commit()


def _serialize_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def save_news(items: Iterable[NewsItem]) -> int:
    """Сохранить список новостей, игнорируя дубликаты по URL. Возвращает число реально вставленных записей."""
    inserted = 0
    with get_connection() as conn:
        for item in items:
            try:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO news (title, url, source, published_at, summary)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        item.title,
                        item.url,
                        item.source,
                        _serialize_datetime(item.published_at),
                        item.summary,
                    ),
                )
                if conn.total_changes > inserted:
                    inserted = conn.total_changes
            except sqlite3.Error:
                continue
        conn.commit()
    return inserted


def get_latest(limit: int = 50) -> List[NewsItem]:
    with get_connection() as conn:
        cursor = conn.execute(
            """
            SELECT title, url, source, published_at, summary
            FROM news
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        )
        rows = cursor.fetchall()

    items: List[NewsItem] = []
    for title, url, source, published_at_str, summary in rows:
        published_at = (
            datetime.fromisoformat(published_at_str)
            if published_at_str
            else None
        )
        items.append(
            NewsItem(
                title=title,
                url=url,
                source=source,
                published_at=published_at,
                summary=summary,
            )
        )
    return items


def save_companies(items: Iterable[Company]) -> int:
    inserted = 0
    with get_connection() as conn:
        for item in items:
            try:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO companies (name, source, rank, year, url)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        item.name,
                        item.source,
                        item.rank,
                        item.year,
                        item.url,
                    ),
                )
                if conn.total_changes > inserted:
                    inserted = conn.total_changes
            except sqlite3.Error:
                continue
        conn.commit()
    return inserted

