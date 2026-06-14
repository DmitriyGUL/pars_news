from __future__ import annotations

from typing import List
from bs4 import BeautifulSoup

from models import NewsItem
from .base_parser import BaseParser
from .date_utils import parse_date_from_tag, parse_date_from_url


class AdindexParser(BaseParser):
    """Парсер новостей с сайта adindex.ru."""
    
    BASE_URL = "https://adindex.ru"
    NEWS_URL = "https://adindex.ru/news/hr/"
    SOURCE_NAME = "adindex"
    
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                     "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    }
    
    def _parse_page(self, soup: BeautifulSoup, cutoff, seen_urls) -> List[NewsItem]:
        """Парсит новости с одной страницы adindex.ru."""
        items: List[NewsItem] = []
        
        # Более специфичные селекторы для adindex
        selectors = [
            "article a[href]",  # Новости в статьях
            ".news-item a[href]",  # Новости с классом news-item
            ".item a[href]",  # Новости с классом item
            "h2 a[href]",  # Заголовки с ссылками
            "h3 a[href]",  # Подзаголовки с ссылками
        ]
        
        for selector in selectors:
            for link in soup.select(selector):
                href = link.get("href")
                if not href:
                    continue
                
                title = link.get_text(strip=True)
                if not title or len(title) < 10:
                    continue
                
                # Пропускаем ссылки на главную, контакты, политику конфиденциальности и т.д.
                skip_keywords = ["/privacy-policy", "/contacts", "/about", "/help", "главная", "назад"]
                if any(keyword in href.lower() or keyword in title.lower() for keyword in skip_keywords):
                    continue
                
                url = self._make_absolute_url(href)
                if not url:
                    continue

                if url in seen_urls:
                    continue
                seen_urls.add(url)

                # Ищем дату в родительском элементе
                parent = link.find_parent(["article", "div", "section"])
                published_at = parse_date_from_tag(parent) if parent else None
                if not published_at:
                    published_at = parse_date_from_url(url)
                
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
    parser = AdindexParser()
    return parser.fetch(limit, days)