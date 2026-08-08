from __future__ import annotations

import csv
import logging
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Dict, Generator, Iterable, List

from models import Company, NewsItem


logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).with_name("news.db")

# Каталог для выгрузок (Excel/CSV), чтобы не засорять корень проекта.
EXPORTS_DIR = Path(__file__).with_name("exports")


def ensure_exports_dir() -> Path:
    """Создаёт каталог для выгрузок и возвращает путь к нему."""
    EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
    return EXPORTS_DIR


def build_export_path(extension: str, moment: datetime | None = None) -> Path:
    """
    Путь к новой выгрузке: «Сбор новостей 07.08.2026, 20-09.xlsx».

    Время пишется через дефис, потому что двоеточие в именах файлов Windows
    запрещено. Метка времени в имени не даёт перезаписать прошлые отчёты.
    """
    moment = moment or datetime.now()
    name = f"Сбор новостей {moment:%d.%m.%Y, %H-%M}.{extension.lstrip('.')}"
    return ensure_exports_dir() / name


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
        for item in items:
            try:
                cursor = conn.execute(
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
                inserted += cursor.rowcount
            except sqlite3.Error as exc:
                logger.warning("Не удалось сохранить новость %s: %s", item.url, exc)
                continue
        conn.commit()
    return inserted


def _rows_to_news_items(rows: Iterable[tuple]) -> List[NewsItem]:
    """Преобразует строки выборки (title, url, source, published_at, summary) в NewsItem."""
    items: List[NewsItem] = []
    for title, url, source, published_at_str, summary in rows:
        published_at = None
        if published_at_str:
            try:
                published_at = datetime.fromisoformat(published_at_str)
            except ValueError:
                logger.warning("Некорректная дата в БД для %s: %r", url, published_at_str)

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

    return _rows_to_news_items(rows)


def get_news_rows_for_date_refresh(only_suspicious: bool = True, limit: int = 100000) -> List[tuple]:
    """
    Записи, которым нужно пересчитать дату публикации: (url, published_at).

    По умолчанию берутся только подозрительные — те, где дата публикации
    совпадает с датой сбора либо отсутствует. Именно такие строки оставила
    прежняя логика, подставлявшая дату из шапки сайта.
    """
    condition = ""
    params: List = []
    if only_suspicious:
        # Дата совпадает с датой сбора, отсутствует или лежит в будущем —
        # все три случая давала прежняя логика разбора даты.
        condition = (
            "WHERE published_at IS NULL "
            "   OR substr(published_at, 1, 10) = substr(created_at, 1, 10) "
            "   OR published_at > ?"
        )
        params.append(datetime.now().isoformat())

    params.append(limit)
    with get_connection() as conn:
        cursor = conn.execute(
            f"SELECT url, published_at FROM news {condition} ORDER BY id DESC LIMIT ?",
            params,
        )
        return cursor.fetchall()


def update_published_at(url: str, published_at: datetime | None) -> None:
    """Обновляет дату публикации одной новости."""
    with get_connection() as conn:
        conn.execute(
            "UPDATE news SET published_at = ? WHERE url = ?",
            (_serialize_datetime(published_at), url),
        )
        conn.commit()


def get_news_urls_for_summary(
    limit: int = 100000,
    only_missing: bool = True,
    since: str | datetime | None = None,
) -> List[str]:
    """
    URL новостей для команды backfill-summaries.

    По умолчанию берутся только записи без лида. `only_missing=False` возвращает
    все — это нужно, когда изменились правила извлечения лида и уже сохранённые
    описания надо перечитать. `since` ограничивает выборку датой публикации:
    еженедельному отчёту не нужно дозаполнять весь архив.
    """
    conditions = []
    params: List = []

    if only_missing:
        conditions.append("(summary IS NULL OR trim(summary) = '')")
    if since:
        # Записи без даты тоже берём: лид поможет её потом определить.
        conditions.append("(published_at IS NULL OR substr(published_at, 1, 10) >= ?)")
        params.append(_as_date_string(since))

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    params.append(limit)

    with get_connection() as conn:
        cursor = conn.execute(
            f"SELECT url FROM news {where} ORDER BY id DESC LIMIT ?",
            params,
        )
        return [row[0] for row in cursor.fetchall()]


def update_summary(url: str, summary: str | None) -> None:
    """Обновляет лид одной новости."""
    with get_connection() as conn:
        conn.execute("UPDATE news SET summary = ? WHERE url = ?", (summary, url))
        conn.commit()


def get_all_news_urls() -> List[tuple]:
    """Все сохранённые новости в виде (url, source, title) — для проверок целостности."""
    with get_connection() as conn:
        cursor = conn.execute("SELECT url, source, title FROM news")
        return cursor.fetchall()


def delete_news_by_urls(urls: Iterable[str]) -> int:
    """Удаляет новости по списку URL. Возвращает число удалённых записей."""
    urls = list(urls)
    if not urls:
        return 0

    with get_connection() as conn:
        cursor = conn.executemany("DELETE FROM news WHERE url = ?", ((u,) for u in urls))
        deleted = cursor.rowcount
        conn.commit()
    return deleted


def save_companies(items: Iterable[Company]) -> int:
    """Сохранить список компаний, игнорируя дубликаты. Возвращает число вставленных записей."""
    inserted = 0
    with get_connection() as conn:
        for item in items:
            try:
                cursor = conn.execute(
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
                inserted += cursor.rowcount
            except sqlite3.Error as exc:
                logger.warning("Не удалось сохранить компанию %s: %s", item.name, exc)
                continue
        conn.commit()
    return inserted


def _as_date_string(value: str | datetime) -> str:
    """Приводит дату к виду YYYY-MM-DD для сравнения с колонкой published_at."""
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d")
    return str(value)[:10]


def get_news_by_date_range(start_date: str | datetime, end_date: str | datetime) -> List[NewsItem]:
    """
    Получает новости за указанный период (границы включительно).

    Сравнение идёт по первым 10 символам published_at (YYYY-MM-DD): в БД
    попадают как наивные даты, так и даты со смещением ("...+03:00"), и
    прямое строковое сравнение полных значений давало неверные границы.
    """
    with get_connection() as conn:
        cursor = conn.execute(
            """
            SELECT title, url, source, published_at, summary
            FROM news
            WHERE published_at IS NOT NULL
              AND substr(published_at, 1, 10) BETWEEN ? AND ?
            ORDER BY published_at DESC
            """,
            (_as_date_string(start_date), _as_date_string(end_date)),
        )
        rows = cursor.fetchall()

    return _rows_to_news_items(rows)


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


def export_to_csv(
    output_path: str | Path | None = None,
    limit: int = 10000,
    start_date: str | datetime | None = None,
    end_date: str | datetime | None = None,
) -> str:
    """
    Экспортирует новости в CSV файл.

    По умолчанию файл создаётся в каталоге exports/ с меткой времени в имени,
    чтобы предыдущие выгрузки не перезаписывались. Если заданы обе границы
    периода, выгружаются новости за него, иначе — последние `limit` записей.
    """
    if output_path is None:
        output_path = build_export_path("csv")

    if start_date and end_date:
        news_items = get_news_by_date_range(start_date, end_date)[:limit]
    else:
        news_items = get_latest(limit=limit)

    # utf-8-sig — чтобы Excel корректно открывал кириллицу
    with open(output_path, 'w', newline='', encoding='utf-8-sig') as csvfile:
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

    return str(output_path)