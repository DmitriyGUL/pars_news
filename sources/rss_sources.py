"""
Источники, читающие RSS-ленты.

Делятся на два вида:

* Профильные (Forbes, CNews, vc.ru, Frank Media) — тематика издания и так
  близка к задаче, берём ленту целиком.
* Федеральные (Коммерсантъ, Ведомости, ТАСС, Интерфакс, РБК) — пишут обо всём,
  поэтому к ним применяется отбор TOPIC_FILTER: нужна кадровая лексика вместе
  с деловым контекстом. Иначе на одну кадровую новость приходились бы сотни
  спортивных и военных сводок, а «назначение пенальти» считалось бы
  назначением руководителя.

Проверять новый фид удобно так:

    py -c "from sources.rss_sources import CnewsParser as P; \
           print(len(P().fetch(limit=20, days=30)))"
"""

from __future__ import annotations

import re
from typing import List

from models import NewsItem
from tagging import is_hr_business_news
from .rss_parser import RssParser


class ForbesFeedParser(RssParser):
    """Общая лента forbes.ru.

    Раздел «Новости компаний» отдельного фида не имеет, а его листинг
    подгружается скриптом и вглубь не листается (см. forbes_companies) —
    поэтому лента дополняет тот источник, а не заменяет его.
    """

    SOURCE_NAME = "forbes_feed"
    FEED_URLS = ("https://www.forbes.ru/newrss.xml",)
    ARTICLE_URL_PATTERN = re.compile(r"forbes\.ru/[a-z-]+/\d+-")


class CnewsParser(RssParser):
    """CNews — ИТ-рынок, вендоры и госинформатизация."""

    SOURCE_NAME = "cnews"
    FEED_URLS = ("https://www.cnews.ru/inc/rss/news.xml",)


class VcParser(RssParser):
    """vc.ru — бизнес и технологии."""

    SOURCE_NAME = "vc"
    FEED_URLS = ("https://vc.ru/rss/all",)


class FrankMediaParser(RssParser):
    """Frank Media — банки и финансовый сектор."""

    SOURCE_NAME = "frankmedia"
    FEED_URLS = ("https://frankmedia.ru/feed",)


# --- Федеральные ленты: только кадровые новости --------------------------

class KommersantParser(RssParser):
    """«Коммерсантъ», отобранное по кадровой лексике."""

    SOURCE_NAME = "kommersant"
    FEED_URLS = ("https://www.kommersant.ru/RSS/news.xml",)
    TOPIC_FILTER = staticmethod(is_hr_business_news)


class VedomostiParser(RssParser):
    """«Ведомости», отобранное по кадровой лексике."""

    SOURCE_NAME = "vedomosti"
    FEED_URLS = ("https://www.vedomosti.ru/rss/news",)
    TOPIC_FILTER = staticmethod(is_hr_business_news)


class TassParser(RssParser):
    """ТАСС, отобранное по кадровой лексике."""

    SOURCE_NAME = "tass"
    FEED_URLS = ("https://tass.ru/rss/v2.xml",)
    TOPIC_FILTER = staticmethod(is_hr_business_news)


class InterfaxParser(RssParser):
    """«Интерфакс», отобранное по кадровой лексике."""

    SOURCE_NAME = "interfax"
    FEED_URLS = ("https://www.interfax.ru/rss.asp",)
    TOPIC_FILTER = staticmethod(is_hr_business_news)


class RbcFeedParser(RssParser):
    """Лента РБК, отобранное по кадровой лексике.

    Дополняет rbc_companies: тот берёт раздел «Новости компаний», а здесь
    кадровые новости из общей ленты.
    """

    SOURCE_NAME = "rbc_feed"
    FEED_URLS = ("https://rssexport.rbc.ru/rbcnews/news/30/full.rss",)
    TOPIC_FILTER = staticmethod(is_hr_business_news)


def _make_fetch(parser_class):
    """Функция-обёртка fetch для источника — единый интерфейс с main.py."""

    def fetch(limit: int = 200, days: int = 7, with_summaries: bool = True,
              max_pages: int | None = None) -> List[NewsItem]:
        return parser_class().fetch(
            limit, days, with_summaries=with_summaries, max_pages=max_pages
        )

    fetch.__doc__ = f"Новости источника {parser_class.SOURCE_NAME}."
    return fetch


fetch_forbes_feed = _make_fetch(ForbesFeedParser)
fetch_cnews = _make_fetch(CnewsParser)
fetch_vc = _make_fetch(VcParser)
fetch_frankmedia = _make_fetch(FrankMediaParser)
fetch_kommersant = _make_fetch(KommersantParser)
fetch_vedomosti = _make_fetch(VedomostiParser)
fetch_tass = _make_fetch(TassParser)
fetch_interfax = _make_fetch(InterfaxParser)
fetch_rbc_feed = _make_fetch(RbcFeedParser)
