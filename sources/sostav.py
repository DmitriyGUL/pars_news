"""
Sostav.ru — реклама, маркетинг, бренды (sostav.ru).

Та же ниша, что уже закрывает AdIndex, но другая редакция и другой охват
брендов — материалы почти не пересекаются по URL, поэтому дублей не даёт.

Пагинация — числовой параметр `?page=N` (проверено: страница 2 отдаёт новый
набор материалов, не повтор первой). Даты на странице статьи не лежат ни в
`<time>`, ни в `meta[property=article:published_time]` — только в ld+json
(`datePublished`), который `date_utils.parse_date_from_html` уже разбирает
без доработок.
"""

from __future__ import annotations

import re
from typing import List

from models import NewsItem
from .base_parser import BaseParser


class SostavParser(BaseParser):
    """Парсер раздела sostav.ru/news."""

    BASE_URL = "https://www.sostav.ru"
    NEWS_URL = "https://www.sostav.ru/news"
    SOURCE_NAME = "sostav"

    LINK_SELECTORS = ("a[href*='/publication/']",)

    # /publication/<slug>-<числовой-id>.html — материал; без числового ID
    # в конце это разделы и статичные страницы («Гайдлайны», «Контакты»).
    ARTICLE_URL_PATTERN = re.compile(r"/publication/[^/]+-\d+\.html$")

    PAGE_PARAM = "page"
    SECOND_PAGE_NUMBER = 2


def fetch(limit: int = 200, days: int = 7, with_summaries: bool = True,
          max_pages: int | None = None) -> List[NewsItem]:
    """Функция для обратной совместимости."""
    parser = SostavParser()
    return parser.fetch(limit, days, with_summaries=with_summaries, max_pages=max_pages)
