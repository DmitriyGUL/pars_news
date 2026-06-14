from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

try:
    import openpyxl
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill, Border, Side
    from openpyxl.utils import get_column_letter
except ImportError:
    print("Ошибка: Модуль openpyxl не установлен. Установите его: pip install openpyxl")
    raise


logger = logging.getLogger(__name__)


def create_excel_export(
    company_news: Dict[str, List[Dict]], 
    all_companies: List[Dict], 
    output_path: Optional[Path] = None
) -> str:
    """
    Создает Excel файл с двумя листами:
    1. Компании (все компании из базы данных)
    2. Новости по компаниям (анализ новостей на предмет упоминаний компаний)
    
    Возвращает путь к созданному файлу.
    """
    if output_path is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = Path(f"news_analysis_{timestamp}.xlsx")
    
    # Создаем новую книгу Excel
    wb = Workbook()
    
    # Создаем лист для компаний
    create_companies_sheet(wb, all_companies)
    
    # Создаем лист для новостей по компаниям
    create_company_news_sheet(wb, company_news)
    
    # Удаляем дефолтный лист, если он пустой
    if "Sheet" in wb.sheetnames:
        # Подсчитываем количество строк с данными
        sheet = wb["Sheet"]
        max_row = sheet.max_row
        if max_row <= 1:  # Только заголовок или пустой
            del wb["Sheet"]
    
    # Сохраняем файл
    wb.save(output_path)
    
    logger.info(f"Excel файл успешно создан: {output_path}")
    return str(output_path)


