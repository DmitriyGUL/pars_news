#!/usr/bin/env python3
"""
Интерфейс командной строки для проекта парсинга новостей.

Это единственная точка входа проекта: `py cli.py <команда>`.
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from company_analyzer import (
    find_news_by_company_name,
    get_all_companies_from_db,
    get_news_and_companies_from_db,
    get_news_with_companies_from_db,
    seed_reference_companies,
)
from main import run_all_parsers
from storage import export_to_csv, get_connection, get_latest, get_statistics, init_db


logger = logging.getLogger(__name__)


LOGS_DIR = Path(__file__).with_name("logs")


def setup_logging(verbose: bool = False) -> Path:
    """
    Настройка логирования: в консоль и в файл.

    Файл нужен потому, что прогон длинный: к моменту, когда что-то упало,
    вывод в терминале успевает прокрутиться или потеряться вместе с окном.
    В файл всегда пишется DEBUG со всеми трейсбеками, независимо от --verbose.
    """
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOGS_DIR / f"run_{datetime.now():%Y%m%d_%H%M%S}.log"

    console = logging.StreamHandler()
    console.setLevel(logging.DEBUG if verbose else logging.INFO)

    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)

    logging.basicConfig(
        level=logging.DEBUG,
        format='[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        handlers=[console, file_handler],
    )
    # Болтовня http-библиотек на DEBUG забивает файл и прячет наши сообщения.
    for noisy in ("urllib3", "requests", "chardet", "charset_normalizer"):
        logging.getLogger(noisy).setLevel(logging.INFO)

    return log_path


# --------------------------------------------------------------------------
# Общие помощники вывода
# --------------------------------------------------------------------------

def print_analysis_summary(company_news: Dict[str, List[Dict]]) -> None:
    """Печатает сводку по результатам анализа."""
    total_news = sum(len(news_list) for news_list in company_news.values())

    print("\nРезультаты анализа:")
    print(f"- Обнаружено компаний: {len(company_news)}")
    print(f"- Найдено новостей с упоминаниями: {total_news}")


def print_top_companies(company_news: Dict[str, List[Dict]], top: int) -> None:
    """Печатает топ компаний по числу новостей."""
    if not company_news or top <= 0:
        return

    company_stats = [
        (name, len(news_list), sum(news.get('mention_count', 0) for news in news_list))
        for name, news_list in company_news.items()
    ]
    company_stats.sort(key=lambda item: (item[1], item[2]), reverse=True)

    print(f"\nТоп-{top} компаний по количеству упоминаний:")
    for i, (company, news_count, mentions) in enumerate(company_stats[:top], 1):
        print(f"{i}. {company}: {news_count} новостей, {mentions} упоминаний")


def print_latest_news(limit: int) -> None:
    """Печатает последние новости из БД."""
    if limit <= 0:
        return

    print(f"\nПоследние {limit} новостей:")
    for item in get_latest(limit=limit):
        date_str = item.published_at.isoformat() if item.published_at else "без даты"
        print(f"- [{item.source}] {date_str} — {item.title[:80]}")


def export_excel_safe(limit_news: int, start_date=None, end_date=None) -> str | None:
    """
    Экспорт в Excel с понятным сообщением, если не установлен openpyxl.

    Модуль export_excel импортируется здесь, а не на уровне файла: он падает с
    ImportError без openpyxl, и при импорте наверху из-за этого переставали
    работать вообще все команды CLI, включая parse и stats.
    """
    try:
        from export_excel import export_analysis_to_excel

        excel_path = export_analysis_to_excel(
            limit_news=limit_news, start_date=start_date, end_date=end_date
        )
    except ImportError as exc:
        logger.error("Ошибка при экспорте в Excel: %s", exc)
        logger.error("Установите openpyxl: pip install openpyxl")
        return None

    logger.info("Экспорт в Excel выполнен: %s", excel_path)
    print(f"\nExcel файл создан: {excel_path}")
    return excel_path


def run_parsers_and_save(args: argparse.Namespace) -> None:
    """Запуск парсеров с сохранением в БД."""
    from storage import save_news

    logger.info("Запуск парсеров новостей...")
    items = run_all_parsers(
        days=args.days,
        limit_per_source=args.limit,
        with_summaries=not args.no_summaries,
        max_pages=args.max_pages,
        only_sources=args.source or None,
    )
    inserted = save_news(items)
    logger.info("Собрано %d записей, в БД добавлено %d новых", len(items), inserted)


# --------------------------------------------------------------------------
# Команды
# --------------------------------------------------------------------------

def cmd_parse(args: argparse.Namespace) -> None:
    """Команда парсинга новостей."""
    run_parsers_and_save(args)

    if args.export_csv:
        csv_path = export_to_csv()
        logger.info("Экспорт в CSV выполнен: %s", csv_path)

    print_latest_news(args.show_latest)


def cmd_analyze(args: argparse.Namespace) -> None:
    """Команда анализа новостей на предмет упоминаний компаний."""
    logger.info("Анализ новостей на предмет упоминаний компаний...")

    company_news = get_news_with_companies_from_db(limit=args.limit)
    print_analysis_summary(company_news)
    print_top_companies(company_news, args.top)

    if args.export_excel:
        export_excel_safe(args.limit)


def cmd_stats(args: argparse.Namespace) -> None:
    """Команда получения статистики."""
    stats = get_statistics()

    print("\n=== Статистика базы данных ===")
    print("\nНовости:")
    print(f"  Всего записей: {stats['news']['total']}")
    print(f"  Источников: {stats['news']['sources']}")
    if stats['news']['date_range']['min'] and stats['news']['date_range']['max']:
        print(f"  Период: {stats['news']['date_range']['min']} - {stats['news']['date_range']['max']}")

    print("\nКомпании:")
    print(f"  Всего записей: {stats['companies']['total']}")
    print(f"  Источников: {stats['companies']['sources']}")
    print(f"  С рейтингом: {stats['companies']['with_rank']}")

    with get_connection() as conn:
        cursor = conn.execute(
            "SELECT source, COUNT(*) FROM news GROUP BY source ORDER BY COUNT(*) DESC"
        )
        sources = cursor.fetchall()

        if sources:
            print("\nРаспределение новостей по источникам:")
            for source, count in sources[:10]:
                print(f"  {source}: {count}")

        cursor = conn.execute(
            "SELECT source, COUNT(*) FROM companies GROUP BY source ORDER BY COUNT(*) DESC"
        )
        company_sources = cursor.fetchall()

        if company_sources:
            print("\nРаспределение компаний по источникам:")
            for source, count in company_sources:
                print(f"  {source}: {count}")

    print_latest_news(args.show_latest)


def cmd_export(args: argparse.Namespace) -> None:
    """Команда экспорта данных."""
    if bool(args.date_from) != bool(args.date_to):
        # Одна граница периода без второй молча игнорировалась бы — лучше сказать сразу.
        raise ValueError("Период задаётся обеими границами: укажите и --from, и --to")

    if args.format in ("excel", "both"):
        export_excel_safe(args.limit)

    if args.format in ("csv", "both"):
        csv_path = export_to_csv(
            limit=args.limit, start_date=args.date_from, end_date=args.date_to
        )
        logger.info("Экспорт в CSV выполнен: %s", csv_path)
        print(f"CSV файл создан: {csv_path}")


def cmd_search(args: argparse.Namespace) -> None:
    """Команда поиска новостей по компании."""
    logger.info("Поиск новостей по компании: %s", args.company)

    news_list = find_news_by_company_name(
        args.company, limit=args.limit, scan_limit=args.scan_limit
    )

    if not news_list:
        print(f"Не найдено новостей для компании '{args.company}'")
        return

    print(f"\nНайдено {len(news_list)} новостей для '{args.company}':")
    for i, news in enumerate(news_list, 1):
        print(f"\n{i}. {news['title']}")
        print(f"   Источник: {news['source']}")
        if news.get('published_at'):
            print(f"   Дата: {news['published_at']}")
        print(f"   Ссылка: {news['url']}")
        if news.get('text_snippet'):
            print(f"   Сниппет: {news['text_snippet']}")


def cmd_parse_and_export(args: argparse.Namespace) -> None:
    """Команда парсинга новостей с автоматическим экспортом в Excel."""
    run_parsers_and_save(args)

    logger.info("Анализ новостей на предмет упоминаний компаний...")
    company_news = get_news_with_companies_from_db(limit=args.analysis_limit)

    print_analysis_summary(company_news)
    export_excel_safe(args.analysis_limit)
    print_top_companies(company_news, args.show_top)


def cmd_collect(args: argparse.Namespace) -> None:
    """
    Полный цикл за один запуск: сбор → лиды → анализ → Excel.

    Отличается от parse-and-export тремя вещами, из-за которых тот не годился
    как еженедельный отчёт:

    * лимиты сняты — берётся всё, что источники отдают за период;
    * лиды догружаются отдельным шагом, поэтому сбор ссылок не ждёт обхода
      каждой статьи, а прерванный прогон продолжается с того же места;
    * в Excel попадают новости именно за период, а не последние N записей
      вперемешку со старыми.
    """
    from datetime import timedelta

    from tagging import NON_EVENT_TYPES

    started = datetime.now()
    period_end = started.date()
    period_start = period_end - timedelta(days=args.days - 1)

    print(f"\n=== Сбор новостей за {args.days} дн. "
          f"({period_start:%d.%m.%Y} — {period_end:%d.%m.%Y}) ===")

    # Шаг 1. Сбор ссылок без догрузки статей: так обход листингов не ждёт
    # каждую статью, а лиды доберёт следующий шаг.
    print("\n[1/4] Сбор новостей из всех источников...")
    run_parsers_and_save(argparse.Namespace(
        days=args.days,
        limit=args.limit,
        no_summaries=True,
        max_pages=args.max_pages,
        source=args.source,
    ))

    # Шаг 2. Лиды. Отдельным шагом, потому что этот этап самый долгий и
    # заодно дозаполняет записи, собранные прошлыми прогонами.
    if args.no_summaries:
        print("\n[2/4] Догрузка описаний пропущена (--no-summaries)")
    else:
        print("\n[2/4] Догрузка описаний статей...")
        # Только период отчёта: дозаполнять весь архив еженедельному прогону
        # незачем, для этого есть отдельная команда backfill-summaries.
        backfill_args = argparse.Namespace(
            limit=args.summary_limit, workers=args.workers,
            refresh=False, since=period_start,
        )
        cmd_backfill_summaries(backfill_args)

    # Шаг 3. Анализ за период
    print("\n[3/4] Анализ упоминаний компаний и разметка материалов...")
    rows, company_news = get_news_and_companies_from_db(
        limit=args.analysis_limit, start_date=period_start, end_date=period_end
    )

    print(f"\nЗа период найдено материалов: {len(rows)}")
    print_analysis_summary(company_news)

    by_type: Dict[str, int] = {}
    signals: Dict[str, int] = {}
    for row in rows:
        by_type[row['material_type']] = by_type.get(row['material_type'], 0) + 1
        signals[row['hr_signal']] = signals.get(row['hr_signal'], 0) + 1

    print("\nТипы материалов:")
    for material_type, count in sorted(by_type.items(), key=lambda i: i[1], reverse=True):
        mark = "  (не кадровое событие)" if material_type in NON_EVENT_TYPES else ""
        print(f"  {material_type}: {count}{mark}")

    print("\nВлияние на кадровые движения:")
    for level in ("высокий", "средний", "нет"):
        print(f"  {level}: {signals.get(level, 0)}")

    print_top_companies(company_news, args.show_top)

    # Шаг 4. Excel за тот же период
    print("\n[4/4] Формирование Excel...")
    excel_path = export_excel_safe(
        args.analysis_limit, start_date=period_start, end_date=period_end
    )

    elapsed = (datetime.now() - started).total_seconds()
    print(f"\n=== Готово за {elapsed / 60:.1f} мин ===")
    if excel_path:
        print(f"Отчёт: {excel_path}")


def cmd_seed_companies(args: argparse.Namespace) -> None:
    """Заполняет таблицу companies справочным списком отслеживаемых компаний."""
    inserted = seed_reference_companies()
    total = len(get_all_companies_from_db())
    logger.info("Добавлено компаний: %d (всего в БД: %d)", inserted, total)
    print(f"\nДобавлено компаний: {inserted}. Всего в базе: {total}")


def cmd_refresh_dates(args: argparse.Namespace) -> None:
    """
    Пересчитывает даты публикации у уже сохранённых новостей.

    Нужна разово после исправления разбора дат: записи, собранные раньше, могли
    получить дату сбора вместо реальной даты публикации (дата бралась из часов
    в шапке сайта). Дата определяется заново — из URL, а затем со страницы.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    from sources.base_parser import DEFAULT_USER_AGENT
    from sources.date_utils import fetch_article_date, parse_date_from_url
    from storage import get_news_rows_for_date_refresh, update_published_at

    rows = get_news_rows_for_date_refresh(
        only_suspicious=not args.all, limit=args.limit
    )
    logger.info("К пересчёту дат: %d записей", len(rows))
    if not rows:
        print("Нечего пересчитывать.")
        return

    headers = {"User-Agent": DEFAULT_USER_AGENT}
    changed = 0
    cleared = 0

    def resolve(url: str):
        return parse_date_from_url(url) or fetch_article_date(url, headers)

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(resolve, url): (url, old) for url, old in rows}
        for future in as_completed(futures):
            url, old = futures[future]
            try:
                new = future.result()
            except Exception as exc:  # noqa: BLE001 — сбой одной статьи не роняет прогон
                logger.debug("%s: %s", url, exc)
                continue

            new_str = new.isoformat() if new else None
            if new_str == old:
                continue

            update_published_at(url, new)
            changed += 1
            if new is None:
                cleared += 1

    logger.info("Обновлено дат: %d (из них очищено: %d)", changed, cleared)
    print(f"\nПересчитано записей: {len(rows)}. Обновлено дат: {changed}, очищено: {cleared}")


