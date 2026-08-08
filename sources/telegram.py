"""
Публичные Telegram-каналы.

Читаются через веб-превью t.me/s/<канал> — это обычный HTML, который отдаётся
без бота, токена и авторизации. Ограничение: так доступны только публичные
каналы, у которых в настройках включён предпросмотр. Если канал закрыт или
имени не существует, страница приходит пустой (постов ноль) — парсер сообщает
об этом в лог и идёт дальше.

Пост — не статья: у него нет заголовка. За заголовок берётся первая фраза, а
полный текст кладётся в summary, по которому и считаются теги.

Проверить канал, ничего не сохраняя:

    py -c "from sources.telegram import probe_channel; probe_channel('banksta')"
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta
from typing import List, Optional, Sequence
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup, Tag

from models import NewsItem
from .base_parser import DEFAULT_USER_AGENT
from .date_utils import SUMMARY_MAX_LENGTH, to_naive_local


logger = logging.getLogger(__name__)

TELEGRAM_BASE = "https://t.me"

# Ссылка на пост: https://t.me/<канал>/<номер>
POST_URL_PATTERN = re.compile(r"t\.me/[\w\d_]+/\d+")

# Заголовок поста — первая фраза. Режем по концу предложения или переводу
# строки, иначе в заголовок попадает весь пост целиком.
SENTENCE_END = re.compile(r"(?<=[.!?…])\s+|\n")

TITLE_MAX_LENGTH = 200

# Хвосты, которыми каналы подписывают посты, — в заголовке они мешают.
SIGNATURE = re.compile(r"\s*@[\w\d_]+\s*$")


def _post_title(text: str) -> str:
    """Первая фраза поста — она играет роль заголовка новости."""
    first = SENTENCE_END.split(text.strip(), maxsplit=1)[0].strip()
    first = SIGNATURE.sub("", first)

    if len(first) > TITLE_MAX_LENGTH:
        # Длинную фразу режем по границе слова, чтобы не рвать посередине.
        cut = first[:TITLE_MAX_LENGTH].rsplit(" ", 1)[0]
        return cut + "…"
    return first


class TelegramParser:
    """
    Базовый класс источника «публичные Telegram-каналы».

    Подклассу достаточно объявить CHANNELS и SOURCE_NAME. Интерфейс совпадает
    с BaseParser и RssParser, поэтому источник подключается так же.
    """

    SOURCE_NAME: str = ""
    CHANNELS: Sequence[str] = ()

    REQUEST_TIMEOUT = 20
    # Пауза между запросами страниц канала — как у листингов сайтов.
    REQUEST_DELAY = 0.5
    # Сколько «экранов» листаем назад по одному каналу за прогон.
    MAX_PAGES = 20

    ARTICLE_URL_PATTERN = POST_URL_PATTERN

    # Отбор по теме, как у RSS: нужен широким каналам, где кадровых постов мало.
    # Присваивать через staticmethod, иначе функция станет методом.
    TOPIC_FILTER = None

    # Слишком короткие посты («➖», «Реклама») новостями не считаем.
    MIN_TEXT_LENGTH = 60

    def __init__(self):
        self._session = requests.Session()
        self._session.headers.update({"User-Agent": DEFAULT_USER_AGENT})

    @classmethod
    def is_article_url(cls, url: str) -> bool:
        return bool(cls.ARTICLE_URL_PATTERN.search(url))

    def fetch(
        self,
        limit: int = 200,
        days: int = 7,
        with_summaries: bool = True,
        max_pages: Optional[int] = None,
    ) -> List[NewsItem]:
        """
        Посты каналов за последние `days` дней.

        Дата и текст берутся прямо из разметки превью, поэтому заходить
        куда-либо ещё не нужно: `with_summaries` здесь ни на что не влияет.
        """
        cutoff = datetime.now() - timedelta(days=days)
        max_pages = max_pages if max_pages is not None else self.MAX_PAGES

        items: List[NewsItem] = []
        for channel in self.CHANNELS:
            if len(items) >= limit:
                break
            items.extend(
                self._fetch_channel(channel, cutoff, limit - len(items), max_pages)
            )

        return items

    def _fetch_channel(
        self, channel: str, cutoff: datetime, limit: int, max_pages: int
    ) -> List[NewsItem]:
        """Листает канал назад, пока посты не станут старше cutoff."""
        import time

        items: List[NewsItem] = []
        page_url = f"{TELEGRAM_BASE}/s/{channel}"
        seen_urls = set()

        for page_no in range(max_pages):
            if page_no:
                time.sleep(self.REQUEST_DELAY)

            soup = self._load_page(channel, page_url)
            if soup is None:
                break

            posts = soup.select(".tgme_widget_message_wrap")
            if not posts:
                # Канал закрыт, не существует или у него выключен предпросмотр.
                logger.warning(
                    "%s: канал %s не отдаёт посты (закрыт, без предпросмотра или имени нет)",
                    self.SOURCE_NAME, channel,
                )
                break

            reached_cutoff = False
            for post in posts:
                item = self._post_to_news_item(post, channel)
                if item is None or item.url in seen_urls:
                    continue
                if item.published_at and item.published_at < cutoff:
                    # Превью отдаёт посты по возрастанию даты, поэтому первый
                    # пост старше cutoff означает: дальше вглубь только старее.
                    reached_cutoff = True
                    continue

                seen_urls.add(item.url)
                items.append(item)
                if len(items) >= limit:
                    return items

            if reached_cutoff:
                break

            next_url = self._next_page_url(soup, page_url)
            if not next_url or next_url == page_url:
                break
            page_url = next_url

        logger.debug("%s: канал %s дал %d постов", self.SOURCE_NAME, channel, len(items))
        return items

    def _load_page(self, channel: str, url: str) -> Optional[BeautifulSoup]:
        try:
            resp = self._session.get(url, timeout=self.REQUEST_TIMEOUT)
            resp.raise_for_status()
        except requests.RequestException as exc:
            logger.error("%s: ошибка при запросе %s: %s", self.SOURCE_NAME, url, exc)
            return None
        return BeautifulSoup(resp.text, "html.parser")

    def _next_page_url(self, soup: BeautifulSoup, current_url: str) -> Optional[str]:
        """
        Адрес следующего «экрана» канала.

        В превью это ссылка вида /s/<канал>?before=<номер поста>: она листает
        ленту назад, к более старым постам.
        """
        more = soup.select_one("a.tme_messages_more[href]")
        if more is None:
            return None
        return urljoin(current_url, more["href"])

    def _post_to_news_item(self, post: Tag, channel: str) -> Optional[NewsItem]:
        text_tag = post.select_one(".tgme_widget_message_text")
        if text_tag is None:
            # Пост без текста — картинка, опрос или пересланное видео.
            return None

        text = " ".join(text_tag.get_text(" ", strip=True).split())
        if len(text) < self.MIN_TEXT_LENGTH:
            return None

        bubble = post.select_one(".tgme_widget_message[data-post]")
        data_post = bubble.get("data-post") if bubble else None
        if not data_post:
            return None

        title = _post_title(text)
        if not title:
            return None

        if self.TOPIC_FILTER is not None and not self.TOPIC_FILTER(text):
            return None

        time_tag = post.select_one("time[datetime]")
        published_at = None
        if time_tag and time_tag.get("datetime"):
            try:
                published_at = to_naive_local(
                    datetime.fromisoformat(time_tag["datetime"].replace("Z", "+00:00"))
                )
            except ValueError:
                logger.debug("%s: не разобрал дату %r", self.SOURCE_NAME, time_tag["datetime"])

        return NewsItem(
            title=title,
            url=f"{TELEGRAM_BASE}/{data_post}",
            source=self.SOURCE_NAME,
            published_at=published_at,
            summary=text[:SUMMARY_MAX_LENGTH],
        )


def probe_channel(channel: str, days: int = 7) -> None:
    """Печатает, что отдаёт канал. Нужна при подборе каналов в конфигурацию."""

    class _Probe(TelegramParser):
        SOURCE_NAME = "probe"
        CHANNELS = (channel,)

    items = _Probe().fetch(limit=10, days=days)
    print(f"{channel}: постов за {days} дн. — {len(items)}")
    for item in items[:5]:
        print(f"  {item.published_at} | {item.title[:90]}")
