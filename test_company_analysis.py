#!/usr/bin/env python3
"""
Тестовый скрипт для проверки работы анализатора компаний и экспорта в Excel.
"""

import logging
from datetime import datetime, timedelta

from models import NewsItem
from storage import init_db, save_news
from company_analyzer import detect_companies_in_text, analyze_news_for_companies
from export_excel import export_analysis_to_excel


def setup_logging():
    """Настройка логирования."""
    logging.basicConfig(
        level=logging.INFO,
        format='[%(asctime)s] [%(levelname)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )


def test_detection():
    """Тест обнаружения компаний в тексте."""
    print("Тест обнаружения компаний в тексте:")
    
    test_texts = [
        "Газпром объявил о новых инвестициях в нефтегазовый сектор. Компания Сбербанк также участвует в проекте.",
        "Apple представила новые iPhone, а Microsoft анонсировала обновление Windows.",
        "На встрече присутствовали представители Роснефти и Лукойла, также обсуждались вопросы с ВТБ.",
        "Яндекс и Mail.ru Group объявили о партнерстве в сфере IT-технологий.",
        "Tesla строит новый завод в Европе, Google инвестирует в искусственный интеллект.",
    ]
    
    for i, text in enumerate(test_texts, 1):
        print(f"\nТекст {i}:")
        print(f"  '{text[:50]}...'")
        companies = detect_companies_in_text(text)
        if companies:
            for company, count in companies:
                print(f"  - {company}: {count} упоминаний")
        else:
            print("  Не обнаружено компаний")


def create_test_news():
    """Создание тестовых новостей для проверки."""
    print("\nСоздание тестовых новостей...")
    
    now = datetime.now()
    
    test_news = [
        NewsItem(
            title="Газпром увеличил добычу газа на 15%",
            url="https://example.com/news1",
            source="test",
            published_at=now - timedelta(days=1),
            summary="Компания Газпром сообщила об увеличении добычи природного газа на 15% по сравнению с прошлым годом. Это позволит увеличить экспортные поставки."
        ),
        NewsItem(
            title="Сбербанк запустил новую кредитную программу",
            url="https://example.com/news2",
            source="test",
            published_at=now - timedelta(days=2),
            summary="Сбербанк представил новую кредитную программу для малого бизнеса. Программа включает льготные ставки и упрощенную процедуру оформления."
        ),
        NewsItem(
            title="Apple и Microsoft объявили о сотрудничестве",
            url="https://example.com/news3",
            source="test",
            published_at=now - timedelta(days=3),
            summary="Корпорации Apple и Microsoft договорились о совместной разработке новых технологий. Партнерство охватывает облачные сервисы и искусственный интеллект."
        ),
        NewsItem(
            title="Роснефть и Лукойл обсуждают совместные проекты",
            url="https://example.com/news4",
            source="test",
            published_at=now - timedelta(days=4),
            summary="Представители Роснефти и Лукойла провели встречу по вопросам совместной разработки месторождений. Также обсуждалось сотрудничество с ВТБ."
        ),
        NewsItem(
            title="Яндекс инвестирует в развитие искусственного интеллекта",
            url="https://example.com/news5",
            source="test",
            published_at=now - timedelta(days=5),
            summary="Компания Яндекс объявила о крупных инвестициях в развитие технологий искусственного интеллекта. Проект поддерживается партнерами из Mail.ru Group."
        ),
        NewsItem(
            title="Tesla строит новый завод в Германии",
            url="https://example.com/news6",
            source="test",
            published_at=now - timedelta(days=6),
            summary="Компания Tesla начала строительство нового завода по производству электромобилей в Германии. Google также проявляет интерес к проекту."
        ),
    ]
    
    # Сохраняем тестовые новости
    init_db()
    inserted = save_news(test_news)
    print(f"Добавлено {inserted} тестовых новостей")
    
    return test_news


def test_analysis():
    """Тест анализа новостей на предмет упоминаний компаний."""
    print("\nТест анализа новостей:")
    
    test_news = create_test_news()
    
    # Анализируем новости
    company_news = analyze_news_for_companies(test_news)
    
    print("\nРезультаты анализа:")
    total_companies = len(company_news)
    total_news = sum(len(news_list) for news_list in company_news.values())
    
    print(f"- Обнаружено компаний: {total_companies}")
    print(f"- Найдено новостей с упоминаниями: {total_news}")
    
    if company_news:
        print("\nДетали по компаниям:")
        for company_name, news_list in company_news.items():
            print(f"\n{company_name}: {len(news_list)} новостей")
            for news in news_list:
                print(f"  - {news['title']}")
                if news.get('text_snippet'):
                    print(f"    Сниппет: {news['text_snippet']}")
    
    return company_news


def test_excel_export(company_news):
    """Тест экспорта в Excel."""
    print("\nТест экспорта в Excel...")
    
    try:
        # Создаем тестовые компании для экспорта
        from company_analyzer import get_all_companies_from_db
        
        # Если нет компаний в базе, создаем тестовые
        all_companies = get_all_companies_from_db()
        if not all_companies:
            from models import Company
            from storage import save_companies
            
            test_companies = [
                Company(name="Газпром", source="forbes", rank=1, year=2023),
                Company(name="Сбербанк", source="forbes", rank=2, year=2023),
                Company(name="Роснефть", source="forbes", rank=3, year=2023),
                Company(name="Лукойл", source="forbes", rank=4, year=2023),
                Company(name="Apple", source="fortune", rank=5, year=2023),
                Company(name="Microsoft", source="fortune", rank=6, year=2023),
            ]
            
            save_companies(test_companies)
            all_companies = get_all_companies_from_db()
            print(f"Добавлено {len(test_companies)} тестовых компаний")
        
        # Экспортируем в Excel
        excel_path = export_analysis_to_excel(limit_news=100)
        print(f"\nЭкспорт успешно завершен!")
        print(f"Файл создан: {excel_path}")
        
        # Показываем краткую информацию о файле
        import os
        if os.path.exists(excel_path):
            file_size = os.path.getsize(excel_path)
            print(f"Размер файла: {file_size / 1024:.2f} KB")
        
        return excel_path
        
    except ImportError as e:
        print(f"Ошибка: {e}")
        print("Для работы экспорта в Excel требуется установить openpyxl:")
        print("pip install openpyxl")
        return None
    except Exception as e:
        print(f"Ошибка при экспорте: {e}")
        return None


def main():
    """Основная функция тестирования."""
    setup_logging()
    
    print("=" * 60)
    print("ТЕСТ АНАЛИЗАТОРА КОМПАНИЙ И ЭКСПОРТА В EXCEL")
    print("=" * 60)
    
    # Тест обнаружения компаний
    test_detection()
    
    # Тест анализа новостей
    company_news = test_analysis()
    
    # Тест экспорта в Excel
    if company_news:
        excel_path = test_excel_export(company_news)
        
        if excel_path:
            print("\n" + "=" * 60)
            print("ТЕСТ УСПЕШНО ЗАВЕРШЕН!")
            print("=" * 60)
            print("\nЧто было сделано:")
            print("1. Протестировано обнаружение компаний в тексте")
            print("2. Созданы тестовые новости и сохранены в БД")
            print("3. Проанализированы новости на предмет упоминаний компаний")
            print("4. Создан Excel файл с результатами анализа")
            print("\nДля проверки работы с реальными данными:")
            print("1. Запустите парсер: python cli.py parse")
            print("2. Проанализируйте данные: python cli.py analyze --export-excel")
            print("3. Посмотрите статистику: python cli.py stats")
        else:
            print("\nТест экспорта не выполнен. Проверьте наличие openpyxl.")
    else:
        print("\nНе удалось протестировать анализ новостей.")


if __name__ == "__main__":
    main()