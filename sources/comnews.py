from __future__ import annotations

import re
from typing import List

from models import NewsItem
from .base_parser import BaseParser


class ComnewsParser(BaseParser):
    """Парсер новостей с сайта comnews.ru."""

    BASE_URL = "https://www.comnews.ru"
    NEWS_URL = "https://www.comnews.ru/manpower"
    SOURCE_NAME = "comnews"

    LINK_SELECTORS = ("a[href^='/']",)

    # Статьи comnews всегда лежат по пути /content/<id>/... (в том числе внутри
    # разделов, например /digital-economy/content/245934/...). Без этой проверки
    # селектор a[href^='/'] складывал в БД разделы сайта («Связь и ТВ»,
    # «Электроника», «Технологии») как новости.
    ARTICLE_URL_PATTERN = re.compile(r"/content/\d+/")


def fetch(limit: int = 200, days: int = 7, with_summaries: bool = True,
          max_pages: int | None = None) -> List[NewsItem]:
    """Функция для обратной совместимости."""
    parser = ComnewsParser()
    return parser.fetch(limit, days, with_summaries=with_summaries, max_pages=max_pages)
