from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import List, Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from models import NewsItem
from .date_utils import enrich_news_items


class BaseParser(ABC):
    """Базовый класс для всех парсеров новостей."""
    
    BASE_URL: str = ""
    NEWS_URL: str = ""
    SOURCE_NAME: str = ""
    HEADERS: dict[str, str] = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                     "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    def __init__(self):
        self._session = requests.Session()
        self._session.headers.update(self.HEADERS)
        
    def fetch(self, limit: int = 200, days: int = 7) -> List[NewsItem]:
        """Основной метод получения новостей."""
        cutoff = datetime.now() - timedelta(days=days)
        items: List[NewsItem] = []
        seen_urls: set[str] = set()
        
        page_url: Optional[str] = self.NEWS_URL
        pages_parsed = 0
        max_pages = 10
        
        while page_url and pages_parsed < max_pages and len(items) < limit:
            try:
                resp = self._session.get(page_url, timeout=15)
                resp.raise_for_status()
            except requests.RequestException as e:
                print(f"[ERROR] {self.SOURCE_NAME}: ошибка при запросе {page_url}: {e}")
                break
                
            soup = BeautifulSoup(resp.text, "html.parser")
            pages_parsed += 1
            
            # Парсим новости с текущей страницы
            page_items = self._parse_page(soup, cutoff, seen_urls)
            for item in page_items:
                if len(items) >= limit:
                    break
                items.append(item)
            
            if len(items) >= limit:
                break
            
            # Ищем следующую страницу
            page_url = self._find_next_page(soup)
            
        # Обогащаем новости датами публикации
        return enrich_news_items(items, self._session.headers)
    
    @abstractmethod
    def _parse_page(self, soup: BeautifulSoup, cutoff: datetime, seen_urls: set[str]) -> List[NewsItem]:
        """Парсит новости с одной страницы. Должен быть реализован в дочерних классах."""
        pass
    
    def _find_next_page(self, soup: BeautifulSoup) -> Optional[str]:
        """Ищет ссылку на следующую страницу."""
        # Пробуем найти стандартную ссылку rel="next"
        link = soup.find("a", rel="next")
        if link and link.get("href"):
            return urljoin(self.NEWS_URL, link["href"])
        
        # Ищем по тексту ссылки
        next_texts = ["следующая", "далее", "еще", "next", "дальше"]
        for a in soup.find_all("a"):
            text = a.get_text(strip=True).lower()
            if any(next_text in text for next_text in next_texts):
                href = a.get("href")
                if href:
                    return urljoin(self.NEWS_URL, href)
        
        return None
    
    def _make_absolute_url(self, href: str) -> str:
        """Преобразует относительную ссылку в абсолютную."""
        if href.startswith("/"):
            return urljoin(self.BASE_URL, href)
        elif href.startswith("http"):
            return href
        else:
            return urljoin(self.NEWS_URL, href)