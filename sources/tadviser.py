"""
TAdviser — ИТ-рынок, компании, продукты и персоналии (tadviser.ru).

Площадка — MediaWiki: материалы лежат в пространствах имён «Статья:»,
«Персона:» и «Компания:». Раздел «Персона:» особенно ценен для кадровой
аналитики — там прямо фиксируются назначения («Персона:Панёв Александр»).

Пагинация на странице «Новости» рисуется JS-кнопкой «Ещё »: её href ведёт в
никуда (#), рабочего числового параметра у неё нет. Поэтому берём одну
страницу листинга — как Forbes, накопление идёт за счёт регулярных прогонов.
"""

from __future__ import annotations

import re
from typing import List

from models import NewsItem
from .base_parser import BaseParser


class TadviserParser(BaseParser):
    """Парсер новостного раздела tadviser.ru."""

    BASE_URL = "https://www.tadviser.ru"
    NEWS_URL = "https://www.tadviser.ru/index.php/Новости"
    SOURCE_NAME = "tadviser"

    LINK_SELECTORS = ("a[href*='/index.php/']",)

    # Три пространства имён с реальными материалами; остальные (Служебная:,
    # Видео:, Продукт:) — не новости в нашем смысле.
    ARTICLE_URL_PATTERN = re.compile(r"/index\.php/(Статья|Персона|Компания):")

    # На MediaWiki короткие ссылки-якоря попадаются чаще, чем на обычных
    # сайтах: порог выше общего.
    MIN_TITLE_LENGTH = 12


def fetch(limit: int = 200, days: int = 7, with_summaries: bool = True,
          max_pages: int | None = None) -> List[NewsItem]:
    """Функция для обратной совместимости."""
    parser = TadviserParser()
    return parser.fetch(limit, days, with_summaries=with_summaries, max_pages=max_pages)
