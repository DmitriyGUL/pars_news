#!/usr/bin/env python3
"""
Интерфейс командной строки для проекта парсинга новостей.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Optional

from storage import init_db, get_statistics, export_to_csv
from main import run_all_parsers, save_news
from company_analyzer import get_news_with_companies_from_db, get_all_companies_from_db, find_news_by_company_name
from export_excel import export_analysis_to_excel


def setup_logging(verbose: bool = False) -> None:
    """Настройка логирования."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='[%(asctime)s] [%(levelname)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )


def cmd_parse(args: argparse.Namespace) -> None:
    """Команда парсинга новостей."""
    logging.info("Запуск парсеров новостей...")
    
    items = run_all_parsers(days=args.days, limit_per_source=args.limit)
    inserted = save_news(items)
    
    logging.info(f"В БД добавлено {inserted} новых записей")
    
    if args.export_csv:
        csv_path = export_to_csv()
        logging.info(f"Экспорт в CSV выполнен: {csv_path}")


def cmd_analyze(args: argparse.Namespace) -> None:
    """Команда анализа новостей на предмет упоминаний компаний."""
    logging.info("Анализ новостей на предмет упоминаний компаний...")
    
    company_news = get_news_with_companies_from_db(limit=args.limit)
    
    total_companies = len(company_news)
    total_news = sum(len(news_list) for news_list in company_news.values())
    
    logging.info(f"Результаты анализа:")
    logging.info(f"- Обнаружено компаний: {total_companies}")
    logging.info(f"- Найдено новостей с упоминаниями: {total_news}")
    
    # Выводим топ компаний
    if company_news:
        print("\nТоп компаний по количеству упоминаний:")
        company_stats = []
        for company_name, news_list in company_news.items():
            total_mentions = sum(news.get('mention_count', 0) for news in news_list)
            company_stats.append((company_name, len(news_list), total_mentions))
        
        company_stats.sort(key=lambda x: x[1], reverse=True)
        
        for i, (company, news_count, mentions) in enumerate(company_stats[:args.top], 1):
            print(f"{i}. {company}: {news_count} новостей, {mentions} упоминаний")
    
    if args.export_excel:
        try:
            excel_path = export_analysis_to_excel(limit_news=args.limit)
            logging.info(f"Экспорт в Excel выполнен: {excel_path}")
        except ImportError as e:
            logging.error(f"Ошибка при экспорте в Excel: {e}")
            logging.error("Установите openpyxl: pip install openpyxl")


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
    
    # Дополнительная статистика
    from storage import get_connection
    with get_connection() as conn:
        cursor = conn.execute("SELECT source, COUNT(*) FROM news GROUP BY source ORDER BY COUNT(*) DESC")
        sources = cursor.fetchall()
        
        if sources:
            print("\nРаспределение новостей по источникам:")
            for source, count in sources[:10]:
                print(f"  {source}: {count}")
        
        cursor = conn.execute("SELECT source, COUNT(*) FROM companies GROUP BY source ORDER BY COUNT(*) DESC")
        company_sources = cursor.fetchall()
        
        if company_sources:
            print("\nРаспределение компаний по источникам:")
            for source, count in company_sources:
                print(f"  {source}: {count}")


def cmd_export(args: argparse.Namespace) -> None:
    """Команда экспорта данных."""
    if args.format == "excel":
        try:
            excel_path = export_analysis_to_excel(limit_news=args.limit)
            logging.info(f"Экспорт в Excel выполнен: {excel_path}")
            print(f"\nФайл создан: {excel_path}")
        except ImportError as e:
            logging.error(f"Ошибка при экспорте в Excel: {e}")
            logging.error("Установите openpyxl: pip install openpyxl")
    
    elif args.format == "csv":
        csv_path = export_to_csv()
        logging.info(f"Экспорт в CSV выполнен: {csv_path}")
        print(f"\nФайл создан: {csv_path}")
    
    elif args.format == "both":
        # Экспорт в Excel
        try:
            excel_path = export_analysis_to_excel(limit_news=args.limit)
            logging.info(f"Экспорт в Excel выполнен: {excel_path}")
            print(f"\nExcel файл создан: {excel_path}")
        except ImportError as e:
            logging.error(f"Ошибка при экспорте в Excel: {e}")
            logging.error("Установите openpyxl: pip install openpyxl")
        
        # Экспорт в CSV
        csv_path = export_to_csv()
        logging.info(f"Экспорт в CSV выполнен: {csv_path}")
        print(f"CSV файл создан: {csv_path}")


