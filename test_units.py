#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Юнит-тесты чистых функций проекта: детектор компаний, разбор дат, фильтры URL.

Запуск: py test_units.py   (или: py -m pytest test_units.py)
Сеть и база данных не используются.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta

from bs4 import BeautifulSoup

from company_analyzer import (
    ALIAS_CONTEXT,
    AMBIGUOUS_ALIASES,
    COMPANY_ALIASES,
    REQUIRED_COMPANIES,
    _extract_snippet_with_company,
    analyze_news_for_companies,
    detect_companies_in_text,
    news_items_to_rows,
)
from models import NewsItem
from sources import adindex, comnews, forbes_companies, rbc_companies, ria_companies
from sources.date_utils import (
    _parse_iso_datetime,
    is_plausible_publication_date,
    parse_article_meta,
    parse_date_from_html,
    parse_date_from_text,
    parse_date_from_url,
    parse_relative_date,
    parse_summary_from_html,
    to_naive_local,
)
import requests

from sources.base_parser import BaseParser
from sources.rb import RbHrParser
from sources.telegram import TelegramParser
from sources.rss_parser import RssParser, parse_feed_date
from cli import build_parser
from main import PARSER_CLASSES, PARSERS
from tagging import (
    analyze_text,
    detect_material_type,
    detect_tags,
    hr_signal,
    is_hr_business_news,
)


def _counts(text: str) -> dict:
    return dict(detect_companies_in_text(text))


# --------------------------------------------------------------------------
# Детектор компаний
# --------------------------------------------------------------------------

def test_aliases_are_lowercase_and_unique():
    """Регистровые дубликаты алиасов кратно завышали счётчик упоминаний."""
    for company, aliases in COMPANY_ALIASES.items():
        assert aliases == [a.lower() for a in aliases], f"{company}: алиасы не в нижнем регистре"
        assert len(aliases) == len(set(aliases)), f"{company}: дублирующиеся алиасы"


def test_single_mention_counted_once():
    assert _counts("Газпром объявил о сделке") == {"Газпром": 1}
    assert _counts("Авито запустила новый сервис") == {"Авито": 1}


def test_repeated_mentions_counted_correctly():
    assert _counts("Яндекс и снова Яндекс, а также Яндекс") == {"Яндекс": 3}


def test_distinct_aliases_sum_up():
    """Сбербанк и Сбер — разные алиасы одной компании, оба засчитываются."""
    assert _counts("Сбербанк и Сбер") == {"Сбер": 2}


def test_case_endings_recognized():
    """Падежные формы названия — то же упоминание компании."""
    assert _counts("Топ-менеджер Яндекса перешёл в другую компанию") == {"Яндекс": 1}
    assert _counts("Кадровые изменения в Яндексе") == {"Яндекс": 1}
    assert _counts("совет директоров Ростелекома") == {"Ростелеком": 1}


def test_case_endings_do_not_glue_other_words():
    """Окончания не должны склеивать разные названия и обычные слова."""
    # СберТех — отдельная компания в словаре, а не падежная форма Сбера
    assert "Сбер" not in _counts("СберТех выпустил СУБД")
    # "газета" не должна давать "Группа ГАЗ"
    assert _counts("газета опубликовала статью") == {}
    # Аббревиатуры не склоняются: "мтси" не бывает
    assert _counts("МТС и ВТБ подписали соглашение") == {"МТС": 1, "ВТБ": 1}


def test_nested_aliases_counted_once():
    """Вложенные алиасы одной компании не должны завышать счётчик."""
    assert _counts("Лаборатория Касперского выпустила отчёт") == {
        "Лаборатория Касперского": 1
    }
    # Два разных упоминания той же компании по-прежнему считаются двумя
    assert _counts("Лаборатория Касперского и продукты Касперского") == {
        "Лаборатория Касперского": 2
    }


def test_word_boundaries_respected():
    assert _counts("Газпромбанк это не Газпром") == {"Газпромбанк": 1, "Газпром": 1}


def test_ambiguous_alias_needs_qualifier():
    """Обычные слова не должны считаться компаниями без маркера организации."""
    assert _counts("лента публикаций обновилась") == {}
    assert _counts("цена на газ выросла") == {}
    assert _counts("самолет вылетел с опозданием") == {}
    assert _counts("ядро операционной системы обновлено") == {}
    assert _counts("подросток упал с самоката") == {}


def test_ambiguous_alias_with_qualifier_detected():
    assert _counts("сеть «Лента» открыла магазин") == {"Лента": 1}
    assert _counts('"Магнит" внедряет GitFlic') == {"Магнит": 1}
    # Одно упоминание, хотя подходят оба алиаса — "группа газ" и "газ":
    # вложенные вхождения схлопываются, см. _company_spans.
    assert _counts("группа ГАЗ выпустила грузовик") == {"Группа ГАЗ": 1}
    assert _counts("застройщик Самолет сдал жилищный комплекс") == {"Самолет": 1}


