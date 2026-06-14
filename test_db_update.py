#!/usr/bin/env python3
"""Тест обновления базы данных."""

import os
import sys
import sqlite3

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def check_db_structure():
    """Проверяет структуру базы данных."""
    db_path = os.path.join(os.path.dirname(__file__), "news.db")
    
    print("Проверка структуры базы данных...")
    print("=" * 60)
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Проверяем таблицы
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        tables = cursor.fetchall()
        print(f"Таблицы в БД: {[t[0] for t in tables]}")
        
        # Проверяем структуру таблицы news
        print("\nСтруктура таблицы 'news':")
        cursor.execute("PRAGMA table_info(news)")
        columns = cursor.fetchall()
        for col in columns:
            print(f"  {col[1]:20} {col[2]:15} {'PK' if col[5] else ''}")
        
        # Проверяем индексы
        print("\nИндексы таблицы 'news':")
        cursor.execute("SELECT name, sql FROM sqlite_master WHERE type='index' AND tbl_name='news'")
        indexes = cursor.fetchall()
        for idx in indexes:
            print(f"  {idx[0]}: {idx[1]}")
        
        # Проверяем количество записей
        cursor.execute("SELECT COUNT(*) FROM news")
        count = cursor.fetchone()[0]
        print(f"\nЗаписей в таблице 'news': {count}")
        
        # Проверяем примеры записей
        if count > 0:
            cursor.execute("SELECT title, source, published_at, created_at FROM news ORDER BY id DESC LIMIT 3")
            rows = cursor.fetchall()
            print("\nПоследние 3 записи:")
            for i, row in enumerate(rows, 1):
                title, source, published_at, created_at = row
                print(f"  {i}. [{source}] {title[:50]}...")
                print(f"     Дата публикации: {published_at or 'нет'}")
                print(f"     Дата создания: {created_at}")
        
        # Проверяем наличие колонки created_at
        cursor.execute("SELECT COUNT(*) FROM news WHERE created_at IS NOT NULL")
        with_created_at = cursor.fetchone()[0]
        print(f"\nЗаписей с created_at: {with_created_at} из {count}")
        
        conn.close()
        
        return True
        
    except Exception as e:
        print(f"Ошибка при проверке БД: {e}")
        return False


def test_insert_new_record():
    """Тестирует вставку новой записи."""
    print("\n" + "=" * 60)
    print("Тест вставки новой записи...")
    
    try:
        from storage import save_news
        from models import NewsItem
        from datetime import datetime
        
        # Создаем тестовую новость
        test_item = NewsItem(
            title="Тестовая новость для проверки работы БД",
            url="https://example.com/test-news-" + str(int(datetime.now().timestamp())),
            source="test",
            published_at=datetime.now(),
            summary="Это тестовая новость для проверки обновления базы данных"
        )
        
        # Пытаемся сохранить
        inserted = save_news([test_item])
        print(f"Вставлено новых записей: {inserted}")
        
        # Проверяем, что запись добавилась
        db_path = os.path.join(os.path.dirname(__file__), "news.db")
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM news WHERE source = 'test'")
        test_count = cursor.fetchone()[0]
        
        print(f"Тестовых записей в БД: {test_count}")
        
        # Очищаем тестовые записи
        cursor.execute("DELETE FROM news WHERE source = 'test'")
        conn.commit()
        conn.close()
        
        return inserted > 0
        
    except Exception as e:
        print(f"Ошибка при тесте вставки: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Основная функция тестирования."""
    print("Тест обновления базы данных pars_news")
    print("=" * 60)
    
    # Проверяем существование файла БД
    db_path = os.path.join(os.path.dirname(__file__), "news.db")
    if os.path.exists(db_path):
        print(f"Файл БД найден: {db_path} ({os.path.getsize(db_path)} байт)")
    else:
        print("Файл БД не найден. Создаем новую БД...")
        from storage import init_db
        init_db()
    
    # Проверяем структуру
    db_ok = check_db_structure()
    
    # Тестируем вставку
    insert_ok = test_insert_new_record()
    
    print("\n" + "=" * 60)
    print("РЕЗУЛЬТАТЫ ТЕСТА:")
    
    if db_ok and insert_ok:
        print("✅ База данных работает корректно")
        print("   - Структура таблиц проверена")
        print("   - Вставка новых записей работает")
        print("   - Колонка created_at присутствует")
    else:
        print("❌ Есть проблемы с базой данных")
        if not db_ok:
            print("   - Проблема со структурой БД")
        if not insert_ok:
            print("   - Проблема с вставкой записей")
    
    print("\nДля полной проверки запустите:")
    print("  py main.py")
    print("  py cli.py stats")


if __name__ == "__main__":
    main()