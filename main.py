from __future__ import annotations

import argparse
import logging
import sys
from typing import List, Optional

from models import NewsItem
from storage import get_latest, init_db, save_news, get_statistics
from sources import adindex, comnews, forbes_companies, rbc_companies, ria_companies
from company_analyzer import get_news_with_companies_from_db
from export_excel import export_analysis_to_excel


# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

PARSERS = [
    ("adindex", adindex.fetch),
    ("comnews", comnews.fetch),
    ("rbc_companies", rbc_companies.fetch),
    ("ria_companies", ria_companies.fetch),
    ("forbes_companies", forbes_companies.fetch),
]


def run_all_parsers(days: int = 7, limit_per_source: int = 200) -> List[NewsItem]:
    collected: List[NewsItem] = []

    for source_name, fetch_func in PARSERS:
        try:
            items = fetch_func(limit=limit_per_source, days=days)
        except Exception as exc:  # noqa: BLE001
            logger.error(f"{source_name}: {exc}")
            continue

        logger.info(f"{source_name}: получено {len(items)} записей")
        collected.extend(items)

    return collected


def parse_news(args: argparse.Namespace) -> None:
    """Парсинг новостей."""
    logger.info("Запуск парсеров новостей...")
    
    items = run_all_parsers(days=args.days, limit_per_source=args.limit)
    inserted = save_news(items)
    
    logger.info(f"В БД добавлено {inserted} новых записей")
    
    # Показываем последние новости
    if args.show_latest:
        latest = get_latest(limit=args.show_latest)
        print("\nПоследние новости:")
        for item in latest:
            date_str = item.published_at.isoformat() if item.published_at else "без даты"
            print(f"- [{item.source}] {date_str} — {item.title[:80]}...")


def analyze_companies(args: argparse.Namespace) -> None:
    """Анализ новостей на предмет упоминаний компаний."""
    logger.info("Анализ новостей на предмет упоминаний компаний...")
    
    company_news = get_news_with_companies_from_db(limit=args.limit)
    
    total_companies = len(company_news)
    total_news = sum(len(news_list) for news_list in company_news.values())
    
    print(f"\nРезультаты анализа:")
    print(f"- Обнаружено компаний: {total_companies}")
    print(f"- Найдено новостей с упоминаниями: {total_news}")
    
    # Выводим топ компаний
    if company_news and args.show_top > 0:
        print(f"\nТоп-{args.show_top} компаний по количеству упоминаний:")
        company_stats = []
        for company_name, news_list in company_news.items():
            total_mentions = sum(news.get('mention_count', 0) for news in news_list)
            company_stats.append((company_name, len(news_list), total_mentions))
        
        company_stats.sort(key=lambda x: x[1], reverse=True)
        
        for i, (company, news_count, mentions) in enumerate(company_stats[:args.show_top], 1):
            print(f"{i}. {company}: {news_count} новостей, {mentions} упоминаний")
    
    # Экспорт в Excel
    if args.export_excel:
        try:
            excel_path = export_analysis_to_excel(limit_news=args.limit)
            logger.info(f"Экспорт в Excel выполнен: {excel_path}")
        except ImportError as e:
            logger.error(f"Ошибка при экспорте в Excel: {e}")
            logger.error("Установите openpyxl: pip install openpyxl")


def show_stats(args: argparse.Namespace) -> None:
    """Показать статистику."""
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
    
    # Показываем последние новости
    if args.show_latest > 0:
        from storage import get_latest
        latest = get_latest(limit=args.show_latest)
        print(f"\nПоследние {args.show_latest} новостей:")
        for item in latest:
            date_str = item.published_at.isoformat() if item.published_at else "без даты"
            print(f"- [{item.source}] {date_str} — {item.title[:80]}...")


def export_data(args: argparse.Namespace) -> None:
    """Экспорт данных."""
    if args.format == "excel":
        try:
            excel_path = export_analysis_to_excel(limit_news=args.limit)
            logger.info(f"Экспорт в Excel выполнен: {excel_path}")
            print(f"\nФайл создан: {excel_path}")
        except ImportError as e:
            logger.error(f"Ошибка при экспорте в Excel: {e}")
            logger.error("Установите openpyxl: pip install openpyxl")
    else:
        logger.warning(f"Формат {args.format} пока не поддерживается")


