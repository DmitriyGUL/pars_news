"""
Конкретные Telegram-каналы, подключённые к проекту.

Каналы делятся так же, как ленты RSS:

* Профильные — пишут преимущественно по теме, берём целиком.
* Широкие — деловая лента обо всём, поэтому к ним применяется TOPIC_FILTER:
  нужна кадровая лексика вместе с деловым контекстом.

Прежде чем добавлять канал, проверьте, что он читается без бота, — годятся
только публичные каналы с включённым предпросмотром:

    py -c "from sources.telegram import probe_channel; probe_channel('banksta')"

Если постов ноль, канал закрыт, предпросмотр выключен или такого имени нет.

Осторожно с дублями: если канал — это лента издания, которое уже подключено
через RSS (Коммерсантъ, ТАСС, Ведомости, Интерфакс, Forbes, РБК, AdIndex,
Frank Media), те же новости придут дважды под разными адресами: ссылкой на
сайт и ссылкой на пост. Дедупликация в БД идёт по URL и такие пары не
склеивает. Поэтому здесь только каналы без уже подключённого сайта.
"""

from __future__ import annotations

from typing import List

from models import NewsItem
from tagging import is_hr_business_news
from .telegram import TelegramParser


class TelegramBusinessParser(TelegramParser):
    """
    Широкие деловые каналы — только кадровые новости.

    Каналы пишут обо всём подряд (санкции, рынки, политика), поэтому без
    отбора они забили бы базу так же, как федеральные ленты.
    """

    SOURCE_NAME = "telegram_business"
    CHANNELS = (
        "banksta",          # Банкста — банки и финансы
        "if_market_news",   # IF News — рынки и экономика
    )
    TOPIC_FILTER = staticmethod(is_hr_business_news)


class TelegramHrParser(TelegramParser):
    """
    Профильные кадровые каналы — берутся целиком.

    Отбор по кадровой теме им не нужен: они и так про кадры, а фильтр отрезал
    бы, например, разбор рынка труда без слова «назначен».

    Все каналы проверены на чтение через t.me/s/. Прежде чем добавлять новый,
    прогоните probe_channel — примерно половина произвольно взятых имён
    оказывается закрытой или несуществующей.
    """

    SOURCE_NAME = "telegram_hr"
    CHANNELS = (
        "hranalitycs",      # HR-аналитика
        "labor_market",     # Рынок Труда
        "shl_hr_club",      # HR Club
        "neohr",            # Neo HR
        "shltools",         # SHLTOOLS
        "HR_portal",        # HR трансформация
        "hrtechnology",     # Поток
        "huntflow",         # Хантфлоу
        "friendwork",       # FriendWork
        "rff_channel",      # Recruitment for Friends
        "whrdata",          # Красивая аналитика | HR data
        "hrhuballevents",   # HR [хаб] ВСЕ события
        "hrzarplata",       # hr.zarplata.ru
        "rus_hr",           # Русский HR
    )


def fetch_business(limit: int = 200, days: int = 7, with_summaries: bool = True,
                   max_pages: int | None = None) -> List[NewsItem]:
    """Кадровые новости из широких деловых каналов."""
    return TelegramBusinessParser().fetch(
        limit, days, with_summaries=with_summaries, max_pages=max_pages
    )


def fetch_hr(limit: int = 200, days: int = 7, with_summaries: bool = True,
             max_pages: int | None = None) -> List[NewsItem]:
    """Профильные кадровые каналы."""
    return TelegramHrParser().fetch(
        limit, days, with_summaries=with_summaries, max_pages=max_pages
    )
