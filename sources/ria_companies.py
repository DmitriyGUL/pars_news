from __future__ import annotations

import re
from typing import List, Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from models import NewsItem
from .base_parser import BaseParser



class RiaCompaniesParser(BaseParser):
    """Парсер новостей с сайта ria.ru/company."""

    BASE_URL = "https://ria.ru"
    NEWS_URL = "https://ria.ru/company/"
    SOURCE_NAME = "ria_companies"

    LINK_SELECTORS = ("a[href*='/20']",)

    # У РИА материалы лежат по пути /YYYYMMDD/<slug>.html
    ARTICLE_URL_PATTERN = re.compile(r"/\d{8}/")

    def _find_next_page(self, soup: BeautifulSoup, current_url: str) -> Optional[str]:
        """
        Следующая порция новостей.

        У РИА нет обычной пагинации: лента догружается запросом
        /services/company/more.html?id=<id>&date=<метка>. На первой странице
        адрес лежит в data-url блока «Еще», а в самих порциях — в data-next-url
        обёртки. Без этого парсер ограничивался единственной страницей.
        """
        for selector, attr in (
            (".list-more[data-url]", "data-url"),
            ("[data-next-url]", "data-next-url"),
        ):
            node = soup.select_one(selector)
            if node and str(node.get(attr, "")).strip():
                return urljoin(self.BASE_URL, str(node[attr]).strip())

        return None


def fetch(limit: int = 200, days: int = 7, with_summaries: bool = True,
          max_pages: int | None = None) -> List[NewsItem]:
    """Функция для обратной совместимости."""
    parser = RiaCompaniesParser()
    return parser.fetch(limit, days, with_summaries=with_summaries, max_pages=max_pages)