def parse_and_export(args: argparse.Namespace) -> None:
    """Парсинг новостей с автоматическим экспортом в Excel."""
    logger.info("Запуск парсеров новостей с автоматическим экспортом в Excel...")
    
    # Парсинг новостей
    items = run_all_parsers(days=args.days, limit_per_source=args.limit)
    inserted = save_news(items)
    
    logger.info(f"В БД добавлено {inserted} новых записей")
    
    # Анализ новостей на предмет упоминаний компаний
    logger.info("Анализ новостей на предмет упоминаний компаний...")
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
        logger.info(f"Экспорт в Excel выполнен: {excel_path}")
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
        logger.error(f"Ошибка при экспорте в Excel: {e}")
        logger.error("Установите openpyxl: pip install openpyxl")


def main() -> None:
    """Основная функция с аргументами командной строки."""
    parser = argparse.ArgumentParser(
        description="Парсер новостей с анализом упоминаний компаний",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры использования:
  %(prog)s parse --days 7 --limit 100
  %(prog)s analyze --export-excel --show-top 20
  %(prog)s stats --show-latest 10
  %(prog)s export --format excel --limit 500
  %(prog)s parse-and-export --days 7 --limit 200 --show-top 15
        """
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
        "--show-latest",
        type=int,
        default=10,
        help="Количество последних новостей для показа (по умолчанию: 10)"
    )
    
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
        "--show-top",
        type=int,
        default=10,
        help="Количество топ компаний для вывода (по умолчанию: 10)"
    )
    analyze_parser.add_argument(
        "--export-excel",
        action="store_true",
        help="Экспортировать результаты в Excel"
    )
    
    # Команда stats
    stats_parser = subparsers.add_parser(
        "stats",
        help="Статистика по базе данных"
    )
    stats_parser.add_argument(
        "--show-latest",
        type=int,
        default=0,
        help="Количество последних новостей для показа (по умолчанию: 0)"
    )
    
    # Команда export
    export_parser = subparsers.add_parser(
        "export",
        help="Экспорт данных"
    )
    export_parser.add_argument(
        "--format",
        choices=["excel"],
        default="excel",
        help="Формат экспорта (по умолчанию: excel)"
    )
    export_parser.add_argument(
        "--limit",
        type=int,
        default=1000,
        help="Лимит новостей для экспорта (по умолчанию: 1000)"
    )
    
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
    
    # Парсинг аргументов
    args = parser.parse_args()
    
    # Инициализация базы данных
    init_db()
    
    # Выполнение команды
    try:
        if args.command == "parse":
            parse_news(args)
        elif args.command == "analyze":
            analyze_companies(args)
        elif args.command == "stats":
            show_stats(args)
        elif args.command == "export":
            export_data(args)
        elif args.command == "parse-and-export":
            parse_and_export(args)
        else:
            parser.print_help()
    except Exception as e:
        logger.error(f"Ошибка при выполнении: {e}")
        sys.exit(1)


def legacy_main() -> None:
    """Стартовый main для обратной совместимости."""
    logger.info("Запуск парсера новостей")
    init_db()
    
    # По умолчанию собираем публикации примерно за последнюю неделю
    items = run_all_parsers(days=7, limit_per_source=200)

    inserted = save_news(items)
    logger.info(f"В БД добавлено {inserted} новых записей")

    latest = get_latest(limit=10)
    print("\nПоследние новости:")
    for item in latest:
        date_str = item.published_at.isoformat() if item.published_at else "без даты"
        print(f"- [{item.source}] {date_str} — {item.title[:80]}...")
    
    # Предлагаем проанализировать компании
    print("\nХотите проанализировать новости на предмет упоминаний компаний?")
    print("Используйте: python main.py analyze --export-excel")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        # Новый режим с аргументами командной строки
        main()
    else:
        # Старый режим для обратной совместимости
        legacy_main()