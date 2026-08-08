"""
Базовый парсер RSS/Atom-лент.

Лента выгодна тем, что отдаёт заголовок, ссылку, дату публикации и лид одним
запросом: не нужно ни обходить страницы листинга, ни заходить в каждую статью
ради даты. Поэтому источник на RSS добавляется одним классом с парой полей.

Разбор идёт стандартным xml.etree: подключать lxml ради этого не нужно.
"""

from __future__ import annotations

import html as html_lib
import logging
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
from typing import Callable, List, Optional, Pattern, Sequence

import requests

from models import NewsItem
from .base_parser import DEFAULT_USER_AGENT
from .date_utils import (
    SUMMARY_MAX_LENGTH,
    SUMMARY_MIN_LENGTH,
    enrich_news_items,
    strip_author_prefix,
    to_naive_local,
)


logger = logging.getLogger(__name__)

# Теги внутри <item>/<entry> разложены по разным пространствам имён, поэтому
# сравниваем только локальную часть имени.
TITLE_TAGS = ("title",)
LINK_TAGS = ("link", "guid")
DATE_TAGS = ("pubDate", "published", "updated", "date")
SUMMARY_TAGS = ("description", "summary", "encoded", "content")

TAG_RE = re.compile(r"<[^>]+>")


def _local_name(tag: str) -> str:
    """Имя тега без пространства имён: '{...}pubDate' -> 'pubDate'."""
    return tag.rsplit("}", 1)[-1]


def _strip_html(value: str) -> str:
    """Текст без разметки: лид в RSS часто приходит куском HTML."""
    return " ".join(html_lib.unescape(TAG_RE.sub(" ", value)).split())


def parse_feed_date(value: str) -> Optional[datetime]:
    """
    Дата записи ленты.

    RSS предписывает формат RFC 822 («Fri, 08 Aug 2026 11:20:00 +0300»), Atom —
    ISO 8601. Встречаются оба, поэтому пробуем по очереди.
    """
    value = value.strip()
    if not value:
        return None

    try:
        return to_naive_local(parsedate_to_datetime(value))
    except (TypeError, ValueError):
        pass

    try:
        return to_naive_local(datetime.fromisoformat(value.replace("Z", "+00:00")))
    except ValueError:
        return None


class RssParser:
    """
    Базовый класс источника, читающего RSS/Atom.

    Подклассу достаточно объявить FEED_URLS и SOURCE_NAME. Интерфейс совпадает
    с BaseParser (fetch/is_article_url), поэтому оба вида источников
    взаимозаменяемы для main.py и команды cleanup.
    """

    SOURCE_NAME: str = ""
    FEED_URLS: Sequence[str] = ()
    REQUEST_TIMEOUT = 20

    # Ссылка считается новостью, только если совпадает с шаблоном. Нужно лентам,
    # которые подмешивают спецпроекты и страницы разделов.
    ARTICLE_URL_PATTERN: Optional[Pattern[str]] = None

    # Отбор по теме: если задан, в выгрузку попадают только записи, для которых
    # функция вернула True (проверяется заголовок вместе с лидом). Так широкая
    # федеральная лента даёт профильные новости, а не сводки с полей.
    # Присваивать нужно через staticmethod, иначе Python сделает из функции
    # метод и передаст ей self.
    TOPIC_FILTER: Optional[Callable[[str], bool]] = None

    MIN_TITLE_LENGTH = 10

    def __init__(self):
        self._session = requests.Session()
        self._session.headers.update({"User-Agent": DEFAULT_USER_AGENT})

    @classmethod
    def is_article_url(cls, url: str) -> bool:
        """Проверяет, что URL похож на страницу новости, а не на раздел сайта."""
        if cls.ARTICLE_URL_PATTERN is None:
            return True
        return bool(cls.ARTICLE_URL_PATTERN.search(url))

    def fetch(
        self,
        limit: int = 200,
        days: int = 7,
        with_summaries: bool = True,
        max_pages: Optional[int] = None,
    ) -> List[NewsItem]:
        """
        Новости из лент источника.

        `max_pages` принимается ради единой сигнатуры с BaseParser и не
        используется: лента отдаётся одним документом, листать нечего.
        """
        cutoff = datetime.now() - timedelta(days=days)
        items: List[NewsItem] = []
        seen_urls = set()

        for feed_url in self.FEED_URLS:
            if len(items) >= limit:
                break

            for item in self._fetch_feed(feed_url):
                if len(items) >= limit:
                    break
                if item.url in seen_urls:
                    continue
                if item.published_at and item.published_at < cutoff:
                    continue

                seen_urls.add(item.url)
                items.append(item)

        # Дата и лид почти всегда приходят из ленты, но часть источников их не
        # отдаёт — для таких записей отработает обычное обогащение.
        return enrich_news_items(
            items, dict(self._session.headers), fetch_summaries=with_summaries
        )

    def _fetch_feed(self, feed_url: str) -> List[NewsItem]:
        try:
            resp = self._session.get(feed_url, timeout=self.REQUEST_TIMEOUT)
            resp.raise_for_status()
        except requests.RequestException as exc:
            logger.error("%s: ошибка при запросе %s: %s", self.SOURCE_NAME, feed_url, exc)
            return []

        try:
            # Разбираем байты, а не resp.text: кодировка объявлена в самом XML.
            root = ET.fromstring(resp.content)
        except ET.ParseError as exc:
            logger.error("%s: лента %s не разобралась: %s", self.SOURCE_NAME, feed_url, exc)
            return []

        items = []
        for entry in root.iter():
            if _local_name(entry.tag) not in ("item", "entry"):
                continue
            item = self._entry_to_news_item(entry)
            if item is not None:
                items.append(item)

        return items

    def _entry_to_news_item(self, entry: ET.Element) -> Optional[NewsItem]:
        """Превращает запись ленты в NewsItem либо отбраковывает её."""
        fields = {}
        for child in entry:
            name = _local_name(child.tag)
            if name in fields:
                continue
            # У Atom ссылка лежит в атрибуте href, а не в тексте элемента.
            fields[name] = (child.text or child.get("href") or "").strip()

        title = _strip_html(self._first(fields, TITLE_TAGS))
        url = self._first(fields, LINK_TAGS)
        if not title or not url.startswith("http"):
            return None
        if len(title) < self.MIN_TITLE_LENGTH or not self.is_article_url(url):
            return None

        summary = _strip_html(self._first(fields, SUMMARY_TAGS))
        summary = strip_author_prefix(summary)
        if len(summary) < SUMMARY_MIN_LENGTH:
            summary = ""

        if not self._matches_topic(title, summary):
            return None

        return NewsItem(
            title=title,
            url=url.split("?")[0],
            source=self.SOURCE_NAME,
            published_at=parse_feed_date(self._first(fields, DATE_TAGS)),
            summary=summary[:SUMMARY_MAX_LENGTH] or None,
        )

    def _matches_topic(self, title: str, summary: str) -> bool:
        if self.TOPIC_FILTER is None:
            return True
        return bool(self.TOPIC_FILTER(f"{title} {summary}"))

    @staticmethod
    def _first(fields: dict, names: Sequence[str]) -> str:
        for name in names:
            value = fields.get(name)
            if value:
                return value
        return ""
