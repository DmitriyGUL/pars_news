from __future__ import annotations

import json
import logging
import re
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from typing import Dict, Iterable, NamedTuple, Optional

import requests
from bs4 import BeautifulSoup, Tag

from models import NewsItem


logger = logging.getLogger(__name__)

RU_MONTHS = {
    "января": 1,
    "февраля": 2,
    "марта": 3,
    "апреля": 4,
    "мая": 5,
    "июня": 6,
    "июля": 7,
    "августа": 8,
    "сентября": 9,
    "октября": 10,
    "ноября": 11,
    "декабря": 12,
    "янв": 1,
    "фев": 2,
    "мар": 3,
    "апр": 4,
    "май": 5,
    "июн": 6,
    "июл": 7,
    "авг": 8,
    "сен": 9,
    "окт": 10,
    "ноя": 11,
    "дек": 12,
}

DATE_PATTERNS = (
    re.compile(r"(\d{1,2})[./](\d{1,2})[./](\d{2,4})"),
    re.compile(
        r"(\d{1,2})\s+(" + "|".join(RU_MONTHS.keys()) + r")(?:\s+(\d{4}))?",
        re.IGNORECASE,
    ),
)

URL_DATE_PATTERNS = (
    re.compile(r"/(\d{4})/(\d{2})/(\d{2})(?:/|$)"),
    re.compile(r"/(\d{4})-(\d{2})-(\d{2})(?:/|$)"),
    re.compile(r"/(\d{8})(?:/|$)"),
)

# Машинно-читаемые места, где сайты публикуют дату материала. Только они (и
# ld+json) считаются надёжными: свободный текст страницы использовать нельзя —
# в шапке сайта обычно висят часы с сегодняшней датой, и именно они раньше
# записывались в published_at вместо реальной даты публикации.
STRUCTURED_DATE_SELECTORS = (
    'meta[property="article:published_time"]',
    'meta[property="og:article:published_time"]',
    'meta[itemprop="datePublished"]',
    'meta[name="pubdate"]',
    'meta[name="publish-date"]',
    'meta[name="publication_date"]',
    'meta[name="date"]',
    "time[datetime]",
    "time[itemprop='datePublished']",
    "[itemprop='datePublished'][content]",
)

# Элементы, в которых лежит человекочитаемая дата материала. Ищутся только
# внутри основного содержимого, из которого удалены шапка, меню и подвал.
DATE_ELEMENT_SELECTORS = (
    "[class*='publish']",
    "[class*='pubdate']",
    "[class*='article-date']",
    "[class*='article__date']",
    "[class*='news-date']",
    "[class*='post-date']",
    "[class*='date']",
    "time",
)

# Обвязка страницы, которую нужно выкинуть перед поиском даты в тексте.
CHROME_SELECTORS = ("header", "nav", "footer", "aside", "script", "style", "noscript")

# Контейнеры основного содержимого страницы (в порядке предпочтения).
MAIN_CONTENT_SELECTORS = (
    "article",
    "[itemprop='articleBody']",
    "[class*='article__body']",
    "[class*='article-body']",
    "[class*='node__content']",
    "main",
    "[role='main']",
)

# Дата публикации не может быть в будущем и не может быть доисторической.
_MIN_VALID_YEAR = 2000
_FUTURE_TOLERANCE = timedelta(days=1)

RELATIVE_PATTERNS = (
    (re.compile(r"^(\d+)\s*(?:мин|min)", re.IGNORECASE), "minutes"),
    (re.compile(r"^(\d+)\s*(?:час|hour|hr)", re.IGNORECASE), "hours"),
    (re.compile(r"^(\d+)\s*(?:дн|дня|дней|day)", re.IGNORECASE), "days"),
)


def is_plausible_publication_date(value: Optional[datetime]) -> bool:
    """Отсекает мусорные даты: из будущего и заведомо неправдоподобно старые."""
    if value is None:
        return False
    naive = to_naive_local(value)
    if naive.year < _MIN_VALID_YEAR:
        return False
    return naive <= datetime.now() + _FUTURE_TOLERANCE


def parse_relative_date(text: str) -> Optional[datetime]:
    """
    Разбирает относительные даты: «сегодня», «вчера», «2 часа назад».

    Вызывается только для коротких подписей из элементов с датой — в обычном
    тексте статьи слова «сегодня» и «вчера» встречаются сплошь и рядом.
    """
    if not text:
        return None

    normalized = " ".join(text.split()).strip().lower()
    if len(normalized) > 30:
        return None

    now = datetime.now()
    if normalized.startswith(("сегодня", "today")):
        return now.replace(hour=0, minute=0, second=0, microsecond=0)
    if normalized.startswith(("вчера", "yesterday")):
        return (now - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)

    for pattern, unit in RELATIVE_PATTERNS:
        match = pattern.match(normalized)
        if match:
            return now - timedelta(**{unit: int(match.group(1))})

    return None