def cmd_backfill_summaries(args: argparse.Namespace) -> None:
    """
    Догружает лид статьи для новостей, у которых его нет.

    Нужна разово: новости, собранные до появления тегов, лежат в БД с одним
    заголовком, а по 80 символам заголовка тема определяется плохо.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    from sources.base_parser import DEFAULT_USER_AGENT
    from sources.date_utils import fetch_article_meta
    from storage import get_news_urls_for_summary, update_summary

    urls = get_news_urls_for_summary(
        limit=args.limit,
        only_missing=not args.refresh,
        since=getattr(args, "since", None),
    )
    logger.info("Новостей к обработке: %d", len(urls))
    if not urls:
        print("У всех новостей уже есть описание.")
        return

    headers = {"User-Agent": DEFAULT_USER_AGENT}
    filled = 0

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(fetch_article_meta, url, headers): url for url in urls}
        for done, future in enumerate(as_completed(futures), 1):
            # Команда работает десятки минут: без прогресса это неотличимо
            # от зависшего процесса.
            if done % 25 == 0 or done == len(urls):
                logger.info("  обработано %d из %d, заполнено %d", done, len(urls), filled)

            url = futures[future]
            try:
                meta = future.result()
            except Exception as exc:  # noqa: BLE001 — сбой одной статьи не роняет прогон
                logger.debug("%s: %s", url, exc)
                continue

            if meta.summary:
                update_summary(url, meta.summary)
                filled += 1

    logger.info("Заполнено описаний: %d из %d", filled, len(urls))
    print(f"\nОбработано новостей: {len(urls)}. Заполнено описаний: {filled}")


def cmd_tags(args: argparse.Namespace) -> None:
    """Сводка по тегам и влиянию новостей на кадровые движения."""
    from company_analyzer import get_news_and_companies_from_db
    from tagging import HR_LEVELS, NON_EVENT_TYPES

    rows, _ = get_news_and_companies_from_db(limit=args.limit)

    if args.type:
        rows = [row for row in rows if row['material_type'] == args.type]
    if args.exclude_promo:
        rows = [row for row in rows if row['material_type'] not in NON_EVENT_TYPES]

    by_tag: Dict[str, int] = {}
    by_type: Dict[str, int] = {}
    by_level = {level: 0 for level in HR_LEVELS}
    for row in rows:
        by_level[row['hr_signal']] = by_level.get(row['hr_signal'], 0) + 1
        by_type[row['material_type']] = by_type.get(row['material_type'], 0) + 1
        for tag in filter(None, (t.strip() for t in row['tags'].split(","))):
            by_tag[tag] = by_tag.get(tag, 0) + 1

    print(f"\nПроанализировано материалов: {len(rows)}")

    print("\nТип материала:")
    for material_type, count in sorted(by_type.items(), key=lambda item: item[1], reverse=True):
        mark = "  (не кадровое событие)" if material_type in NON_EVENT_TYPES else ""
        print(f"  {material_type}: {count}{mark}")

    print("\nВлияние на кадровые движения:")
    for level in HR_LEVELS:
        print(f"  {level}: {by_level.get(level, 0)}")

    print("\nТемы:")
    if not by_tag:
        print("  (ничего не распознано)")
    for tag, count in sorted(by_tag.items(), key=lambda item: item[1], reverse=True):
        print(f"  {tag}: {count}")

    if args.show_signal:
        selected = [row for row in rows if row['hr_signal'] == args.show_signal]
        print(f"\nМатериалы с сигналом «{args.show_signal}» ({len(selected)}), первые {args.show}:")
        for row in selected[:args.show]:
            date_str = (row['published_at'] or "без даты")[:10]
            print(f"\n- [{row['source']}] {date_str} — {row['title'][:90]}")
            print(f"  Тип: {row['material_type']} | Темы: {row['tags'] or '—'}")
            print(f"  Почему: {row['hr_reason'] or '—'}")
            if row['companies']:
                print(f"  Компании: {row['companies']}")


def cmd_cleanup(args: argparse.Namespace) -> None:
    """
    Удаляет из БД записи, которые новостями не являются.

    Убираются два вида мусора:

    1. Разделы сайтов и страницы рейтингов («Связь и ТВ», «Рейтинг операторов
       Indoor-инвентаря») — ранние прогоны складывали их в таблицу, потому что
       проверки URL тогда не было. Записи проверяются тем же правилом, что и
       при парсинге.
    2. Записи от источников, которых в проекте нет, — например тестовые новости
       с example.com, оставшиеся от прежнего демо-скрипта.
    """
    from main import PARSER_CLASSES
    from storage import delete_news_by_urls, get_all_news_urls

    # Реестр из main.py, а не свой список: иначе новый источник считался бы
    # неизвестным, и cleanup удалил бы все его новости.
    parsers = PARSER_CLASSES

    junk = []
    for url, source, title in get_all_news_urls():
        parser = parsers.get(source)
        if parser is None or not parser.is_article_url(url):
            junk.append((url, source, title))

    if not junk:
        print("Записей, не являющихся новостями, не найдено.")
        return

    print(f"\nНайдено записей на удаление: {len(junk)}")
    for url, source, title in junk[:15]:
        print(f"  [{source}] {title[:55]} -> {url[:80]}")
    if len(junk) > 15:
        print(f"  ... и ещё {len(junk) - 15}")

    if args.dry_run:
        print("\nРежим проверки (--dry-run): ничего не удалено.")
        return

    deleted = delete_news_by_urls(url for url, _, _ in junk)
    logger.info("Удалено записей: %d", deleted)
    print(f"\nУдалено записей: {deleted}")


def cmd_sources(args: argparse.Namespace) -> None:
    """Показывает подключённые источники и сколько новостей от каждого в БД."""
    from main import PARSER_CLASSES, PARSERS

    with get_connection() as conn:
        cursor = conn.execute("SELECT source, COUNT(*) FROM news GROUP BY source")
        counts = dict(cursor.fetchall())

    print(f"\nПодключено источников: {len(PARSERS)}")
    for name, _ in PARSERS:
        parser = PARSER_CLASSES[name]

        channels = getattr(parser, "CHANNELS", ())
        feeds = getattr(parser, "FEED_URLS", ())
        if channels or hasattr(parser, "CHANNELS"):
            kind = "telegram"
            where = ", ".join(f"@{c}" for c in channels) or "каналы не заданы"
        elif feeds:
            kind = "лента"
            where = ", ".join(feeds)
        else:
            kind = "листинг"
            where = getattr(parser, "NEWS_URL", "")

        filtered = " [фильтр по кадрам]" if getattr(parser, "TOPIC_FILTER", None) else ""
        print(f"  {name:18s} {counts.get(name, 0):5d} записей  {kind}{filtered}")
        print(f"  {'':18s}       {where[:88]}")

    unknown = set(counts) - set(PARSER_CLASSES)
    if unknown:
        print("\nВ базе есть записи от источников, которых нет в конфигурации:")
        for name in sorted(unknown):
            print(f"  {name}: {counts[name]} записей")
        print("Команда cleanup сочтёт их мусором — проверьте, прежде чем запускать её.")


def cmd_init(args: argparse.Namespace) -> None:
    """Команда инициализации базы данных."""
    logger.info("Инициализация базы данных...")
    init_db()
    logger.info("База данных инициализирована")


# --------------------------------------------------------------------------
# Разбор аргументов
# --------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    """Собирает парсер аргументов командной строки."""
    parser = argparse.ArgumentParser(
        description="Парсер новостей с анализом упоминаний компаний",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры использования:
  %(prog)s collect                        # всё за 7 дней + анализ + Excel
  %(prog)s collect --days 30
  %(prog)s parse --days 7 --limit 100
  %(prog)s analyze --export-excel --top 20
  %(prog)s stats --show-latest 10
  %(prog)s export --format both --limit 500
  %(prog)s export --format csv --from 2026-08-01 --to 2026-08-08
  %(prog)s search --company "Газпром"
  %(prog)s parse-and-export --days 7 --limit 200 --show-top 15
  %(prog)s seed-companies
  %(prog)s refresh-dates
  %(prog)s backfill-summaries
  %(prog)s tags --show-signal высокий
        """
    )

    parser.add_argument("--verbose", "-v", action="store_true", help="Подробный вывод")

    subparsers = parser.add_subparsers(title="команды", dest="command", required=True)

    # parse
    parse_parser = subparsers.add_parser("parse", help="Парсинг новостей из всех источников")
    parse_parser.add_argument("--days", "-d", type=int, default=7,
                              help="Количество дней для парсинга (по умолчанию: 7)")
    parse_parser.add_argument("--limit", "-l", type=int, default=200,
                              help="Лимит новостей на источник (по умолчанию: 200)")
    parse_parser.add_argument("--show-latest", type=int, default=10,
                              help="Сколько последних новостей показать (по умолчанию: 10)")
    parse_parser.add_argument("--export-csv", action="store_true",
                              help="Экспортировать результаты в CSV")
    parse_parser.add_argument("--no-summaries", action="store_true",
                              help="Не догружать описания статей (быстрее, но теги хуже)")
    parse_parser.add_argument("--max-pages", type=int, default=None,
                              help="Глубина обхода листингов в страницах (по умолчанию: 20)")
    parse_parser.add_argument("--source", action="append", metavar="ИМЯ",
                              help="Собрать только указанный источник (можно повторять)")
    parse_parser.set_defaults(func=cmd_parse)

    # analyze
    analyze_parser = subparsers.add_parser("analyze", help="Анализ упоминаний компаний в новостях")
    analyze_parser.add_argument("--limit", type=int, default=1000,
                                help="Лимит новостей для анализа (по умолчанию: 1000)")
    analyze_parser.add_argument("--top", "--show-top", dest="top", type=int, default=10,
                                help="Количество топ компаний для вывода (по умолчанию: 10)")
    analyze_parser.add_argument("--export-excel", action="store_true",
                                help="Экспортировать результаты в Excel")
    analyze_parser.set_defaults(func=cmd_analyze)

    # stats
    stats_parser = subparsers.add_parser("stats", help="Статистика по базе данных")
    stats_parser.add_argument("--show-latest", type=int, default=0,
                              help="Сколько последних новостей показать (по умолчанию: 0)")
    stats_parser.set_defaults(func=cmd_stats)

    # export
    export_parser = subparsers.add_parser("export", help="Экспорт данных")
    export_parser.add_argument("--format", choices=["excel", "csv", "both"], default="excel",
                               help="Формат экспорта (по умолчанию: excel)")
    export_parser.add_argument("--limit", type=int, default=1000,
                               help="Лимит новостей для экспорта (по умолчанию: 1000)")
    export_parser.add_argument("--from", dest="date_from", metavar="ГГГГ-ММ-ДД",
                               help="Начало периода для выгрузки в CSV (включительно)")
    export_parser.add_argument("--to", dest="date_to", metavar="ГГГГ-ММ-ДД",
                               help="Конец периода для выгрузки в CSV (включительно)")
    export_parser.set_defaults(func=cmd_export)

    # search
    search_parser = subparsers.add_parser("search", help="Поиск новостей по компании")
    search_parser.add_argument("--company", "-c", required=True,
                               help="Название компании для поиска")
    search_parser.add_argument("--limit", "-l", type=int, default=50,
                               help="Лимит результатов (по умолчанию: 50)")
    search_parser.add_argument("--scan-limit", type=int, default=10000,
                               help="Сколько последних новостей просматривать (по умолчанию: 10000)")
    search_parser.set_defaults(func=cmd_search)

    # parse-and-export
    parse_export_parser = subparsers.add_parser(
        "parse-and-export", help="Парсинг новостей с автоматическим экспортом в Excel"
    )
    parse_export_parser.add_argument("--days", "-d", type=int, default=7,
                                     help="Количество дней для парсинга (по умолчанию: 7)")
    parse_export_parser.add_argument("--limit", "-l", type=int, default=200,
                                     help="Лимит новостей на источник (по умолчанию: 200)")
    parse_export_parser.add_argument("--analysis-limit", type=int, default=1000,
                                     help="Лимит новостей для анализа компаний (по умолчанию: 1000)")
    parse_export_parser.add_argument("--show-top", type=int, default=10,
                                     help="Количество топ компаний для вывода (по умолчанию: 10)")
    parse_export_parser.add_argument("--no-summaries", action="store_true",
                                     help="Не догружать описания статей (быстрее, но теги хуже)")
    parse_export_parser.add_argument("--max-pages", type=int, default=None,
                                     help="Глубина обхода листингов в страницах (по умолчанию: 20)")
    parse_export_parser.add_argument("--source", action="append", metavar="ИМЯ",
                                     help="Собрать только указанный источник (можно повторять)")
    parse_export_parser.set_defaults(func=cmd_parse_and_export)

    # collect — основной сценарий: всё за период одной командой
    collect_parser = subparsers.add_parser(
        "collect",
        help="Полный цикл: собрать всё за период, проанализировать и сделать Excel",
    )
    collect_parser.add_argument("--days", "-d", type=int, default=7,
                                help="Период в днях (по умолчанию: 7)")
    collect_parser.add_argument("--limit", "-l", type=int, default=100000,
                                help="Лимит новостей на источник (по умолчанию: без лимита)")
    collect_parser.add_argument("--max-pages", type=int, default=40,
                                help="Глубина обхода листингов в страницах (по умолчанию: 40)")
    collect_parser.add_argument("--analysis-limit", type=int, default=100000,
                                help="Лимит материалов в отчёте (по умолчанию: без лимита)")
    collect_parser.add_argument("--summary-limit", type=int, default=100000,
                                help="Максимум описаний за прогон (по умолчанию: без лимита)")
    collect_parser.add_argument("--workers", type=int, default=4,
                                help="Число параллельных запросов при догрузке (по умолчанию: 4)")
    collect_parser.add_argument("--show-top", type=int, default=15,
                                help="Сколько компаний показать в сводке (по умолчанию: 15)")
    collect_parser.add_argument("--no-summaries", action="store_true",
                                help="Пропустить догрузку описаний (быстрее, но теги хуже)")
    collect_parser.add_argument("--source", action="append", metavar="ИМЯ",
                                help="Собрать только указанный источник (можно повторять)")
    collect_parser.set_defaults(func=cmd_collect)

    # seed-companies
    seed_parser = subparsers.add_parser(
        "seed-companies", help="Заполнить таблицу компаний справочным списком"
    )
    seed_parser.set_defaults(func=cmd_seed_companies)

    # refresh-dates
    refresh_parser = subparsers.add_parser(
        "refresh-dates", help="Пересчитать даты публикации у сохранённых новостей"
    )
    refresh_parser.add_argument("--all", action="store_true",
                                help="Пересчитать все записи, а не только подозрительные")
    refresh_parser.add_argument("--limit", type=int, default=100000,
                                help="Максимум записей за прогон (по умолчанию: 100000)")
    refresh_parser.add_argument("--workers", type=int, default=8,
                                help="Число параллельных запросов (по умолчанию: 8)")
    refresh_parser.set_defaults(func=cmd_refresh_dates)

    # backfill-summaries
    backfill_parser = subparsers.add_parser(
        "backfill-summaries", help="Догрузить описания (лид) для новостей без него"
    )
    backfill_parser.add_argument("--limit", type=int, default=100000,
                                 help="Максимум записей за прогон (по умолчанию: 100000)")
    backfill_parser.add_argument("--workers", type=int, default=4,
                                 help="Число параллельных запросов (по умолчанию: 4)")
    backfill_parser.add_argument("--refresh", action="store_true",
                                 help="Перечитать описания и у тех новостей, где они уже есть")
    backfill_parser.add_argument("--since", metavar="ГГГГ-ММ-ДД",
                                 help="Только новости, опубликованные не раньше этой даты")
    backfill_parser.set_defaults(func=cmd_backfill_summaries)

    # tags
    tags_parser = subparsers.add_parser(
        "tags", help="Сводка по тегам и влиянию новостей на кадровые движения"
    )
    tags_parser.add_argument("--limit", type=int, default=1000,
                             help="Лимит новостей для анализа (по умолчанию: 1000)")
    tags_parser.add_argument("--show-signal", choices=["высокий", "средний", "нет"],
                             help="Показать новости с этим уровнем влияния на кадры")
    tags_parser.add_argument("--show", type=int, default=10,
                             help="Сколько новостей показать при --show-signal (по умолчанию: 10)")
    tags_parser.add_argument("--type", metavar="ТИП",
                             help="Только материалы этого типа (Реклама, Мероприятие, "
                                  "Обучение, Исследование, Вакансия, Мнение, Новость)")
    tags_parser.add_argument("--exclude-promo", action="store_true",
                             help="Убрать рекламу, анонсы, обучение и колонки")
    tags_parser.set_defaults(func=cmd_tags)

    # cleanup
    cleanup_parser = subparsers.add_parser(
        "cleanup", help="Удалить из БД записи, не являющиеся новостями"
    )
    cleanup_parser.add_argument("--dry-run", action="store_true",
                                help="Только показать, что будет удалено")
    cleanup_parser.set_defaults(func=cmd_cleanup)

    # sources
    sources_parser = subparsers.add_parser(
        "sources", help="Список подключённых источников новостей"
    )
    sources_parser.set_defaults(func=cmd_sources)

    # init
    init_parser = subparsers.add_parser("init", help="Инициализация базы данных")
    init_parser.set_defaults(func=cmd_init)

    return parser


def main() -> int:
    """Основная функция CLI."""
    parser = build_parser()
    args = parser.parse_args()

    log_path = setup_logging(args.verbose)
    logger.debug("Лог прогона: %s", log_path)

    # Схема БД нужна всем командам, а init_db идемпотентна
    init_db()

    try:
        args.func(args)
        return 0
    except KeyboardInterrupt:
        logger.warning("Прервано пользователем")
        return 130
    except Exception:  # noqa: BLE001
        # Трейсбек всегда уходит в файл, поэтому разбор не зависит от того,
        # запускали ли команду с --verbose и сохранилось ли окно терминала.
        logger.exception("Ошибка при выполнении команды")
        print(f"\nОшибка. Подробности с трейсбеком: {log_path}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
