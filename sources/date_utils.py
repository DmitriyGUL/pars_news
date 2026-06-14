from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from typing import Dict, Iterable, Optional

import requests
from bs4 import BeautifulSoup, Tag

from models import NewsItem


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


def _parse_iso_datetime(value: str) -> Optional[datetime]:
    cleaned = value.strip()
    if not cleaned:
        return None

    cleaned = cleaned.replace("Z", "+00:00")
    for candidate in (cleaned, cleaned.split("+")[0], cleaned.split(".")[0]):
        try:
            return datetime.fromisoformat(candidate)
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
        year = int(match.group(3)) if match.group(3) else datetime.now().year
        return _parse_numeric_date(day, month, year)

    lowered = normalized.lower()
    parts = lowered.split()
    if len(parts) >= 2 and parts[1].startswith("hour"):
        try:
            return datetime.now() - timedelta(hours=int(parts[0]))
        except ValueError:
            pass
    if len(parts) >= 2 and parts[1].startswith("day"):
        try:
            return datetime.now() - timedelta(days=int(parts[0]))
        except ValueError:
            pass

    return None


def parse_date_from_url(url: str) -> Optional[datetime]:
    for pattern in URL_DATE_PATTERNS:
        match = pattern.search(url)
        if not match:
            continue

        groups = match.groups()
        if len(groups) == 3:
            year, month, day = map(int, groups)
            return _parse_numeric_date(day, month, year)

        raw = groups[0]
        if len(raw) == 8:
            year = int(raw[:4])
            month = int(raw[4:6])
            day = int(raw[6:8])
            return _parse_numeric_date(day, month, year)

    return None


def parse_date_from_tag(block: Tag) -> Optional[datetime]:
    time_tag = block.find("time")
    if time_tag:
        dt_attr = time_tag.get("datetime")
        if isinstance(dt_attr, str):
            parsed = _parse_iso_datetime(dt_attr)
            if parsed:
                return parsed

        parsed = parse_date_from_text(time_tag.get_text(strip=True))
        if parsed:
            return parsed

    for attr in ("content", "datetime"):
        meta = block.find("meta", attrs={attr: True})
        if meta and meta.get(attr):
            parsed = _parse_iso_datetime(str(meta[attr]))
            if parsed:
                return parsed

    meta_published = block.find("meta", attrs={"property": "article:published_time"})
    if meta_published and meta_published.get("content"):
        parsed = _parse_iso_datetime(str(meta_published["content"]))
        if parsed:
            return parsed

    return parse_date_from_text(block.get_text(" ", strip=True))


def parse_date_from_html(html: str) -> Optional[datetime]:
    soup = BeautifulSoup(html, "html.parser")

    for selector in (
        "time[datetime]",
        'meta[property="article:published_time"]',
        'meta[name="pubdate"]',
        'meta[name="publish-date"]',
        'meta[itemprop="datePublished"]',
    ):
        node = soup.select_one(selector)
        if not node:
            continue

        value = node.get("datetime") or node.get("content")
        if isinstance(value, str):
            parsed = _parse_iso_datetime(value)
            if parsed:
                return parsed

        parsed = parse_date_from_text(node.get_text(strip=True))
        if parsed:
            return parsed

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
                    if parsed:
                        return parsed

    article = soup.find("article") or soup.body
    if article:
        parsed = parse_date_from_tag(article)
        if parsed:
            return parsed

    return parse_date_from_text(soup.get_text(" ", strip=True)[:2000])


def fetch_article_date(url: str, headers: Dict[str, str], cache: Dict[str, Optional[datetime]]) -> Optional[datetime]:
    if url in cache:
        return cache[url]

    try:
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        parsed = parse_date_from_html(resp.text)
    except requests.RequestException:
        parsed = None

    cache[url] = parsed
    return parsed


def resolve_published_at(
    block: Tag,
    url: str,
    headers: Dict[str, str],
    cache: Optional[Dict[str, Optional[datetime]]] = None,
    fetch_article: bool = True,
) -> Optional[datetime]:
    cache = cache if cache is not None else {}

    for resolver in (
        lambda: parse_date_from_tag(block),
        lambda: parse_date_from_url(url),
    ):
        parsed = resolver()
        if parsed:
            return parsed

    if fetch_article:
        return fetch_article_date(url, headers, cache)
    return None


def enrich_news_items(
    items: Iterable[NewsItem],
    headers: Dict[str, str],
    fetch_missing: bool = True,
) -> list[NewsItem]:
    cache: Dict[str, Optional[datetime]] = {}
    enriched: list[NewsItem] = []

    for item in items:
        if item.published_at:
            enriched.append(item)
            continue

        published_at = parse_date_from_url(item.url)
        if not published_at and fetch_missing:
            published_at = fetch_article_date(item.url, headers, cache)

        enriched.append(
            NewsItem(
                title=item.title,
                url=item.url,
                source=item.source,
                published_at=published_at,
                summary=item.summary,
            )
        )

    return enriched