def cmd_search(args: argparse.Namespace) -> None:
    """Команда поиска новостей по компании."""
    logging.info(f"Поиск новостей по компании: {args.company}")
    
    news_list = find_news_by_company_name(args.company, limit=args.limit)
    
    if not news_list:
        print(f"Не найдено новостей для компании '{args.company}'")
        return
    
    print(f"\nНайдено {len(news_list)} новостей для '{args.company}':")
    for i, news in enumerate(news_list, 1):
        print(f"\n{i}. {news['title']}")
        print(f"   Источник: {news['source']}")
        if news['published_at']:
            print(f"   Дата: {news['published_at']}")
        print(f"   Ссылка: {news['url']}")
        if news.get('text_snippet'):
            print(f"   Сниппет: {news['text_snippet']}")


def cmd_parse_and_export(args: argparse.Namespace) -> None:
    """Команда парсинга новостей с автоматическим экспортом в Excel."""
    logging.info("Запуск парсеров новостей с автоматическим экспортом в Excel...")
    
    # Парсинг новостей
    from main import run_all_parsers
    items = run_all_parsers(days=args.days, limit_per_source=args.limit)
    inserted = save_news(items)
    
    logging.info(f"В БД добавлено {inserted} новых записей")
    
    # Анализ новостей на предмет упоминаний компаний
    logging.info("Анализ новостей на предмет упоминаний компаний...")
    from company_analyzer import get_news_with_companies_from_db
    company_news = get_news_with_companies_from_db(limit=args.analysis_limit)
    
    total_companies = len(company_news)
    total_news = sum(len(news_list) for news_list in company_news.values())
    
    print(f"\nРезультаты анализа:")
    print(f"- Обнаружено компаний: {total_companies}")
    print(f"- Найдено новостей с упоминаниями: {total_news}")
    
    # Экспорт в Excel
    try:
        excel_path = export_analysis_to_excel(limit_news=args.analysis_limit)
        logging.info(f"Экспорт в Excel выполнен: {excel_path}")
        print(f"\nФайл Excel создан: {excel_path}")
        
        # Показываем топ компаний
        if company_news and args.show_top > 0:
            print(f"\nТоп-{args.show_top} компаний по количеству упоминаний:")
            company_stats = []
            for company_name, news_list in company_news.items():
                total_mentions = sum(news.get('mention_count', 0) for news in news_list)
                company_stats.append((company_name, len(news_list), total_mentions))
            
            company_stats.sort(key=lambda x: x[1], reverse=True)
            
            for i, (company, news_count, mentions) in enumerate(company_stats[:args.show_top], 1):
                print(f"{i}. {company}: {news_count} новостей, {mentions} упоминаний")
                
    except ImportError as e:
        logging.error(f"Ошибка при экспорте в Excel: {e}")
        logging.error("Установите openpyxl: pip install openpyxl")


def cmd_init(args: argparse.Namespace) -> None:
    """Команда инициализации базы данных."""
    logging.info("Инициализация базы данных...")
    init_db()
    logging.info("База данных инициализирована")