def to_naive_local(value: Optional[datetime]) -> Optional[datetime]:
    """
    Приводит дату к наивной в локальной зоне.

    Часть источников (например Forbes) отдаёт даты со смещением "+03:00", а
    часть — без него. Сравнение таких дат между собой или с datetime.now()
    падает с TypeError, поэтому все даты нормализуются сразу после разбора.
    """
    if value is None or value.tzinfo is None:
        return value
    return value.astimezone().replace(tzinfo=None)


def _parse_iso_datetime(value: str) -> Optional[datetime]:
    cleaned = value.strip()
    if not cleaned:
        return None

    cleaned = cleaned.replace("Z", "+00:00")
    for candidate in (cleaned, cleaned.split("+")[0], cleaned.split(".")[0]):
        try:
            # Единая точка нормализации: ISO — единственный источник дат
            # со смещением, числовые форматы всегда дают наивную дату.
            return to_naive_local(datetime.fromisoformat(candidate))
        except ValueError:
            continue
    return None


def _parse_numeric_date(day: int, month: int, year: int) -> Optional[datetime]:
    if year < 100:
        year += 2000
    try:
        return datetime(year, month, day)
    except ValueError:
        return None


def parse_date_from_text(text: str) -> Optional[datetime]:
    if not text:
        return None

    normalized = " ".join(text.split())

    match = DATE_PATTERNS[0].search(normalized)
    if match:
        day, month, year = map(int, match.groups())
        parsed = _parse_numeric_date(day, month, year)
        if parsed:
            return parsed

    match = DATE_PATTERNS[1].search(normalized.lower())
    if match:
        day = int(match.group(1))
        month = RU_MONTHS[match.group(2).lower()]
        if match.group(3):
            return _parse_numeric_date(day, month, int(match.group(3)))

        # Год не указан («5 декабря»): берём текущий, а если дата уехала в
        # будущее — значит это материал прошлого года.
        parsed = _parse_numeric_date(day, month, datetime.now().year)
        if parsed and not is_plausible_publication_date(parsed):
            parsed = _parse_numeric_date(day, month, datetime.now().year - 1)
        return parsed

    return None


def parse_date_from_url(url: str) -> Optional[datetime]:
    for pattern in URL_DATE_PATTERNS:
        match = pattern.search(url)
        if not match:
            continue

        groups = match.groups()
        if len(groups) == 3:
            year, month, day = map(int, groups)
            parsed = _parse_numeric_date(day, month, year)
        else:
            raw = groups[0]
            if len(raw) != 8:
                continue
            parsed = _parse_numeric_date(int(raw[6:8]), int(raw[4:6]), int(raw[:4]))

        if is_plausible_publication_date(parsed):
            return parsed

    return None


def _date_from_node(node: Tag) -> Optional[datetime]:
    """Достаёт дату из одного элемента: сперва атрибуты, затем его подпись."""
    for attr in ("datetime", "content"):
        value = node.get(attr)
        if isinstance(value, str):
            parsed = _parse_iso_datetime(value) or parse_date_from_text(value)
            if is_plausible_publication_date(parsed):
                return parsed

    text = node.get_text(" ", strip=True)
    parsed = parse_date_from_text(text) or parse_relative_date(text)
    if is_plausible_publication_date(parsed):
        return parsed
    return None


def parse_date_from_tag(block: Tag) -> Optional[datetime]:
    """
    Дата из блока новости в листинге.

    Сначала проверяются элементы с машинно-читаемой датой, и только потом —
    текст самого блока. Свободный текст берётся именно у блока новости, а не у
    страницы целиком, поэтому часы в шапке сайта сюда не попадают.
    """
    for selector in STRUCTURED_DATE_SELECTORS:
        for node in block.select(selector):
            parsed = _date_from_node(node)
            if parsed:
                return parsed

    for selector in DATE_ELEMENT_SELECTORS:
        for node in block.select(selector):
            parsed = _date_from_node(node)
            if parsed:
                return parsed

    text = block.get_text(" ", strip=True)
    parsed = parse_date_from_text(text)
    return parsed if is_plausible_publication_date(parsed) else None


def _date_from_ld_json(soup: BeautifulSoup) -> Optional[datetime]:
    """Дата публикации из микроразметки schema.org (ld+json)."""
    for script in soup.find_all("script", {"type": "application/ld+json"}):
        if not script.string:
            continue
        try:
            data = json.loads(script.string)
        except json.JSONDecodeError:
            continue

        nodes = []
        if isinstance(data, dict):
            nodes.append(data)
            graph = data.get("@graph")
            if isinstance(graph, list):
                nodes.extend(graph)
        elif isinstance(data, list):
            nodes.extend(data)

        for node in nodes:
            if not isinstance(node, dict):
                continue
            for key in ("datePublished", "dateCreated", "uploadDate"):
                value = node.get(key)
                if isinstance(value, str):
                    parsed = _parse_iso_datetime(value)
                    if is_plausible_publication_date(parsed):
                        return parsed

    return None