def test_ambiguous_alias_with_industry_context_detected():
    """Отраслевой контекст в тексте заменяет кавычки и слово-квалификатор."""
    assert _counts("Самокат расширил экспресс-доставку продуктов") == {"Самокат": 1}
    assert _counts("YADRO наладила выпуск серверного оборудования") == {"YADRO": 1}


def test_required_companies_are_all_in_dictionary():
    """Обязательный список отслеживания не должен разъезжаться со словарём."""
    assert REQUIRED_COMPANIES <= set(COMPANY_ALIASES)


def test_ambiguous_aliases_exist_in_dictionary():
    """Защита от опечаток: каждый «неоднозначный» алиас должен быть реальным."""
    all_aliases = {a for aliases in COMPANY_ALIASES.values() for a in aliases}
    assert AMBIGUOUS_ALIASES <= all_aliases
    assert set(ALIAS_CONTEXT) <= AMBIGUOUS_ALIASES


def test_empty_text():
    assert detect_companies_in_text("") == []
    assert detect_companies_in_text(None) == []


def test_snippet_never_empty_for_detected_company():
    """Экспорт в Excel режет сниппет строкой, поэтому None недопустим."""
    text = "Компания Яндекс объявила о запуске нового сервиса для бизнеса"
    for company, _ in detect_companies_in_text(text):
        snippet = _extract_snippet_with_company(text, company)
        assert isinstance(snippet, str) and snippet


def test_analyze_news_builds_expected_structure():
    news = [
        NewsItem(title="Газпром и Яндекс", url="https://e.com/1", source="test",
                 published_at=datetime(2026, 8, 1), summary="Газпром снова в новостях"),
    ]
    result = analyze_news_for_companies(news)
    assert set(result) == {"Газпром", "Яндекс"}
    assert result["Газпром"][0]["mention_count"] == 2
    assert result["Яндекс"][0]["mention_count"] == 1


def test_news_rows_include_unmatched_news():
    """Лист «Все новости» должен содержать и новости без компаний."""
    news = [
        NewsItem(title="Яндекс открыл офис", url="https://e.com/1", source="test"),
        NewsItem(title="Погода в Москве испортилась", url="https://e.com/2", source="test"),
    ]
    rows = news_items_to_rows(news)
    assert len(rows) == 2
    assert rows[0]["companies"] == "Яндекс" and rows[0]["companies_count"] == 1
    assert rows[1]["companies"] == "" and rows[1]["companies_count"] == 0


# --------------------------------------------------------------------------
# Теги и влияние на кадровые движения
# --------------------------------------------------------------------------

def test_tags_detected_by_word_stem():
    """Маркер — основа слова, морфология покрывается без словаря словоформ."""
    assert "Сокращения" in detect_tags("Компания объявила о сокращении штата")
    assert "Сокращения" in detect_tags("Банк сократит 200 сотрудников")
    assert "Назначения" in detect_tags("Новым директором назначен Иванов")


def test_tags_absent_for_unrelated_news():
    assert detect_tags("Погода в Москве испортилась") == []
    assert detect_tags("") == []


def test_ambiguous_tag_marker_needs_context():
    """«Суд» без признаков разбирательства не должен давать тег «Суды и санкции»."""
    assert "Суды и санкции" not in detect_tags("Судак пойман в Волге")
    assert "Суды и санкции" in detect_tags("Суд удовлетворил иск к оператору")


def test_material_type_detected():
    assert detect_material_type("Приглашаем на вебинар по подбору персонала") == "Мероприятие"
    assert detect_material_type("Онлайн-курс по кадровому делопроизводству") == "Обучение"
    assert detect_material_type("Исследование: 40% компаний планируют наём") == "Исследование"
    assert detect_material_type("Мы ищем в команду HR-менеджера") == "Вакансия"
    assert detect_material_type("Редколонка: почему растёт текучесть") == "Мнение"
    # обычная новость типа не получает
    assert detect_material_type("Сбербанк сократил штат на 5%") == "Новость"
    assert detect_material_type("") == "Новость"


def test_advertising_wins_over_other_types():
    """Рекламный пост про вебинар остаётся рекламой, а не мероприятием."""
    text = "Приглашаем на вебинар по найму. Промокод HR2026 даёт скидку. erid: 2Vfnxy"
    assert detect_material_type(text) == "Реклама"


