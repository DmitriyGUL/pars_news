from __future__ import annotations

import re
from typing import List

from models import NewsItem
from .base_parser import BaseParser


class RbcCompaniesParser(BaseParser):
    """Парсер новостей с сайта companies.rbc.ru."""

    BASE_URL = "https://companies.rbc.ru"
    # Лента раздела, а не главная: на главной висят 134 материала одним куском,
    # но перелистывать её нельзя — ?page= там игнорируется. Лента отдаёт по 21
    # материалу на страницу и листается сколь угодно глубоко.
    NEWS_URL = "https://companies.rbc.ru/news/"
    SOURCE_NAME = "rbc_companies"

    LINK_SELECTORS = ("a[href*='/news/'], a[href*='/intervyu/']",)

    # Ссылок «далее» в разметке нет (пагинация рисуется скриптом), но
    # ?page=N сервер обрабатывает.
    PAGE_PARAM = "page"

    # Материал имеет вид /news/<id>/<slug>. Страницы фильтров
    # (/news/?category_filter=it-tehnologii) под шаблон не подходят.
    ARTICLE_URL_PATTERN = re.compile(r"/(news|intervyu)/[^/?#]+/[^/?#]+")


def fetch(limit: int = 200, days: int = 7, with_summaries: bool = True,
          max_pages: int | None = None) -> List[NewsItem]:
    """Функция для обратной совместимости."""
    parser = RbcCompaniesParser()
    return parser.fetch(limit, days, with_summaries=with_summaries, max_pages=max_pages)
