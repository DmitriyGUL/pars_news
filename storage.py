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
        # Таблица новостей
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS news (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                url TEXT NOT NULL UNIQUE,
                source TEXT NOT NULL,
                published_at TEXT,
                summary TEXT,
                created_at TEXT
            )
            """
        )
        
        # Проверяем наличие колонки created_at в таблице news
        cursor = conn.execute("PRAGMA table_info(news)")
        columns = [column[1] for column in cursor.fetchall()]
        
        if 'created_at' not in columns:
            # Добавляем колонку created_at для существующих таблиц
            conn.execute("ALTER TABLE news ADD COLUMN created_at TEXT")
            # Обновляем существующие записи с текущей датой
            conn.execute("UPDATE news SET created_at = datetime('now') WHERE created_at IS NULL")
        
        # Таблица компаний
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS companies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                source TEXT NOT NULL,
                rank INTEGER,
                year INTEGER,
                url TEXT,
                created_at TEXT,
                UNIQUE(name, source, year)
            )
            """
        )
        
        # Проверяем наличие колонки created_at в таблице companies
        cursor = conn.execute("PRAGMA table_info(companies)")
        columns = [column[1] for column in cursor.fetchall()]
        
        if 'created_at' not in columns:
            # Добавляем колонку created_at для существующих таблиц
            conn.execute("ALTER TABLE companies ADD COLUMN created_at TEXT")
            # Обновляем существующие записи с текущей датой
            conn.execute("UPDATE companies SET created_at = datetime('now') WHERE created_at IS NULL")
        
        # Создаем индексы для ускорения запросов
        conn.execute("CREATE INDEX IF NOT EXISTS idx_news_source ON news(source)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_news_published_at ON news(published_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_news_created_at ON news(created_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_companies_source ON companies(source)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_companies_year ON companies(year)")
        
        conn.commit()


def _serialize_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def save_news(items: Iterable[NewsItem]) -> int:
    """Сохранить список новостей, игнорируя дубликаты по URL. Возвращает число реально вставленных записей."""
    inserted = 0
    with get_connection() as conn:
        # Проверяем наличие колонки created_at
        cursor = conn.execute("PRAGMA table_info(news)")
        columns = [column[1] for column in cursor.fetchall()]
        has_created_at = 'created_at' in columns
        
        for item in items:
            try:
                if has_created_at:
                    conn.execute(
                        """
                        INSERT OR IGNORE INTO news (title, url, source, published_at, summary, created_at)
                        VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                        """,
                        (
                            item.title,
                            item.url,
                            item.source,
                            _serialize_datetime(item.published_at),
                            item.summary,
                        ),
                    )
                else:
                    # Старая версия без created_at
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
        # Проверяем наличие колонки created_at
        cursor = conn.execute("PRAGMA table_info(companies)")
        columns = [column[1] for column in cursor.fetchall()]
        has_created_at = 'created_at' in columns
        
        for item in items:
            try:
                if has_created_at:
                    conn.execute(
                        """
                        INSERT OR IGNORE INTO companies (name, source, rank, year, url, created_at)
                        VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                        """,
                        (
                            item.name,
                            item.source,
                            item.rank,
                            item.year,
                            item.url,
                        ),
                    )
                else:
                    # Старая версия без created_at
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



def get_companies(limit: int = 1000) -> List[Dict]:
    """
    Получает список компаний из базы данных.
    """
    with get_connection() as conn:
        cursor = conn.execute(
            """
            SELECT name, source, rank, year, url, created_at
            FROM companies
            ORDER BY name
            LIMIT ?
            """,
            (limit,),
        )
        rows = cursor.fetchall()
    
    companies = []
    for name, source, rank, year, url, created_at in rows:
        companies.append({
            'name': name,
            'source': source,
            'rank': rank,
            'year': year,
            'url': url,
            'created_at': created_at
        })
    
    return companies


def get_news_by_date_range(start_date: str, end_date: str) -> List[NewsItem]:
    """
    Получает новости за указанный период.
    """
    with get_connection() as conn:
        cursor = conn.execute(
            """
            SELECT title, url, source, published_at, summary
            FROM news
            WHERE published_at BETWEEN ? AND ?
            ORDER BY published_at DESC
            """,
            (start_date, end_date),
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


def get_statistics() -> Dict:
    """
    Возвращает статистику по базе данных.
    """
    with get_connection() as conn:
        # Статистика новостей
        cursor = conn.execute("SELECT COUNT(*) FROM news")
        total_news = cursor.fetchone()[0]
        
        cursor = conn.execute("SELECT COUNT(DISTINCT source) FROM news")
        news_sources = cursor.fetchone()[0]
        
        cursor = conn.execute("SELECT MIN(published_at), MAX(published_at) FROM news WHERE published_at IS NOT NULL")
        date_range = cursor.fetchone()
        min_date, max_date = date_range if date_range else (None, None)
        
        # Статистика компаний
        cursor = conn.execute("SELECT COUNT(*) FROM companies")
        total_companies = cursor.fetchone()[0]
        
        cursor = conn.execute("SELECT COUNT(DISTINCT source) FROM companies")
        company_sources = cursor.fetchone()[0]
        
        cursor = conn.execute("SELECT COUNT(*) FROM companies WHERE rank IS NOT NULL")
        companies_with_rank = cursor.fetchone()[0]
    
    return {
        'news': {
            'total': total_news,
            'sources': news_sources,
            'date_range': {
                'min': min_date,
                'max': max_date
            }
        },
        'companies': {
            'total': total_companies,
            'sources': company_sources,
            'with_rank': companies_with_rank
        }
    }


def export_to_csv(output_path: str = "export.csv") -> str:
    """
    Экспортирует новости в CSV файл.
    """
    import csv
    
    news_items = get_latest(limit=10000)
    
    with open(output_path, 'w', newline='', encoding='utf-8') as csvfile:
        fieldnames = ['title', 'url', 'source', 'published_at', 'summary']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        
        writer.writeheader()
        for item in news_items:
            writer.writerow({
                'title': item.title,
                'url': item.url,
                'source': item.source,
                'published_at': item.published_at.isoformat() if item.published_at else '',
                'summary': item.summary or ''
            })
    
    return output_path