"""
Оркестрация парсеров новостей.

Единая точка входа для командной строки — cli.py. Этот модуль оставлен как
библиотечный (и как совместимый способ запуска: `py main.py ...` просто
делегирует в cli.py).
"""

from __future__ import annotations

import logging
import sys
import time
from typing import Callable, Dict, List, Sequence, Tuple

from models import NewsItem
from sources import adindex, comnews, forbes_companies, rb, rbc_companies, ria_companies
from sources import rss_sources, telegram_sources


logger = logging.getLogger(__name__)

# Список источников: (имя, функция получения новостей).
#
# Три группы:
#   1. Профильные листинги — разделы про кадры и компании, обходятся вглубь.
#   2. Профильные ленты — издания, чья тематика и так близка к задаче.
#   3. Федеральные ленты — пишут обо всём, поэтому внутри отфильтрованы по
#      кадровой лексике вместе с деловым контекстом (см. rss_sources).
#
# Чтобы отключить источник, достаточно убрать строку из этого кортежа.
PARSERS: Sequence[Tuple[str, Callable[..., List[NewsItem]]]] = (
    # 1. Профильные листинги
    ("adindex", adindex.fetch),
    ("comnews", comnews.fetch),
    ("rbc_companies", rbc_companies.fetch),
    ("ria_companies", ria_companies.fetch),
    ("forbes_companies", forbes_companies.fetch),
    ("rb_hr", rb.fetch),

    # 2. Профильные ленты
    ("rb_feed", rb.fetch_feed),
    ("forbes_feed", rss_sources.fetch_forbes_feed),
    ("cnews", rss_sources.fetch_cnews),
    ("vc", rss_sources.fetch_vc),
    ("frankmedia", rss_sources.fetch_frankmedia),

    # 3. Telegram-каналы
    ("telegram_hr", telegram_sources.fetch_hr),
    ("telegram_business", telegram_sources.fetch_business),

    # 4. Федеральные ленты (только кадровые новости)
    ("kommersant", rss_sources.fetch_kommersant),
    ("vedomosti", rss_sources.fetch_vedomosti),
    ("tass", rss_sources.fetch_tass),
    ("interfax", rss_sources.fetch_interfax),
    ("rbc_feed", rss_sources.fetch_rbc_feed),
)


# Классы парсеров по имени источника. Нужен командам, которые проверяют уже
# сохранённые записи (cleanup): у каждого класса есть is_article_url.
#
# Реестр обязан покрывать все имена из PARSERS — иначе cleanup сочтёт записи
# неизвестного источника мусором и удалит их. Это проверяется тестом.
PARSER_CLASSES: Dict[str, type] = {
    "adindex": adindex.AdindexParser,
    "comnews": comnews.ComnewsParser,
    "rbc_companies": rbc_companies.RbcCompaniesParser,
    "ria_companies": ria_companies.RiaCompaniesParser,
    "forbes_companies": forbes_companies.ForbesCompaniesParser,
    "rb_hr": rb.RbHrParser,
    "rb_feed": rb.RbFeedParser,
    "forbes_feed": rss_sources.ForbesFeedParser,
    "cnews": rss_sources.CnewsParser,
    "vc": rss_sources.VcParser,
    "frankmedia": rss_sources.FrankMediaParser,
    "telegram_hr": telegram_sources.TelegramHrParser,
    "telegram_business": telegram_sources.TelegramBusinessParser,
    "kommersant": rss_sources.KommersantParser,
    "vedomosti": rss_sources.VedomostiParser,
    "tass": rss_sources.TassParser,
    "interfax": rss_sources.InterfaxParser,
    "rbc_feed": rss_sources.RbcFeedParser,
}


def run_all_parsers(
    days: int = 7,
    limit_per_source: int = 200,
    with_summaries: bool = True,
    max_pages: int | None = None,
    only_sources: Sequence[str] | None = None,
) -> List[NewsItem]:
    """Запускает все парсеры и возвращает собранные новости.

    Падение одного источника не останавливает остальные. `with_summaries`
    управляет догрузкой лида статьи — без него теги считаются по заголовку.
    `max_pages` задаёт глубину обхода листингов, `only_sources` — подмножество
    источников (удобно, когда нужен один сайт).
    """
    collected: List[NewsItem] = []
    planned = [
        (name, func) for name, func in PARSERS
        if not only_sources or name in only_sources
    ]

    for number, (source_name, fetch_func) in enumerate(planned, 1):
        # Номер источника в логе: по нему видно, на каком именно прогон встал,
        # даже если сообщение об ошибке потерялось.
        logger.info("[%d/%d] %s: старт", number, len(planned), source_name)
        started = time.monotonic()

        try:
            items = fetch_func(
                limit=limit_per_source, days=days,
                with_summaries=with_summaries, max_pages=max_pages,
            )
        except Exception:  # noqa: BLE001 — один источник не должен ронять прогон
            # exc_info=True: без трейсбека по одной строке причину не найти,
            # а прогон длинный и повторить его дорого.
            logger.exception("[%d/%d] %s: источник упал", number, len(planned), source_name)
            continue

        logger.info(
            "[%d/%d] %s: получено %d записей за %.0f с",
            number, len(planned), source_name, len(items), time.monotonic() - started,
        )
        collected.extend(items)

    return collected


if __name__ == "__main__":
    from cli import main

    sys.exit(main())
