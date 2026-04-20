from __future__ import annotations

from typing import List

from models import NewsItem
from storage import get_latest, init_db, save_news
from sources import adindex, comnews, forbes_companies, rbc_companies, ria_companies


PARSERS = [
    ("adindex", adindex.fetch),
    ("comnews", comnews.fetch),
    ("rbc_companies", rbc_companies.fetch),
    ("ria_companies", ria_companies.fetch),
    ("forbes_companies", forbes_companies.fetch),
]


def run_all_parsers(days: int = 7, limit_per_source: int = 200) -> List[NewsItem]:
    collected: List[NewsItem] = []

    for source_name, fetch_func in PARSERS:
        try:
            items = fetch_func(limit=limit_per_source, days=days)
        except Exception as exc:  # noqa: BLE001
            print(f"[ERROR] {source_name}: {exc}")
            continue

        print(f"[INFO] {source_name}: получено {len(items)} записей")
        collected.extend(items)

    return collected


def main() -> None:
    init_db()
    # По умолчанию собираем публикации примерно за последнюю неделю
    items = run_all_parsers(days=7, limit_per_source=200)

    inserted = save_news(items)
    print(f"[INFO] В БД добавлено {inserted} новых записей")

    latest = get_latest(limit=10)
    print("\nПоследние новости:")
    for item in latest:
        date_str = item.published_at.isoformat() if item.published_at else "без даты"
        print(f"- [{item.source}] {date_str} — {item.title} — {item.url}")


if __name__ == "__main__":
    main()

