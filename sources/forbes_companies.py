from __future__ import annotations

import re
from typing import List

from models import NewsItem
from .base_parser import BaseParser


class ForbesCompaniesParser(BaseParser):
    """Парсер новостей с сайта forbes.ru/novosti-kompaniy."""

    BASE_URL = "https://www.forbes.ru"
    NEWS_URL = "https://www.forbes.ru/novosti-kompaniy/"
    SOURCE_NAME = "forbes_companies"

    LINK_SELECTORS = ("a[href^='/novosti-kompaniy/']",)

    # Материал раздела, а не сама страница раздела
    ARTICLE_URL_PATTERN = re.compile(r"/novosti-kompaniy/.+")

    # У Forbes встречаются длинные служебные подписи, поэтому порог выше общего
    MIN_TITLE_LENGTH = 15


def fetch(limit: int = 200, days: int = 7, with_summaries: bool = True,
          max_pages: int | None = None) -> List[NewsItem]:
    """Функция для обратной совместимости."""
    parser = ForbesCompaniesParser()
    return parser.fetch(limit, days, with_summaries=with_summaries, max_pages=max_pages)