def create_companies_sheet(wb: Workbook, companies: List[Dict]) -> None:
    """
    Создает лист с информацией о компаниях.
    """
    ws = wb.create_sheet(title="Компании")
    
    # Заголовки
    headers = ["Название компании", "Источник", "Рейтинг", "Год", "Ссылка", "Дата добавления"]
    ws.append(headers)
    
    # Стили для заголовков
    header_font = Font(bold=True, size=12)
    header_fill = PatternFill(start_color="366092", end_color="366092", fill_type="solid")
    header_font_color = Font(color="FFFFFF", bold=True)
    thin_border = Border(
        left=Side(style="thin"),
        right=Side(style="thin"),
        top=Side(style="thin"),
        bottom=Side(style="thin")
    )
    
    # Применяем стили к заголовкам
    for col in range(1, len(headers) + 1):
        cell = ws.cell(row=1, column=col)
        cell.font = header_font_color
        cell.fill = header_fill
        cell.border = thin_border
        cell.alignment = Alignment(horizontal="center", vertical="center")
    
    # Добавляем данные
    for company in companies:
        row = [
            company.get('name', ''),
            company.get('source', ''),
            company.get('rank', ''),
            company.get('year', ''),
            company.get('url', ''),
            company.get('created_at', ''),
        ]
        ws.append(row)
    
    # Настраиваем ширину колонок
    column_widths = [35, 15, 10, 10, 50, 20]
    for i, width in enumerate(column_widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = width
    
    # Применяем стили к данным
    data_font = Font(size=11)
    for row in ws.iter_rows(min_row=2, max_row=ws.max_row, min_col=1, max_col=len(headers)):
        for cell in row:
            cell.font = data_font
            cell.border = thin_border
            cell.alignment = Alignment(vertical="center", wrap_text=True)
    
    # Замораживаем заголовки
    ws.freeze_panes = "A2"


def create_company_news_sheet(wb: Workbook, company_news: Dict[str, List[Dict]]) -> None:
    """
    Создает лист с новостями, сгруппированными по компаниям.
    """
    ws = wb.create_sheet(title="Новости по компаниям")
    
    # Заголовки
    headers = [
        "Компания", 
        "Количество упоминаний", 
        "Заголовок новости", 
        "Источник новости", 
        "Дата публикации", 
        "Ссылка", 
        "Сниппет текста"
    ]
    ws.append(headers)
    
    # Стили для заголовков
    header_font = Font(bold=True, size=12)
    header_fill = PatternFill(start_color="C65911", end_color="C65911", fill_type="solid")
    header_font_color = Font(color="FFFFFF", bold=True)
    thin_border = Border(
        left=Side(style="thin"),
        right=Side(style="thin"),
        top=Side(style="thin"),
        bottom=Side(style="thin")
    )
    
    # Применяем стили к заголовкам
    for col in range(1, len(headers) + 1):
        cell = ws.cell(row=1, column=col)
        cell.font = header_font_color
        cell.fill = header_fill
        cell.border = thin_border
        cell.alignment = Alignment(horizontal="center", vertical="center")
    
    # Добавляем данные
    row_index = 2
    for company_name, news_list in sorted(company_news.items()):
        for news in news_list:
            row = [
                company_name,
                news.get('mention_count', 0),
                news.get('title', ''),
                news.get('source', ''),
                news.get('published_at', ''),
                news.get('url', ''),
                news.get('text_snippet', '')[:200]  # Ограничиваем длину сниппета
            ]
            ws.append(row)
            
            # Закрашиваем строки для разных компаний разными цветами
            fill_color = "E2EFDA" if row_index % 2 == 0 else "DDEBF7"
            for col in range(1, len(headers) + 1):
                cell = ws.cell(row=row_index, column=col)
                cell.fill = PatternFill(start_color=fill_color, end_color=fill_color, fill_type="solid")
            
            row_index += 1
    
    # Настраиваем ширину колонок
    column_widths = [25, 15, 50, 15, 20, 50, 60]
    for i, width in enumerate(column_widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = width
    
    # Применяем стили к данным
    data_font = Font(size=11)
    for row in ws.iter_rows(min_row=2, max_row=ws.max_row, min_col=1, max_col=len(headers)):
        for cell in row:
            cell.font = data_font
            cell.border = thin_border
            cell.alignment = Alignment(vertical="center", wrap_text=True)
    
    # Замораживаем заголовки
    ws.freeze_panes = "A2"
    
    # Создаем сводную таблицу на отдельном листе
    create_summary_sheet(wb, company_news)


def create_summary_sheet(wb: Workbook, company_news: Dict[str, List[Dict]]) -> None:
    """
    Создает сводный лист со статистикой по компаниям.
    """
    ws = wb.create_sheet(title="Статистика")
    
    # Заголовки
    headers = ["Компания", "Количество новостей", "Общее количество упоминаний", "Последняя дата"]
    ws.append(headers)
    
    # Стили для заголовков
    header_fill = PatternFill(start_color="7030A0", end_color="7030A0", fill_type="solid")
    header_font_color = Font(color="FFFFFF", bold=True)
    thin_border = Border(
        left=Side(style="thin"),
        right=Side(style="thin"),
        top=Side(style="thin"),
        bottom=Side(style="thin")
    )
    
    # Применяем стили к заголовкам
    for col in range(1, len(headers) + 1):
        cell = ws.cell(row=1, column=col)
        cell.font = header_font_color
        cell.fill = header_fill
        cell.border = thin_border
        cell.alignment = Alignment(horizontal="center", vertical="center")
    
    # Собираем статистику
    stats = []
    for company_name, news_list in company_news.items():
        total_news = len(news_list)
        total_mentions = sum(news.get('mention_count', 0) for news in news_list)
        
        # Ищем последнюю дату
        latest_date = None
        latest_date_str = "Неизвестно"
        
        for news in news_list:
            date_str = news.get('published_at')
            if date_str:
                try:
                    # Обработка даты с учетом часовых поясов
                    date_str_clean = date_str.replace('Z', '+00:00')
                    date = datetime.fromisoformat(date_str_clean)
                    
                    # Приводим все даты к наивным (без часового пояса) для сравнения
                    if date.tzinfo is not None:
                        date = date.replace(tzinfo=None)
                    
                    if latest_date is None or date > latest_date:
                        latest_date = date
                        latest_date_str = latest_date.strftime("%Y-%m-%d")
                        
                except (ValueError, AttributeError):
                    pass
        
        stats.append({
            'company': company_name,
            'news_count': total_news,
            'total_mentions': total_mentions,
            'latest_date': latest_date_str
        })
    
    # Сортируем по количеству новостей (по убыванию)
    stats.sort(key=lambda x: x['news_count'], reverse=True)
    
    # Добавляем данные
    for stat in stats:
        row = [
            stat['company'],
            stat['news_count'],
            stat['total_mentions'],
            stat['latest_date']
        ]
        ws.append(row)
    
    # Настраиваем ширину колонок
    column_widths = [25, 20, 25, 15]
    for i, width in enumerate(column_widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = width
    
    # Применяем стили к данным
    data_font = Font(size=11)
    for row in ws.iter_rows(min_row=2, max_row=ws.max_row, min_col=1, max_col=len(headers)):
        for cell in row:
            cell.font = data_font
            cell.border = thin_border
            cell.alignment = Alignment(horizontal="center", vertical="center")
    
    # Замораживаем заголовки
    ws.freeze_panes = "A2"


def export_analysis_to_excel(limit_news: int = 1000) -> str:
    """
    Основная функция для экспорта анализа в Excel.
    """
    from company_analyzer import get_news_with_companies_from_db, get_all_companies_from_db
    
    logger.info("Начинаем анализ новостей на предмет упоминаний компаний...")
    company_news = get_news_with_companies_from_db(limit=limit_news)
    
    logger.info("Получаем список компаний из базы данных...")
    all_companies = get_all_companies_from_db()
    
    logger.info("Создаем Excel файл...")
    excel_path = create_excel_export(company_news, all_companies)
    
    # Выводим статистику
    total_companies = len(company_news)
    total_news = sum(len(news_list) for news_list in company_news.values())
    
    logger.info(f"Анализ завершен:")
    logger.info(f"- Обнаружено компаний: {total_companies}")
    logger.info(f"- Найдено новостей с упоминаниями: {total_news}")
    logger.info(f"- Всего компаний в базе: {len(all_companies)}")
    logger.info(f"- Excel файл сохранен: {excel_path}")
    
    return excel_path


if __name__ == "__main__":
    import sys
    
    # Настраиваем логирование
    logging.basicConfig(
        level=logging.INFO,
        format='[%(asctime)s] [%(levelname)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Определяем лимит новостей из аргументов командной строки
    limit = 1000
    if len(sys.argv) > 1:
        try:
            limit = int(sys.argv[1])
        except ValueError:
            print(f"Использование: python {sys.argv[0]} [лимит_новостей]")
            print(f"Пример: python {sys.argv[0]} 500")
            sys.exit(1)
    
    try:
        export_analysis_to_excel(limit_news=limit)
        print("\nЭкспорт успешно завершен!")
    except Exception as e:
        logger.error(f"Ошибка при экспорте: {e}")
        sys.exit(1)