def test_promo_material_gets_no_hr_signal():
    """
    Анонс вебинара про сокращения — не кадровое движение.

    Это главная причина, по которой тип материала отделён от темы: раньше
    такой пост получал высокий сигнал наравне с настоящим увольнением.
    """
    text = "Вебинар: как правильно проводить сокращение штата сотрудников"
    analysis = analyze_text(text)
    assert analysis.material_type == "Мероприятие"
    assert "Сокращения" in analysis.tags       # тема определена верно
    assert analysis.signal.level == "нет"      # но событием это не считается
    assert "не сообщает о кадровом событии" in analysis.signal.reason


def test_real_news_keeps_signal_despite_similar_words():
    analysis = analyze_text("Компания сократит штат сотрудников в двух регионах")
    assert analysis.material_type == "Новость"
    assert analysis.signal.level == "высокий"


def test_type_marker_deep_in_text_is_ignored():
    """
    Упоминание тренинга в середине аналитики не делает её обучением.

    Реальный случай: «79% уволившихся назвали причиной ухода...» помечалось
    «Обучением» из-за Яндекс Практикума в теле текста и теряло HR-сигнал.
    """
    text = (
        "79% уволившихся называют причиной ухода недостаток признания. "
        "Исследование показало, что руководители недооценивают влияние обратной связи "
        "на удержание сотрудников и стоимость замены специалиста для компании в целом. "
        "Команда Яндекс Практикума собрала гайд из 30 способов признания заслуг."
    )
    analysis = analyze_text(text)
    assert analysis.material_type != "Обучение"
    # а анонс, где жанр назван в начале, определяется по-прежнему
    assert detect_material_type("Курс «Основы психометрики» бесплатно!") == "Обучение"


def test_source_declares_press_release_type():
    """
    На companies.rbc.ru материал пишет сама компания, а не редакция.

    По тексту это от новости не отличить, поэтому тип задаётся площадкой.
    """
    text = "Сервисная служба FLAMAX провела работы в Ленинградской области"
    assert detect_material_type(text) == "Новость"
    assert detect_material_type(text, "rbc_companies") == "Пресс-релиз"
    # у источника без такого правила поведение не меняется
    assert detect_material_type(text, "comnews") == "Новость"


def test_text_markers_win_over_source_default():
    """Реклама остаётся рекламой даже там, где по умолчанию пресс-релизы."""
    text = "Скидка 30% на курс для HR, промокод HR2026"
    assert detect_material_type(text, "rbc_companies") == "Реклама"


def test_press_release_keeps_hr_signal():
    """Пресс-релиз о назначении — настоящее кадровое событие."""
    analysis = analyze_text("В компании назначен новый генеральный директор", "rbc_companies")
    assert analysis.material_type == "Пресс-релиз"
    assert analysis.signal.level == "высокий"


def test_research_keeps_hr_signal():
    """Исследование про сокращения — полезная кадровая аналитика, не реклама."""
    analysis = analyze_text(
        "Исследование: каждая пятая компания планирует сокращение штата сотрудников"
    )
    assert analysis.material_type == "Исследование"
    assert analysis.signal.level == "высокий"


def test_legislation_split_from_courts():
    """Законодательные инициативы и суды со штрафами — разные темы."""
    assert "Законодательные инициативы" in detect_tags(
        "Госдума приняла законопроект о поправках в Трудовой кодекс"
    )
    assert "Суды и санкции" in detect_tags("ФАС оштрафовала оператора на 500 тысяч")
    # и не путаются между собой
    assert "Суды и санкции" not in detect_tags(
        "Законопроект внесён в Госдуму профильным комитетом"
    )


def test_hr_signal_levels():
    assert hr_signal(["Сокращения"]).level == "высокий"
    assert hr_signal(["Назначения"]).level == "высокий"
    assert hr_signal(["M&A"]).level == "средний"
    assert hr_signal(["Продукты и технологии"]).level == "нет"
    assert hr_signal([]).level == "нет"


def test_hr_signal_takes_strongest_rule():
    """При нескольких тегах побеждает самый сильный сигнал, а не первый."""
    signal = hr_signal(["Финансы", "Сокращения"])
    assert signal.level == "высокий"
    assert "Сокращения" in signal.reason


def test_hr_signal_reason_is_filled_when_signal_exists():
    assert hr_signal(["Найм и рост"]).reason
    assert hr_signal(["Продукты и технологии"]).reason == ""


def test_news_rows_carry_tags_and_signal():
    """Теги и сигнал должны доезжать до строк выгрузки."""
    news = [
        NewsItem(title="Сбер сократит часть персонала", url="https://e.com/1",
                 source="test", summary="Банк объявил о сокращении штата"),
    ]
    row = news_items_to_rows(news)[0]
    assert "Сокращения" in row["tags"]
    assert row["hr_signal"] == "высокий"
    assert row["hr_reason"]


def test_company_news_entries_carry_tags():
    news = [
        NewsItem(title="В Яндексе назначен новый директор", url="https://e.com/1",
                 source="test"),
    ]
    entry = analyze_news_for_companies(news)["Яндекс"][0]
    assert "Назначения" in entry["tags"]
    assert entry["hr_signal"] == "высокий"