def main() -> int:
    """Основная функция CLI."""
    parser = argparse.ArgumentParser(
        description="Парсер новостей с анализом упоминаний компаний",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры использования:
  %(prog)s parse --days 7 --limit 100
  %(prog)s analyze --export-excel
  %(prog)s stats
  %(prog)s export --format excel --limit 500
  %(prog)s search --company "Газпром"
  %(prog)s parse-and-export --days 7 --limit 200 --show-top 15
        """
    )
    
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Подробный вывод"
    )
    
    subparsers = parser.add_subparsers(
        title="команды",
        dest="command",
        required=True
    )
    
    # Команда parse
    parse_parser = subparsers.add_parser(
        "parse",
        help="Парсинг новостей из всех источников"
    )
    parse_parser.add_argument(
        "--days", "-d",
        type=int,
        default=7,
        help="Количество дней для парсинга (по умолчанию: 7)"
    )
    parse_parser.add_argument(
        "--limit", "-l",
        type=int,
        default=200,
        help="Лимит новостей на источник (по умолчанию: 200)"
    )
    parse_parser.add_argument(
        "--export-csv",
        action="store_true",
        help="Экспортировать результаты в CSV"
    )
    parse_parser.set_defaults(func=cmd_parse)
    
    # Команда analyze
    analyze_parser = subparsers.add_parser(
        "analyze",
        help="Анализ новостей на предмет упоминаний компаний"
    )
    analyze_parser.add_argument(
        "--limit",
        type=int,
        default=1000,
        help="Лимит новостей для анализа (по умолчанию: 1000)"
    )
    analyze_parser.add_argument(
        "--top",
        type=int,
        default=10,
        help="Количество топ компаний для вывода (по умолчанию: 10)"
    )
    analyze_parser.add_argument(
        "--export-excel",
        action="store_true",
        help="Экспортировать результаты в Excel"
    )
    analyze_parser.set_defaults(func=cmd_analyze)
    
    # Команда stats
    stats_parser = subparsers.add_parser(
        "stats",
        help="Статистика по базе данных"
    )
    stats_parser.set_defaults(func=cmd_stats)
    
    # Команда export
    export_parser = subparsers.add_parser(
        "export",
        help="Экспорт данных"
    )
    export_parser.add_argument(
        "--format",
        choices=["excel", "csv", "both"],
        default="excel",
        help="Формат экспорта (по умолчанию: excel)"
    )
    export_parser.add_argument(
        "--limit",
        type=int,
        default=1000,
        help="Лимит новостей для экспорта (по умолчанию: 1000)"
    )
    export_parser.set_defaults(func=cmd_export)
    
    # Команда search
    search_parser = subparsers.add_parser(
        "search",
        help="Поиск новостей по компании"
    )
    search_parser.add_argument(
        "--company", "-c",
        required=True,
        help="Название компании для поиска"
    )
    search_parser.add_argument(
        "--limit", "-l",
        type=int,
        default=50,
        help="Лимит результатов (по умолчанию: 50)"
    )
    search_parser.set_defaults(func=cmd_search)
    
    # Команда parse-and-export
    parse_export_parser = subparsers.add_parser(
        "parse-and-export",
        help="Парсинг новостей с автоматическим экспортом в Excel"
    )
    parse_export_parser.add_argument(
        "--days", "-d",
        type=int,
        default=7,
        help="Количество дней для парсинга (по умолчанию: 7)"
    )
    parse_export_parser.add_argument(
        "--limit", "-l",
        type=int,
        default=200,
        help="Лимит новостей на источник для парсинга (по умолчанию: 200)"
    )
    parse_export_parser.add_argument(
        "--analysis-limit",
        type=int,
        default=1000,
        help="Лимит новостей для анализа компаний (по умолчанию: 1000)"
    )
    parse_export_parser.add_argument(
        "--show-top",
        type=int,
        default=10,
        help="Количество топ компаний для вывода (по умолчанию: 10)"
    )
    parse_export_parser.set_defaults(func=cmd_parse_and_export)
    
    # Команда init
    init_parser = subparsers.add_parser(
        "init",
        help="Инициализация базы данных"
    )
    init_parser.set_defaults(func=cmd_init)
    
    # Парсинг аргументов
    args = parser.parse_args()
    
    # Настройка логирования
    setup_logging(args.verbose)
    
    # Выполнение команды
    try:
        args.func(args)
        return 0
    except Exception as e:
        logging.error(f"Ошибка при выполнении команды: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())