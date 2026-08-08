from __future__ import annotations

import html as html_lib
import json
import logging
import re
from datetime import datetime
from typing import List, Optional

import requests
from bs4 import BeautifulSoup

from models import NewsItem
from .base_parser import BaseParser


logger = logging.getLogger(__name__)

# Формат даты в ответе догрузки: "2026.07.15 19:00:43"
JSON_DATE_FORMAT = "%Y.%m.%d %H:%M:%S"


class AdindexParser(BaseParser):
    """Парсер новостей с сайта adindex.ru."""

    BASE_URL = "https://adindex.ru"
    NEWS_URL = "https://adindex.ru/news/hr/"
    SOURCE_NAME = "adindex"

    LINK_SELECTORS = (
        "article a[href]",   # Новости в статьях
        ".news-item a[href]",
        ".item a[href]",
        "h2 a[href]",        # Заголовки с ссылками
        "h3 a[href]",
    )

    # Только материалы раздела новостей. Раньше в БД попадали страницы
    # /ratings/... («Рейтинг операторов Indoor-инвентаря»), которые новостями
    # не являются.
    ARTICLE_URL_PATTERN = re.compile(r"/news/")

    def _decode(self, resp: requests.Response) -> str:
        """
        Текст ответа, приведённый к HTML.

        На листинге кнопка «Показать ещё» тянет продолжение ленты с
        /system/includes/blocks/news/load_more.phtml и получает JSON, а не
        HTML. Разворачиваем его в разметку, чтобы дальше работал общий разбор
        листинга. Бонусом дата берётся прямо из ответа — без похода в статью.
        """
        if "application/json" not in resp.headers.get("content-type", ""):
            return super()._decode(resp)

        try:
            payload = json.loads(resp.text)
        except json.JSONDecodeError as exc:
            logger.warning("%s: не удалось разобрать ответ догрузки: %s", self.SOURCE_NAME, exc)
            return ""

        if not isinstance(payload, list):
            return ""

        return self._render_items(payload)

    def _render_items(self, payload: List[dict]) -> str:
        """Собирает HTML-фрагмент из JSON-ответа догрузки."""
        blocks = []
        last_at = ""

        for entry in payload:
            if not isinstance(entry, dict):
                continue
            url = entry.get("url")
            title = entry.get("title")
            if not url or not title:
                continue

            last_at = str(entry.get("last_at") or last_at)
            blocks.append(
                '<div class="news-item">'
                f'{self._render_time(entry.get("date"))}'
                f'<a href="{html_lib.escape(str(url), quote=True)}">'
                f'{html_lib.escape(str(title))}</a>'
                "</div>"
            )

        if not blocks:
            return ""

        # Маркер следующей порции в том же виде, что и кнопка на самом сайте,
        # чтобы _find_next_page не различал страницу и фрагмент.
        blocks.append(
            '<button class="js-load-news" '
            'data-load-url="/system/includes/blocks/news/load_more.phtml?path=124276&amp;last_at=" '
            f'data-last="{html_lib.escape(last_at, quote=True)}"></button>'
        )
        return "<html><body>" + "".join(blocks) + "</body></html>"

    @staticmethod
    def _render_time(raw_date) -> str:
        """Тег <time> с ISO-датой публикации, если она пришла в ответе."""
        if not raw_date:
            return ""
        try:
            parsed = datetime.strptime(str(raw_date), JSON_DATE_FORMAT)
        except ValueError:
            return ""
        return f'<time datetime="{parsed.isoformat()}"></time>'

    def _find_next_page(self, soup: BeautifulSoup, current_url: str) -> Optional[str]:
        """Адрес следующей порции ленты из кнопки «Показать ещё»."""
        button = soup.select_one(".js-load-news[data-load-url][data-last]")
        if not button:
            return super()._find_next_page(soup, current_url)

        last = str(button["data-last"]).strip()
        if not last:
            return None

        return self.BASE_URL + str(button["data-load-url"]) + last


def fetch(limit: int = 200, days: int = 7, with_summaries: bool = True,
          max_pages: int | None = None) -> List[NewsItem]:
    """Функция для обратной совместимости."""
    parser = AdindexParser()
    return parser.fetch(limit, days, with_summaries=with_summaries, max_pages=max_pages)
