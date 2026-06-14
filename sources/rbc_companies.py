from __future__ import annotations

from typing import List
from bs4 import BeautifulSoup

from models import NewsItem
from .base_parser import BaseParser
from .date_utils import parse_date_from_tag, parse_date_from_url


class RbcCompaniesParser(BaseParser):
    """Парсер новостей с сайта companies.rbc.ru."""
    
    BASE_URL = "https://companies.rbc.ru"
    NEWS_URL = "https://companies.rbc.ru/"
    SOURCE_NAME = "rbc_companies"
    
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                     "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    }
    
    def _parse_page(self, soup: BeautifulSoup, cutoff, seen_urls) -> List[NewsItem]:
        """Парсит новости с одной страницы companies.rbc.ru."""
        items: List[NewsItem] = []
        
        for link in soup.select("a[href*='/news/'], a[href*='/intervyu/']"):
            href = link.get("href")
            if not href:
                continue

            title = link.get_text(strip=True)
            if not title or len(title) < 10:
                continue

            url = self._make_absolute_url(href)
            if not url:
                continue

            if url in seen_urls:
                continue
            seen_urls.add(url)

            block = link.find_parent("article") or link.find_parent("div") or link
            published_at = parse_date_from_tag(block) or parse_date_from_url(url)
            if published_at and published_at < cutoff:
                continue

            items.append(
                NewsItem(
                    title=title,
                    url=url,
                    source=self.SOURCE_NAME,
                    published_at=published_at,
                )
            )

        return items


def fetch(limit: int = 200, days: int = 7) -> List[NewsItem]:
    """Функция для обратной совместимости."""
    parser = RbcCompaniesParser()
    return parser.fetch(limit, days)