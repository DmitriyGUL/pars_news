from __future__ import annotations

import logging
import re
import time
from abc import ABC
from datetime import datetime, timedelta
from types import MappingProxyType
from typing import List, Mapping, Optional, Pattern, Sequence
from urllib.parse import parse_qs, urlencode, urljoin, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup

from models import NewsItem
from .date_utils import (
    decode_response,
    enrich_news_items,
    parse_date_from_tag,
    parse_date_from_url,
    to_naive_local,
)


logger = logging.getLogger(__name__)

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


class BaseParser(ABC):
    """Базовый класс для всех парсеров новостей."""

    BASE_URL: str = ""
    NEWS_URL: str = ""
    SOURCE_NAME: str = ""
    # MappingProxyType: общий для всех подклассов словарь не должен мутировать
    HEADERS: Mapping[str, str] = MappingProxyType({"User-Agent": DEFAULT_USER_AGENT})

    # Максимальное число страниц листинга за один прогон
    MAX_PAGES = 20
    REQUEST_TIMEOUT = 15

    # Пауза между запросами страниц листинга. Прогон обходит пять источников по
    # двадцать страниц и вдобавок догружает статьи в несколько потоков — без
    # паузы это уже похоже на нагрузочное тестирование чужого сайта.
    REQUEST_DELAY = 0.5

    # Имя query-параметра постраничной навигации ("page" -> ?page=2, ?page=3...).
    # Нужно сайтам, которые пагинацию рисуют скриптом: ссылки "далее" в разметке
    # нет, но URL с параметром страницы сервер отдаёт нормально.
    PAGE_PARAM: Optional[str] = None
    # Номер, с которого начинается вторая страница (у части сайтов это 1, а не 2)
    SECOND_PAGE_NUMBER = 2

    # --- Настройки разбора страницы листинга (переопределяются в подклассах) ---

    # CSS-селекторы ссылок на новости
    LINK_SELECTORS: Sequence[str] = ()

    # Ссылка считается новостью, только если её URL совпадает с этим шаблоном.
    # Отсекает разделы сайта и страницы фильтров, которые иначе попадают в БД
    # как новости с заголовками вида «Связь и ТВ» или «Малый бизнес».
    ARTICLE_URL_PATTERN: Optional[Pattern[str]] = None

    # Минимальная длина заголовка — короткие подписи это навигация, а не новость
    MIN_TITLE_LENGTH = 10

    # Заголовки-кнопки, которые нужно игнорировать целиком
    SKIP_TITLES: frozenset = frozenset({"читать", "подробнее", "читать далее", "все новости"})

    # Точные подписи ссылок на следующую страницу
    NEXT_PAGE_TEXTS = frozenset({
        "следующая", "следующая страница", "далее", "дальше", "вперёд", "вперед",
        "next", "next page", "›", "»", "→",
    })

    # Где имеет смысл искать пагинацию
    PAGINATION_SELECTORS = (
        ".pagination a[href]",
        ".pager a[href]",
        "[class*='pagination'] a[href]",
        "[class*='pager'] a[href]",
        "nav[aria-label*='aginat'] a[href]",
    )

    def __init__(self):
        self._session = requests.Session()
        self._session.headers.update(dict(self.HEADERS))

    def fetch(
        self,
        limit: int = 200,
        days: int = 7,
        with_summaries: bool = True,
        max_pages: Optional[int] = None,
    ) -> List[NewsItem]:
        """
        Основной метод получения новостей.

        `max_pages` ограничивает глубину обхода листинга. У разделов бывает по
        несколько сотен страниц (у rb.ru/tag/hr — около 480), поэтому предел
        нужен: без него один прогон уходил бы в многочасовой обход архива.
        Обход и так прекращается раньше — по достижении limit.
        """
        cutoff = datetime.now() - timedelta(days=days)
        max_pages = max_pages if max_pages is not None else self.MAX_PAGES
        items: List[NewsItem] = []
        seen_urls: set[str] = set()
        visited_pages: set[str] = set()

        page_url: Optional[str] = self.NEWS_URL
        pages_parsed = 0

        while page_url and pages_parsed < max_pages and len(items) < limit:
            if page_url in visited_pages:
                # Пагинация зациклилась — иначе крутились бы вхолостую до MAX_PAGES
                break
            visited_pages.add(page_url)

            if pages_parsed and self.REQUEST_DELAY:
                time.sleep(self.REQUEST_DELAY)

            try:
                resp = self._session.get(page_url, timeout=self.REQUEST_TIMEOUT)
                resp.raise_for_status()
            except requests.RequestException as e:
                if pages_parsed and self._is_end_of_listing(e):
                    # 404 после уже разобранных страниц — это конец раздела, а
                    # не сбой: сайт просто не отдаёт страницу за последней.
                    # Логировать это ошибкой значит пугать без причины.
                    logger.info(
                        "%s: лента закончилась на странице %d (%s)",
                        self.SOURCE_NAME, pages_parsed + 1, page_url,
                    )
                else:
                    logger.error("%s: ошибка при запросе %s: %s", self.SOURCE_NAME, page_url, e)
                break

            soup = BeautifulSoup(self._decode(resp), "html.parser")
            pages_parsed += 1

            # Парсим новости с текущей страницы
            for item in self._parse_page(soup, cutoff, seen_urls):
                if len(items) >= limit:
                    break
                items.append(item)

            if len(items) >= limit:
                break

            # Ищем следующую страницу
            page_url = self._find_next_page(soup, page_url)

        if page_url and pages_parsed >= max_pages:
            # Лента не кончилась — просто упёрлись в предел глубины. Видно в
            # логе, чтобы не гадать, почему новостей меньше ожидаемого.
            logger.info(
                "%s: остановка на пределе в %d страниц, лента продолжается",
                self.SOURCE_NAME, max_pages,
            )

        logger.debug(
            "%s: обойдено страниц %d, собрано ссылок %d",
            self.SOURCE_NAME, pages_parsed, len(items),
        )

        # Обогащаем новости датами публикации и лидом статьи
        enriched = enrich_news_items(
            items, dict(self._session.headers), fetch_summaries=with_summaries
        )

        # Повторная фильтрация: до обогащения дата у части новостей была
        # неизвестна, поэтому отсечь их по cutoff в _parse_page было нельзя.
        # Новости, у которых дату определить так и не удалось, сохраняем.
        result = [
            item for item in enriched
            if item.published_at is None or to_naive_local(item.published_at) >= cutoff
        ]

        dropped = len(enriched) - len(result)
        if dropped:
            logger.info(
                "%s: отброшено %d новостей старше %s",
                self.SOURCE_NAME, dropped, cutoff.strftime("%Y-%m-%d"),
            )

        return result

    # Коды, которыми сайт отвечает на страницу за последней существующей.
    END_OF_LISTING_CODES = frozenset({404, 410})

    @classmethod
    def _is_end_of_listing(cls, error: requests.RequestException) -> bool:
        """Означает ли ошибка запроса, что страницы кончились."""
        response = getattr(error, "response", None)
        return response is not None and response.status_code in cls.END_OF_LISTING_CODES

    def _decode(self, resp: requests.Response) -> str:
        """Текст ответа с кодировкой, определённой по содержимому при необходимости."""
        return decode_response(resp)

    def _parse_page(self, soup: BeautifulSoup, cutoff: datetime, seen_urls: set[str]) -> List[NewsItem]:
        """
        Парсит новости с одной страницы листинга.

        Реализация общая для всех источников: подклассам достаточно объявить
        LINK_SELECTORS и ARTICLE_URL_PATTERN. Переопределяйте метод только если
        у сайта принципиально другая структура.
        """
        items: List[NewsItem] = []

        for selector in self.LINK_SELECTORS:
            for link in soup.select(selector):
                item = self._link_to_news_item(link, cutoff, seen_urls)
                if item is not None:
                    items.append(item)

        return items

    def _link_to_news_item(self, link, cutoff: datetime, seen_urls: set[str]) -> Optional[NewsItem]:
        """Превращает ссылку в NewsItem либо возвращает None, если это не новость."""
        href = link.get("href")
        if not href:
            return None

        title = self._extract_title(link)
        if not title or len(title) < self.MIN_TITLE_LENGTH:
            return None
        if title.lower() in self.SKIP_TITLES:
            return None

        url = self._normalize_url(self._make_absolute_url(href))
        if not url or not self._is_article_url(url):
            return None

        if url in seen_urls:
            return None
        seen_urls.add(url)

        block = link.find_parent("article") or link.find_parent("div") or link
        published_at = to_naive_local(parse_date_from_tag(block) or parse_date_from_url(url))

        # Новости без даты не отбрасываем: дату определит enrich_news_items,
        # а окончательная фильтрация по cutoff произойдёт в fetch().
        if published_at and published_at < cutoff:
            return None

        return NewsItem(
            title=title,
            url=url,
            source=self.SOURCE_NAME,
            published_at=published_at,
        )

    def _extract_title(self, link) -> str:
        """
        Заголовок новости для ссылки.

        В листингах на одну новость приходится несколько ссылок: обёртка вокруг
        картинки (без текста) и собственно заголовок. Пустую обёртку нельзя
        просто отбрасывать — на РИА и РБК часть новостей представлена только
        такой ссылкой, и они терялись целиком. Поэтому текст ищется также в
        атрибутах ссылки, в alt картинки и в заголовке родительского блока.
        """
        title = link.get_text(strip=True)
        if title:
            return title

        for attr in ("title", "aria-label"):
            value = link.get(attr)
            if isinstance(value, str) and value.strip():
                return value.strip()

        img = link.find("img")
        if img:
            for attr in ("alt", "title"):
                value = img.get(attr)
                if isinstance(value, str) and value.strip():
                    return value.strip()

        block = link.find_parent("article") or link.find_parent("div")
        if block is not None:
            heading = block.find(["h1", "h2", "h3", "h4"])
            if heading:
                text = heading.get_text(strip=True)
                if text:
                    return text

        return ""

    @classmethod
    def is_article_url(cls, url: str) -> bool:
        """
        Проверяет, что URL похож на страницу новости, а не на раздел сайта.

        Метод классовый: проверка нужна и вне парсинга (команда cleanup чистит
        БД от ранее сохранённых разделов), а создавать ради неё экземпляр с
        HTTP-сессией незачем.
        """
        if cls.ARTICLE_URL_PATTERN is None:
            return True
        return bool(cls.ARTICLE_URL_PATTERN.search(url))

    def _is_article_url(self, url: str) -> bool:
        """Совместимость с прежним приватным именем."""
        return self.is_article_url(url)

    def _normalize_url(self, url: str) -> str:
        """
        Отбрасывает якорь и приводит URL к каноничному виду.

        Без этого одна и та же новость с '#comments' и без него считается двумя
        разными записями (UNIQUE-индекс по url их не склеивает).
        """
        if not url:
            return url
        parts = urlparse(url)
        return urlunparse(parts._replace(fragment=""))

    def _find_next_page(self, soup: BeautifulSoup, current_url: str) -> Optional[str]:
        """
        Ищет ссылку на следующую страницу.

        Поиск ограничен блоками пагинации и точными подписями ссылок: раньше
        подстрочный поиск по всем <a> страницы ловил «Ещё по теме» / «Ещё
        новости» и уводил парсер в произвольный раздел сайта.
        """
        # Относительные ссылки резолвятся от адреса текущей страницы, а не от
        # NEWS_URL: на второй и последующих страницах база уже другая, и
        # ссылка вида "?page=3" или "../3/" от NEWS_URL давала неверный адрес.

        # Стандартная ссылка rel="next"
        link = soup.find("a", rel="next")
        if link and link.get("href"):
            return urljoin(current_url, link["href"])

        # Ссылки внутри блоков пагинации
        for selector in self.PAGINATION_SELECTORS:
            for a in soup.select(selector):
                text = a.get_text(strip=True).lower()
                if text in self.NEXT_PAGE_TEXTS:
                    return urljoin(current_url, a["href"])

        # Пагинация через query-параметр, если ссылок в разметке нет
        if self.PAGE_PARAM:
            return self._numeric_next_page(current_url)

        return None

    def _numeric_next_page(self, current_url: str) -> Optional[str]:
        """Строит URL следующей страницы, увеличивая PAGE_PARAM в текущем URL."""
        parts = urlparse(current_url)
        query = parse_qs(parts.query, keep_blank_values=True)

        raw = query.get(self.PAGE_PARAM, [None])[0]
        try:
            next_page = int(raw) + 1 if raw is not None else self.SECOND_PAGE_NUMBER
        except (TypeError, ValueError):
            next_page = self.SECOND_PAGE_NUMBER

        query[self.PAGE_PARAM] = [str(next_page)]
        return urlunparse(parts._replace(query=urlencode(query, doseq=True)))
    
    def _make_absolute_url(self, href: str) -> str:
        """Преобразует относительную ссылку в абсолютную."""
        if href.startswith("/"):
            return urljoin(self.BASE_URL, href)
        elif href.startswith("http"):
            return href
        else:
            return urljoin(self.NEWS_URL, href)