# --------------------------------------------------------------------------
# Лид статьи
# --------------------------------------------------------------------------

def test_summary_taken_from_meta_description():
    html = """
    <html><head>
      <meta property="og:description" content="Компания объявила о сокращении штата на 15 процентов в следующем году">
    </head><body><article><p>Короткий текст</p></article></body></html>
    """
    summary = parse_summary_from_html(BeautifulSoup(html, "html.parser"))
    assert summary.startswith("Компания объявила о сокращении штата")


def test_summary_falls_back_to_first_paragraph():
    html = """
    <html><body>
      <header><p>Реклама на сайте, подписка и контакты редакции нашего издания</p></header>
      <article>
        <p>Фото: ТАСС</p>
        <p>Оператор связи объявил о назначении нового генерального директора с первого сентября</p>
      </article>
    </body></html>
    """
    summary = parse_summary_from_html(BeautifulSoup(html, "html.parser"))
    assert summary.startswith("Оператор связи объявил о назначении")


def test_summary_strips_author_prefix():
    """Подпись автора в начале лида — метаданные, а не содержание новости."""
    html = """
    <html><head><meta name="description"
      content="Ассоциация юристов в сфере ликвидации и банкротства: ФНС ужесточила контроль операций компаний и начала проверять первичные документы">
    </head><body></body></html>
    """
    summary = parse_summary_from_html(BeautifulSoup(html, "html.parser"))
    assert summary.startswith("ФНС ужесточила")
    # ...и теги считаются уже по очищенному тексту
    assert "Сокращения" not in detect_tags(summary)


def test_shortening_of_non_people_is_not_a_layoff():
    """Сокращают не только штат: рабочий день, зарплату, издержки."""
    assert "Сокращения" not in detect_tags(
        "Работодатель при жаре обязан сократить рабочий день сотрудников"
    )
    assert "Сокращения" not in detect_tags(
        "Медианная зарплата сотрудников сократилась на 10% за год"
    )
    assert "Сокращения" not in detect_tags("Компания сократила издержки на персонал")
    # реальный пост из HR-канала: между предметом и глаголом целая обстоятельственная группа
    assert "Сокращения" not in detect_tags(
        "Медианная зарплата стоматолога за год сократилась на 10%"
    )
    # а вот это по-прежнему сокращение штата
    assert "Сокращения" in detect_tags("Компания сократит 200 сотрудников")
    assert "Сокращения" in detect_tags("Банк объявил о сокращении штата")
    # причина в виде расходов слева не должна отменять сокращение людей
    assert "Сокращения" in detect_tags(
        "Из-за падения доходов компания сократит штат сотрудников"
    )
    # возвратная форма про людей тоже остаётся сокращением
    assert "Сокращения" in detect_tags("Штат сотрудников сократился вдвое")


def test_ambiguous_marker_context_is_local():
    """Подтверждение маркера ищется рядом, а не в любом месте текста."""
    far = "Компания наняла сотрудников. " + "О другом. " * 20 + "Сократили сроки доставки."
    assert "Сокращения" not in detect_tags(far)
    assert "Сокращения" in detect_tags("Компания сократит штат сотрудников")


def test_summary_none_when_nothing_meaningful():
    html = "<html><body><article><p>Фото: ТАСС</p></article></body></html>"
    assert parse_summary_from_html(BeautifulSoup(html, "html.parser")) is None


def test_article_meta_returns_date_and_summary():
    html = """
    <html><head>
      <meta property="article:published_time" content="2026-08-01T10:00:00+03:00">
      <meta name="description" content="Компания объявила о сокращении штата на 15 процентов в следующем году">
    </head><body><article><p>Текст</p></article></body></html>
    """
    meta = parse_article_meta(html)
    assert meta.published_at == datetime(2026, 8, 1, 10, 0)
    assert meta.summary.startswith("Компания объявила")


# --------------------------------------------------------------------------
# RSS-источники
# --------------------------------------------------------------------------

RSS_SAMPLE = """<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0"><channel>
  <title>Лента</title>
  <item>
    <title>В компании назначен новый генеральный директор</title>
    <link>https://example.com/news/naznachenie</link>
    <pubDate>Fri, 07 Aug 2026 18:30:00 +0300</pubDate>
    <description>&lt;p&gt;Совет директоров компании утвердил нового руководителя на этой неделе&lt;/p&gt;</description>
  </item>
  <item>
    <title>Сборная выиграла матч, назначен пенальти</title>
    <link>https://example.com/news/sport</link>
    <pubDate>Fri, 07 Aug 2026 17:00:00 +0300</pubDate>
    <description>Спортивная новость про чемпионат и тренера сборной команды страны</description>
  </item>
</channel></rss>
"""

