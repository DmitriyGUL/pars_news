from __future__ import annotations

from typing import List, Optional

from datetime import datetime, timedelta
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup, Tag

from models import NewsItem


BASE_URL = "https://www.comnews.ru"
NEWS_URL = "https://www.comnews.ru/manpower"

HEADERS = {
    "User-Agent": "pars_news/0.1 (+https://www.comnews.ru/)",
}


def _parse_date_from_block(block: Tag) -> Optional[datetime]:
    time_tag = block.find("time")
    if time_tag:
        dt_attr = time_tag.get("datetime")
        if dt_attr:
            try:
                return datetime.fromisoformat(dt_attr.split("+")[0])
            except ValueError:
                pass
        text = time_tag.get_text(strip=True)
        for fmt in ("%d.%m.%y", "%d.%m.%Y"):
            try:
                return datetime.strptime(text.split()[0], fmt)
            except ValueError:
                continue
    return None


def _find_next_page(soup: BeautifulSoup) -> Optional[str]:
    # Конкретно на ComNews есть подпись "Следующая страница ››"
    link = None
    for a in soup.find_all("a"):
        text = a.get_text(strip=True).lower()
        if "следующая страница" in text or text == "следующая":
            link = a
            break
    if not link:
        return None

    href = link.get("href")
    if not href:
        return None

    return urljoin(NEWS_URL, href)


def fetch(limit: int = 200, days: int = 7) -> List[NewsItem]:
    cutoff = datetime.utcnow() - timedelta(days=days)
    items: List[NewsItem] = []
    seen_urls: set[str] = set()

    page_url: Optional[str] = NEWS_URL
    pages_parsed = 0
    max_pages = 10

    while page_url and pages_parsed < max_pages and len(items) < limit:
        resp = requests.get(page_url, headers=HEADERS, timeout=15)
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")
        pages_parsed += 1

        # На странице рубрики ссылки на материалы обычно ведут на внутренние URL
        # с цифрами (ID или датой). Используем это как простой фильтр.
        for link in soup.select("a[href^='/']"):
            href = link.get("href")
            if not href or href == "/":
                continue

            # Пропускаем служебные ссылки рубрики
            if "manpower" in href:
                continue

            # Берем только ссылки, где есть цифры (как правило, это материалы)
            if not any(ch.isdigit() for ch in href):
                continue

            title = link.get_text(strip=True)
            if not title:
                continue

            url = urljoin(BASE_URL, href)
            if url in seen_urls:
                continue
            seen_urls.add(url)

            block = link.find_parent("article") or link
            published_at = _parse_date_from_block(block)
            if published_at and published_at < cutoff:
                continue

            items.append(
                NewsItem(
                    title=title,
                    url=url,
                    source="comnews",
                    published_at=published_at,
                )
            )

            if len(items) >= limit:
                break

        if len(items) >= limit:
            break

        page_url = _find_next_page(soup)

    return items

