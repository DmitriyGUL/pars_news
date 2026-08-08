"""
Источники rb.ru (Rusbase).

Два парсера на одну площадку:

* RbHrParser — раздел /tag/hr/ с профильными кадровыми материалами. Ходит
  вглубь по ?page=N: кнопка «Читать ещё» на сайте рисуется скриптом, но
  страницы сервер отдаёт обычными GET-запросами (у раздела их около 480).
* RbFeedParser — общая лента rb.ru, чтобы не пропустить кадровые новости,
  не попавшие в тег.
"""

from __future__ import annotations

import re
from typing import List

from models import NewsItem
from .base_parser import BaseParser
from .rss_parser import RssParser


# Материалы лежат в нескольких разделах, но у всех общий вид пути:
# /news/<slug>, /interview/<slug>, /reviews/<slug>, /stories/<slug>...
ARTICLE_URL = re.compile(r"/(news|interview|reviews|stories|columns|opinion|lists)/[^/]{8,}")


class RbHrParser(BaseParser):
    """Парсер раздела rb.ru/tag/hr — кадровые материалы Rusbase."""

    BASE_URL = "https://rb.ru"
    NEWS_URL = "https://rb.ru/tag/hr/"
    SOURCE_NAME = "rb_hr"

    LINK_SELECTORS = (
        ".news-item__title",
        "a[href^='/news/']",
        "a[href^='/interview/']",
        "a[href^='/reviews/']",
        "a[href^='/stories/']",
    )

    ARTICLE_URL_PATTERN = ARTICLE_URL

    # Пагинация нарисована скриптом («Читать ещё» + data-num-pages="480"),
    # ссылок «далее» в разметке нет, но ?page=N сервер отдаёт нормально.
    PAGE_PARAM = "page"
    SECOND_PAGE_NUMBER = 2


class RbFeedParser(RssParser):
    """Общая лента rb.ru."""

    SOURCE_NAME = "rb_feed"
    FEED_URLS = ("https://rb.ru/feeds/all/",)
    ARTICLE_URL_PATTERN = ARTICLE_URL


def fetch(limit: int = 200, days: int = 7, with_summaries: bool = True,
          max_pages: int | None = None) -> List[NewsItem]:
    """Раздел HR — основной источник rb.ru для проекта."""
    return RbHrParser().fetch(
        limit, days, with_summaries=with_summaries, max_pages=max_pages
    )


def fetch_feed(limit: int = 200, days: int = 7, with_summaries: bool = True,
               max_pages: int | None = None) -> List[NewsItem]:
    """Общая лента rb.ru."""
    return RbFeedParser().fetch(
        limit, days, with_summaries=with_summaries, max_pages=max_pages
    )