def _main_content(soup: BeautifulSoup) -> Optional[Tag]:
    """
    Возвращает контейнер основного содержимого без шапки, меню и подвала.

    Именно из-за их содержимого дата сбора попадала в published_at: например, в
    шапке comnews.ru стоит виджет с текущей датой («07.08.2026, Пт»), и разбор
    текста всей страницы возвращал сегодняшнее число для любой старой новости.
    """
    for selector in MAIN_CONTENT_SELECTORS:
        node = soup.select_one(selector)
        if node is None:
            continue

        for chrome in node.select(",".join(CHROME_SELECTORS)):
            chrome.decompose()
        return node

    return None


def parse_date_from_html(html: str) -> Optional[datetime]:
    """
    Дата публикации со страницы статьи.

    Порядок: машинно-читаемые теги -> ld+json -> элементы с датой внутри
    основного содержимого. Если ничего не нашлось, возвращается None: пустая
    дата честнее, чем подставленная дата сбора.
    """
    return _date_from_soup(BeautifulSoup(html, "html.parser"))


def _date_from_soup(soup: BeautifulSoup) -> Optional[datetime]:
    """Реализация parse_date_from_html для уже разобранного дерева."""
    for selector in STRUCTURED_DATE_SELECTORS:
        for node in soup.select(selector):
            parsed = _date_from_node(node)
            if parsed:
                return parsed

    parsed = _date_from_ld_json(soup)
    if parsed:
        return parsed

    content = _main_content(soup)
    if content is None:
        return None

    for selector in DATE_ELEMENT_SELECTORS:
        for node in content.select(selector):
            parsed = _date_from_node(node)
            if parsed:
                return parsed

    return None


# --- Лид статьи ------------------------------------------------------------

# Короткие обрывки ("Фото: ТАСС", "Читайте также") лидом не считаем, а очень
# длинный текст в БД не нужен: теги считаются по первым фразам.
SUMMARY_MIN_LENGTH = 60
SUMMARY_MAX_LENGTH = 600

# Лид, который сайт сам объявил кратким описанием материала. Такие описания
# чище первого абзаца: без подписей к фото и врезок.
SUMMARY_META_SELECTORS = (
    'meta[property="og:description"]',
    'meta[name="description"]',
    'meta[itemprop="description"]',
)


# Лид партнёрских материалов начинается с названия компании-автора:
# «Ассоциация юристов в сфере ликвидации и банкротства: ФНС вынесла...».
# Это подпись, а не содержание: она давала новости чужие теги (банкротство,
# ликвидация) и приписывала ей компанию-автора. Срезаем.
AUTHOR_PREFIX = re.compile(r"^[^:]{0,60}:\s*")


def strip_author_prefix(text: str) -> str:
    """Убирает ведущую подпись автора («ООО «Ромашка»: ») из лида."""
    return AUTHOR_PREFIX.sub("", text, count=1)


def _clean_summary(value: str) -> Optional[str]:
    """Схлопывает пробелы, срезает подпись автора и отбрасывает обрывки."""
    text = strip_author_prefix(" ".join(value.split()))
    if len(text) < SUMMARY_MIN_LENGTH:
        return None
    return text[:SUMMARY_MAX_LENGTH]


def parse_summary_from_html(soup: BeautifulSoup) -> Optional[str]:
    """
    Лид материала: сначала мета-описание, затем первый содержательный абзац.

    Абзац берётся только из основного содержимого страницы — в шапке и подвале
    лежат анонсы других материалов, и они исказили бы теги новости.
    """
    for selector in SUMMARY_META_SELECTORS:
        node = soup.select_one(selector)
        if node is None:
            continue
        value = node.get("content")
        if isinstance(value, str):
            cleaned = _clean_summary(value)
            if cleaned:
                return cleaned

    content = _main_content(soup)
    if content is None:
        return None

    for paragraph in content.find_all("p"):
        cleaned = _clean_summary(paragraph.get_text(" ", strip=True))
        if cleaned:
            return cleaned

    return None


class ArticleMeta(NamedTuple):
    """Данные, которые вытаскиваются из страницы статьи за один запрос."""

    published_at: Optional[datetime] = None
    summary: Optional[str] = None


