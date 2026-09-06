"""
hh.ru — раздел «Статьи»: рынок труда, найм, зарплаты (hh.ru/articles).

Раздел смешивает два вида материалов: аналитику рынка труда (/article/NNNN)
и брендированные интервью с работодателями (/interview/NNNN) — по сути,
рекламные материалы о компании как работодателе. Оба берём: интервью не
получают тега «Реклама» автоматически (MATERIAL_MARKERS их не ловит), но
дают полезный контекст о найме конкретных компаний.

Пагинация на листинге — «Показать ещё» без числового параметра в URL,
поэтому, как и у TAdviser, берётся одна страница; накопление — за счёт
регулярных прогонов.
"""

from __future__ import annotations

import re
from typing import List

from models import NewsItem
from .base_parser import BaseParser


class HhArticlesParser(BaseParser):
    """Парсер раздела hh.ru/articles."""

    BASE_URL = "https://hh.ru"
    NEWS_URL = "https://hh.ru/articles"
    SOURCE_NAME = "hh_articles"

    LINK_SELECTORS = (
        "a[href*='/article/']",
        "a[href*='/interview/']",
    )

    # Числовой ID материала — отсекает /article/cookie_policy и прочие
    # служебные страницы, которые иначе попадали бы в БД как новости.
    ARTICLE_URL_PATTERN = re.compile(r"/(article|interview)/\d+")

    # На листинге у карточки интервью встречается два <a> на одну статью:
    # обёртка вокруг картинки (пустой текст) и заголовок. Наш общий разбор
    # ссылки в таком случае ищет текст в других местах и иногда попадает на
    # короткий подзаголовок секции интервью («Требования к ПО», «О компании»)
    # вместо заголовка материала. Порог выше общего отсекает такие обрывки.
    MIN_TITLE_LENGTH = 25


def fetch(limit: int = 200, days: int = 7, with_summaries: bool = True,
          max_pages: int | None = None) -> List[NewsItem]:
    """Функция для обратной совместимости."""
    parser = HhArticlesParser()
    return parser.fetch(limit, days, with_summaries=with_summaries, max_pages=max_pages)