ATOM_SAMPLE = """<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <title>Оператор связи сокращает штат сотрудников в регионах</title>
    <link href="https://example.com/news/atom-zapis"/>
    <published>2026-08-07T15:00:00+03:00</published>
    <summary>Компания объявила об оптимизации численности персонала в нескольких филиалах</summary>
  </entry>
</feed>
"""


class _SampleFeedParser(RssParser):
    SOURCE_NAME = "sample"


def _parse_sample(xml_text: str, parser: RssParser | None = None):
    """Разбирает ленту без обращения к сети."""
    import xml.etree.ElementTree as ET

    parser = parser or _SampleFeedParser()
    root = ET.fromstring(xml_text.encode("utf-8"))
    entries = [e for e in root.iter() if e.tag.rsplit("}", 1)[-1] in ("item", "entry")]
    return [parser._entry_to_news_item(e) for e in entries]


def test_rss_item_parsed_with_date_and_summary():
    item = _parse_sample(RSS_SAMPLE)[0]
    assert item.title.startswith("В компании назначен")
    assert item.url == "https://example.com/news/naznachenie"
    assert item.published_at == datetime(2026, 8, 7, 18, 30)
    # HTML-разметка из description убирается
    assert item.summary.startswith("Совет директоров компании")
    assert "<p>" not in item.summary


def test_atom_entry_parsed():
    """У Atom ссылка в атрибуте href, а дата — в ISO-формате."""
    item = _parse_sample(ATOM_SAMPLE)[0]
    assert item.url == "https://example.com/news/atom-zapis"
    assert item.published_at == datetime(2026, 8, 7, 15, 0)
    assert item.summary.startswith("Компания объявила")


def test_rss_feed_date_formats():
    assert parse_feed_date("Fri, 07 Aug 2026 18:30:00 +0300") == datetime(2026, 8, 7, 18, 30)
    assert parse_feed_date("2026-08-07T15:00:00+03:00") == datetime(2026, 8, 7, 15, 0)
    assert parse_feed_date("не дата") is None
    assert parse_feed_date("") is None


def test_topic_filter_keeps_business_drops_sport():
    """Фильтр федеральных лент: кадровое из бизнеса берём, спорт — нет."""
    class _Filtered(_SampleFeedParser):
        TOPIC_FILTER = staticmethod(is_hr_business_news)

    items = [i for i in _parse_sample(RSS_SAMPLE, _Filtered()) if i is not None]
    titles = [i.title for i in items]
    assert any("назначен новый генеральный директор" in t for t in titles)
    assert not any("пенальти" in t for t in titles)


def test_hr_business_filter_rules():
    assert is_hr_business_news("Компания сократит штат сотрудников")
    assert is_hr_business_news("Гендиректором банка назначен Иванов")
    # спорт и военные сводки отсекаются, даже с кадровой лексикой
    assert not is_hr_business_news("Тренер сборной назначен на новый срок")
    assert not is_hr_business_news("Назначение пенальти в матче")
    # кадровая лексика без делового контекста тоже не проходит
    assert not is_hr_business_news("Назначен новый глава сельского поселения")
    assert not is_hr_business_news("")
    # государственные назначения — не корпоративное кадровое движение
    assert not is_hr_business_news("Президент назначил нового министра финансов")


def test_collect_command_registered_with_no_limits():
    """
    У collect лимиты сняты по умолчанию — иначе отчёт молча терял бы новости.
    """
    parser = build_parser()
    args = parser.parse_args(["collect"])

    assert args.days == 7
    assert args.limit >= 100000
    assert args.analysis_limit >= 100000
    assert args.summary_limit >= 100000
    assert args.max_pages >= 20
    assert not args.no_summaries


def test_collect_accepts_period_and_sources():
    parser = build_parser()
    args = parser.parse_args(["collect", "--days", "30", "--source", "rb_hr"])
    assert args.days == 30 and args.source == ["rb_hr"]


def test_every_configured_source_is_in_registry():
    """
    cleanup удаляет новости источников, которых нет в реестре, поэтому реестр
    обязан покрывать весь список PARSERS.
    """
    configured = {name for name, _ in PARSERS}
    assert configured <= set(PARSER_CLASSES), configured - set(PARSER_CLASSES)


def test_registry_parsers_expose_article_check():
    """Каждому классу из реестра нужен is_article_url — им пользуется cleanup."""
    for name, parser in PARSER_CLASSES.items():
        assert hasattr(parser, "is_article_url"), name
        assert parser.is_article_url("https://example.com/news/test-article") in (True, False)