def parse_article_meta(html: str) -> ArticleMeta:
    """Дата публикации и лид из HTML статьи — с единственным разбором дерева."""
    soup = BeautifulSoup(html, "html.parser")
    # Порядок важен: parse_summary_from_html вырезает из дерева шапку и подвал,
    # поэтому дату ищем первой — часть сайтов держит её в <header> статьи.
    return ArticleMeta(_date_from_soup(soup), parse_summary_from_html(soup))


# Сколько статей догружаем параллельно. Небольшое значение, чтобы не создавать
# заметную нагрузку на сайт-источник.
DEFAULT_MAX_WORKERS = 4

REQUEST_TIMEOUT = 15

# Как часто сообщать о прогрессе догрузки статей.
PROGRESS_EVERY = 25

# У requests.Session нет гарантий потокобезопасности, поэтому держим отдельную
# сессию на каждый рабочий поток (keep-alive при этом сохраняется).
_thread_local = threading.local()


def _get_thread_session(headers: Dict[str, str]) -> requests.Session:
    session = getattr(_thread_local, "session", None)
    if session is None:
        session = requests.Session()
        session.headers.update(headers)
        _thread_local.session = session
    return session


def decode_response(resp: requests.Response) -> str:
    """
    Возвращает текст ответа с корректной кодировкой.

    Многие российские сайты не указывают charset в заголовке, и requests
    откатывается на latin-1, превращая кириллицу в мусор. apparent_encoding
    определяет кодировку по содержимому.
    """
    if resp.encoding is None or resp.encoding.lower() == "iso-8859-1":
        resp.encoding = resp.apparent_encoding or "utf-8"
    return resp.text


def fetch_article_meta(
    url: str,
    headers: Dict[str, str],
    session: Optional[requests.Session] = None,
) -> ArticleMeta:
    """Дата и лид со страницы статьи; пустой ArticleMeta, если она недоступна."""
    http = session if session is not None else _get_thread_session(headers)
    try:
        resp = http.get(url, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        return parse_article_meta(decode_response(resp))
    except requests.RequestException:
        return ArticleMeta()


def fetch_article_date(
    url: str,
    headers: Dict[str, str],
    session: Optional[requests.Session] = None,
) -> Optional[datetime]:
    """Дата публикации со страницы статьи; None, если страница недоступна."""
    return fetch_article_meta(url, headers, session).published_at


def enrich_news_items(
    items: Iterable[NewsItem],
    headers: Dict[str, str],
    fetch_missing: bool = True,
    max_workers: int = DEFAULT_MAX_WORKERS,
    fetch_summaries: bool = True,
) -> list[NewsItem]:
    """
    Проставляет новостям published_at и лид (summary), которых у них нет.

    Дата сначала извлекается из URL — это бесплатно. Страница статьи грузится,
    если не хватает даты либо лида, ровно по одному разу на уникальный URL.

    Лид нужен анализу тегов: по одному заголовку в 80 символов тема новости
    определяется плохо. Если лид не нужен, передайте fetch_summaries=False —
    тогда сеть используется только для новостей с неизвестной датой.
    """
    items = list(items)

    # Шаг 1: дешёвое определение даты из URL
    dates: Dict[str, Optional[datetime]] = {}
    summaries: Dict[str, Optional[str]] = {}
    for item in items:
        if item.url in dates:
            continue
        dates[item.url] = item.published_at or parse_date_from_url(item.url)
        summaries[item.url] = item.summary

    # Шаг 2: сетевая догрузка только того, чего не хватает
    to_fetch = [
        url for url in dates
        if dates[url] is None or (fetch_summaries and not summaries[url])
    ]
    if fetch_missing and to_fetch:
        workers = max(1, min(max_workers, len(to_fetch)))
        logger.info("Догрузка страниц статей: %d шт. в %d потока", len(to_fetch), workers)

        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {
                pool.submit(fetch_article_meta, url, headers): url
                for url in to_fetch
            }
            for done, future in enumerate(as_completed(futures), 1):
                # Прогресс нужен: без него прогон надолго замолкает, и это
                # выглядит как зависание.
                if done % PROGRESS_EVERY == 0 or done == len(to_fetch):
                    logger.info("  догружено %d из %d", done, len(to_fetch))

                url = futures[future]
                try:
                    meta = future.result()
                except Exception:  # noqa: BLE001 — сбой одной статьи не роняет прогон
                    continue

                # Уже известные значения не затираем: дата из листинга точнее
                # угаданной со страницы.
                dates[url] = dates[url] or meta.published_at
                summaries[url] = summaries[url] or meta.summary

    enriched: list[NewsItem] = []
    for item in items:
        enriched.append(
            NewsItem(
                title=item.title,
                url=item.url,
                source=item.source,
                published_at=item.published_at or dates.get(item.url),
                summary=item.summary or summaries.get(item.url),
            )
        )

    return enriched
