from __future__ import annotations

from typing import List, Optional

from datetime import datetime, timedelta
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup, Tag

from models import NewsItem


BASE_URL = "https://www.forbes.ru"
NEWS_URL = "https://www.forbes.ru/novosti-kompaniy/"

HEADERS = {
    "User-Agent": "pars_news/0.1 (+https://www.forbes.ru/)",
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
        # Возможны форматы "18 hours ago", "2 days ago" и т.п.
        parts = text.lower().split()
        if len(parts) >= 2 and parts[1].startswith("hour"):
            try:
                hours = int(parts[0])
                return datetime.utcnow() - timedelta(hours=hours)
            except ValueError:
                pass
        if len(parts) >= 2 and parts[1].startswith("day"):
            try:
                days = int(parts[0])
                return datetime.utcnow() - timedelta(days=days)
            except ValueError:
                pass
    return None


def _find_next_page(soup: BeautifulSoup) -> Optional[str]:
    link = soup.find("a", rel="next")
    if not link:
        for a in soup.find_all("a"):
            text = a.get_text(strip=True).lower()
            if "далее" in text or "next" in text:
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

        # Берем ссылки именно на материалы рубрики "Новости компаний".
        for link in soup.select("a[href^='/novosti-kompaniy/']"):
            href = link.get("href")
            if not href:
                continue

            title = link.get_text(strip=True)
            if not title:
                continue

            # Отбрасываем служебные ссылки типа "Читать"
            if title.lower() in {"читать"} or len(title) < 15:
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
                    source="forbes_companies",
                    published_at=published_at,
                )
            )

            if len(items) >= limit:
                break

        if len(items) >= limit:
            break

        page_url = _find_next_page(soup)

    return items