def test_rb_hr_uses_query_pagination():
    """У rb.ru «Читать ещё» рисуется скриптом — листаем через ?page=N."""
    parser = RbHrParser()
    assert parser.PAGE_PARAM == "page"
    assert parser._numeric_next_page("https://rb.ru/tag/hr/") == "https://rb.ru/tag/hr/?page=2"
    assert parser._numeric_next_page("https://rb.ru/tag/hr/?page=7") == "https://rb.ru/tag/hr/?page=8"


def test_rb_article_urls():
    assert RbHrParser.is_article_url("https://rb.ru/news/kadrovye-izmeneniya-nedeli/")
    assert RbHrParser.is_article_url("https://rb.ru/interview/nataliya-runova-t2/")
    assert not RbHrParser.is_article_url("https://rb.ru/tag/hr/")
    assert not RbHrParser.is_article_url("https://rb.ru/about/")


# --------------------------------------------------------------------------
# Telegram-каналы
# --------------------------------------------------------------------------

TELEGRAM_SAMPLE = """
<div class="tgme_widget_message_wrap">
  <div class="tgme_widget_message" data-post="testchannel/12345">
    <div class="tgme_widget_message_text">Сбербанк сократит штат сотрудников в регионах.
      Решение приняли из-за перевода отделений на удалённое обслуживание. @testchannel</div>
    <div class="tgme_widget_message_footer">
      <time datetime="2026-08-07T17:48:55+00:00"></time>
    </div>
  </div>
</div>
<div class="tgme_widget_message_wrap">
  <div class="tgme_widget_message" data-post="testchannel/12346">
    <div class="tgme_widget_message_text">Коротко</div>
  </div>
</div>
<a class="tme_messages_more" href="/s/testchannel?before=12345"></a>
"""


class _SampleTelegramParser(TelegramParser):
    SOURCE_NAME = "tg_sample"
    CHANNELS = ("testchannel",)


def _parse_telegram(html: str, parser: TelegramParser | None = None):
    parser = parser or _SampleTelegramParser()
    soup = BeautifulSoup(html, "html.parser")
    posts = soup.select(".tgme_widget_message_wrap")
    return [parser._post_to_news_item(p, "testchannel") for p in posts]


def test_telegram_post_parsed():
    item = _parse_telegram(TELEGRAM_SAMPLE)[0]
    assert item.url == "https://t.me/testchannel/12345"
    assert item.source == "tg_sample"
    # Заголовок — первая фраза, подпись канала из неё убрана
    assert item.title == "Сбербанк сократит штат сотрудников в регионах."
    # Полный текст остаётся в лиде: по нему считаются теги
    assert "удалённое обслуживание" in item.summary
    assert "@testchannel" not in item.title


def test_telegram_post_date_converted_from_utc():
    item = _parse_telegram(TELEGRAM_SAMPLE)[0]
    # Дата приходит с зоной UTC и приводится к наивной локальной
    assert item.published_at is not None
    assert item.published_at.tzinfo is None


def test_telegram_short_post_skipped():
    """Однословные посты («Коротко», реклама) новостями не считаются."""
    assert _parse_telegram(TELEGRAM_SAMPLE)[1] is None


def test_telegram_topic_filter_applies():
    class _Filtered(_SampleTelegramParser):
        TOPIC_FILTER = staticmethod(is_hr_business_news)

    kept = _parse_telegram(TELEGRAM_SAMPLE, _Filtered())[0]
    assert kept is not None  # про сокращение штата — кадровая новость

    sport = TELEGRAM_SAMPLE.replace(
        "Сбербанк сократит штат сотрудников в регионах.",
        "Тренер сборной назначен на новый срок в клубе.",
    )
    assert _parse_telegram(sport, _Filtered())[0] is None


def test_telegram_next_page_link():
    """Листание назад идёт по ссылке ?before=<номер поста>."""
    parser = _SampleTelegramParser()
    soup = BeautifulSoup(TELEGRAM_SAMPLE, "html.parser")
    next_url = parser._next_page_url(soup, "https://t.me/s/testchannel")
    assert next_url == "https://t.me/s/testchannel?before=12345"


def test_telegram_post_urls_recognized():
    assert TelegramParser.is_article_url("https://t.me/banksta/99217")
    assert not TelegramParser.is_article_url("https://t.me/s/banksta")


def test_end_of_listing_detected_by_status():
    """404 после разобранных страниц — конец раздела, а не сбой."""
    response = requests.Response()
    response.status_code = 404
    error = requests.HTTPError(response=response)
    assert BaseParser._is_end_of_listing(error)

    response.status_code = 500
    assert not BaseParser._is_end_of_listing(error)
    # Обрыв соединения — не конец ленты, а именно ошибка
    assert not BaseParser._is_end_of_listing(requests.ConnectionError())


# --------------------------------------------------------------------------
# Разбор дат
# --------------------------------------------------------------------------

def test_parse_date_numeric():
    assert parse_date_from_text("22.06.2026") == datetime(2026, 6, 22)
    assert parse_date_from_text("01.02.26") == datetime(2026, 2, 1)


def test_parse_date_russian_month():
    assert parse_date_from_text("22 июня 2026") == datetime(2026, 6, 22)
    assert parse_date_from_text("5 авг 2025") == datetime(2025, 8, 5)


def test_parse_date_invalid_returns_none():
    assert parse_date_from_text("") is None
    assert parse_date_from_text("без даты") is None
    assert parse_date_from_text("32.13.2026") is None


def test_tz_aware_dates_normalized():
    """Даты со смещением должны становиться наивными: иначе сравнение с
    cutoff падает с 'can't compare offset-naive and offset-aware datetimes'."""
    parsed = _parse_iso_datetime("2026-07-29T15:59:35+03:00")
    assert parsed is not None and parsed.tzinfo is None
    # сравнение с наивной датой не должно бросать исключение
    assert isinstance(parsed > datetime(2020, 1, 1), bool)


def test_to_naive_local_passthrough():
    naive = datetime(2026, 8, 1, 12, 0)
    assert to_naive_local(naive) is naive
    assert to_naive_local(None) is None


def test_html_with_tz_date_parsed_naive():
    html = '<html><body><time datetime="2026-07-29T15:59:35+03:00">29 июля</time></body></html>'
    parsed = parse_date_from_html(html)
    assert parsed is not None and parsed.tzinfo is None


def test_parse_date_from_url():
    assert parse_date_from_url("https://ria.ru/20260715/putin.html") == datetime(2026, 7, 15)
    assert parse_date_from_url("https://x.ru/2026/07/15/news") == datetime(2026, 7, 15)
    assert parse_date_from_url("https://x.ru/news/no-date") is None


def test_future_dates_rejected():
    """Дата из будущего — это мусор с вёрстки, а не дата публикации."""
    future = datetime.now() + timedelta(days=30)
    assert not is_plausible_publication_date(future)
    assert not is_plausible_publication_date(datetime(1998, 1, 1))
    assert is_plausible_publication_date(datetime.now() - timedelta(days=1))
    assert parse_date_from_url(f"https://x.ru/{future:%Y/%m/%d}/news") is None


def test_site_clock_in_header_not_used_as_publication_date():
    """
    Регресс: в шапке сайта висят часы с текущей датой, и разбор текста всей
    страницы записывал дату сбора в published_at для любой старой новости.
    """
    today = datetime.now().strftime("%d.%m.%Y")
    html = f"""
    <html><body>
      <header><div class="site-clock">{today}, Пт</div></header>
      <main><div class="article__body"><h1>Новость</h1>
        <p>Текст без даты внутри.</p>
      </div></main>
      <footer>Подвал {today}</footer>
    </body></html>
    """
    assert parse_date_from_html(html) is None


def test_publication_date_taken_from_article_body():
    html = """
    <html><body>
      <header><div class="site-clock">07.08.2026, Пт</div></header>
      <main><div class="article__body">
        <div class="article__date">30.07.2026</div>
        <p>Текст новости.</p>
      </div></main>
    </body></html>
    """
    assert parse_date_from_html(html) == datetime(2026, 7, 30)


def test_relative_dates():
    today = datetime.now().date()
    assert parse_relative_date("Сегодня").date() == today
    assert parse_relative_date("вчера").date() == today - timedelta(days=1)
    assert parse_relative_date("2 часа назад").date() == today
    # Длинный текст со словом «сегодня» относительной датой не является
    assert parse_relative_date("Какие инвесторы приходят сегодня в банный бизнес") is None


def test_russian_month_without_year_not_in_future():
    """«5 декабря» в августе — это прошлый год, а не будущая дата."""
    parsed = parse_date_from_text("5 декабря")
    assert parsed is not None
    assert is_plausible_publication_date(parsed)


# --------------------------------------------------------------------------
# Фильтры URL парсеров
# --------------------------------------------------------------------------

def test_article_url_patterns():
    cases = [
        (comnews.ComnewsParser(), "https://www.comnews.ru/content/245924/2026-06-22/x/y", True),
        (comnews.ComnewsParser(), "https://www.comnews.ru/digital-economy/content/245934/a/b", True),
        (comnews.ComnewsParser(), "https://www.comnews.ru/telecom_tv", False),
        (rbc_companies.RbcCompaniesParser(), "https://companies.rbc.ru/news/3Cpzn/utinet-provedet", True),
        (rbc_companies.RbcCompaniesParser(), "https://companies.rbc.ru/news/?category_filter=it", False),
        (adindex.AdindexParser(), "https://adindex.ru/news/hr/2026/08/1/1.phtml", True),
        (adindex.AdindexParser(), "https://adindex.ru/ratings/156391/2020/156394/", False),
        (ria_companies.RiaCompaniesParser(), "https://ria.ru/20260715/putin-2104981570.html", True),
        (ria_companies.RiaCompaniesParser(), "https://ria.ru/company/", False),
        (forbes_companies.ForbesCompaniesParser(), "https://www.forbes.ru/novosti-kompaniy/562965-alfa", True),
        (forbes_companies.ForbesCompaniesParser(), "https://www.forbes.ru/novosti-kompaniy/", False),
    ]
    for parser, url, expected in cases:
        assert parser._is_article_url(url) is expected, url


def test_url_normalization_strips_fragment():
    parser = comnews.ComnewsParser()
    assert parser._normalize_url("https://e.com/a#comments") == "https://e.com/a"


# --------------------------------------------------------------------------
# Полнота разбора листингов
# --------------------------------------------------------------------------

def _link(html: str):
    return BeautifulSoup(html, "html.parser").find("a")


def test_title_taken_from_wrapper_link():
    """
    Регресс: в листингах РИА и РБК часть новостей представлена только ссылкой
    вокруг картинки. Раньше такие ссылки отбрасывались, и новости терялись.
    """
    parser = rbc_companies.RbcCompaniesParser()

    assert parser._extract_title(_link('<a href="/x">Заголовок новости целиком</a>')) \
        == "Заголовок новости целиком"
    assert parser._extract_title(_link('<a href="/x" title="Заголовок из атрибута"></a>')) \
        == "Заголовок из атрибута"
    assert parser._extract_title(_link('<a href="/x"><img alt="Заголовок из картинки"></a>')) \
        == "Заголовок из картинки"

    block = BeautifulSoup(
        '<div><h3>Заголовок из блока</h3><a href="/x"><img></a></div>', "html.parser"
    )
    assert parser._extract_title(block.find("a")) == "Заголовок из блока"


def test_numeric_pagination_advances():
    """У РБК ссылок «далее» в разметке нет — страницы перебираются параметром."""
    parser = rbc_companies.RbcCompaniesParser()
    empty = BeautifulSoup("<html><body></body></html>", "html.parser")

    first = parser._find_next_page(empty, "https://companies.rbc.ru/news/")
    assert first == "https://companies.rbc.ru/news/?page=2"
    assert parser._find_next_page(empty, first) == "https://companies.rbc.ru/news/?page=3"


def test_source_without_page_param_has_no_numeric_pagination():
    """Остальным источникам параметр страницы не подставляется вслепую."""
    parser = comnews.ComnewsParser()
    empty = BeautifulSoup("<html><body></body></html>", "html.parser")
    assert parser._find_next_page(empty, parser.NEWS_URL) is None


def test_ria_next_chunk_from_markup():
    parser = ria_companies.RiaCompaniesParser()

    page = BeautifulSoup(
        '<div class="list-more" data-url="/services/company/more.html?id=1&date=2"></div>',
        "html.parser",
    )
    assert parser._find_next_page(page, parser.NEWS_URL) == \
        "https://ria.ru/services/company/more.html?id=1&date=2"

    chunk = BeautifulSoup(
        '<div class="list-items-loaded" data-next-url="/services/company/more.html?id=9"></div>',
        "html.parser",
    )
    assert parser._find_next_page(chunk, parser.NEWS_URL) == \
        "https://ria.ru/services/company/more.html?id=9"


def test_adindex_json_chunk_becomes_html():
    """Догрузка adindex отдаёт JSON — он разворачивается в разметку с датами."""
    parser = adindex.AdindexParser()
    rendered = parser._render_items([
        {
            "date": "2026.07.15 19:00:43",
            "last_at": "1784131243",
            "url": "/news/hr/2026/07/15/347231.phtml",
            "title": "Алла Миронова покинула бренд",
        }
    ])

    soup = BeautifulSoup(rendered, "html.parser")
    link = soup.find("a")
    assert link["href"] == "/news/hr/2026/07/15/347231.phtml"
    assert link.get_text(strip=True) == "Алла Миронова покинула бренд"
    assert soup.find("time")["datetime"].startswith("2026-07-15T19:00:43")
    assert parser._find_next_page(soup, parser.NEWS_URL).endswith("last_at=1784131243")


# --------------------------------------------------------------------------
# Запуск без pytest
# --------------------------------------------------------------------------

def _run_all() -> int:
    tests = [
        (name, obj) for name, obj in sorted(globals().items())
        if name.startswith("test_") and callable(obj)
    ]
    failed = 0
    for name, func in tests:
        try:
            func()
            print(f"  OK   {name}")
        except AssertionError as exc:
            failed += 1
            print(f"  FAIL {name}: {exc}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"  ERR  {name}: {type(exc).__name__}: {exc}")

    print(f"\nВсего: {len(tests)}, провалено: {failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    import sys
    sys.exit(_run_all())
