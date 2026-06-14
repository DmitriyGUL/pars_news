#!/usr/bin/env python3
"""Обновляет все парсеры для использования новой архитектуры."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def update_parser_file(filepath, class_name, source_name, base_url, news_url):
    """Обновляет файл парсера."""
    template = '''from __future__ import annotations

from typing import List
from bs4 import BeautifulSoup

from models import NewsItem
from .base_parser import BaseParser
from .date_utils import parse_date_from_tag, parse_date_from_url


class {class_name}(BaseParser):
    """Парсер новостей с сайта {base_url}."""
    
    BASE_URL = "{base_url}"
    NEWS_URL = "{news_url}"
    SOURCE_NAME = "{source_name}"
    
    HEADERS = {{
        "User-Agent": "pars_news/0.1 (+{base_url})",
    }}
    
    def _parse_page(self, soup: BeautifulSoup, cutoff, seen_urls) -> List[NewsItem]:
        """Парсит новости с одной страницы."""
        items: List[NewsItem] = []
        
        # TODO: Реализовать специфичный для сайта парсинг
        # Пример:
        # for link in soup.select("a[href*='/news/']"):
        #     href = link.get("href")
        #     if not href:
        #         continue
        #     
        #     title = link.get_text(strip=True)
        #     if not title or len(title) < 10:
        #         continue
        #     
        #     url = self._make_absolute_url(href)
        #     if not url:
        #         continue
        #     
        #     if url in seen_urls:
        #         continue
        #     seen_urls.add(url)
        #     
        #     block = link.find_parent("article") or link.find_parent("div") or link
        #     published_at = parse_date_from_tag(block) or parse_date_from_url(url)
        #     if published_at and published_at < cutoff:
        #         continue
        #     
        #     items.append(
        #         NewsItem(
        #             title=title,
        #             url=url,
        #             source=self.SOURCE_NAME,
        #             published_at=published_at,
        #         )
        #     )
        
        return items


def fetch(limit: int = 200, days: int = 7) -> List[NewsItem]:
    """Функция для обратной совместимости."""
    parser = {class_name}()
    return parser.fetch(limit, days)
'''
    
    content = template.format(
        class_name=class_name,
        base_url=base_url,
        news_url=news_url,
        source_name=source_name
    )
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print(f"✓ Обновлен: {os.path.basename(filepath)}")


def main():
    """Основная функция."""
    print("Обновление парсеров для новой архитектуры")
    print("=" * 60)
    
    parsers_info = [
        {
            'filepath': 'sources/adindex.py',
            'class_name': 'AdindexParser',
            'source_name': 'adindex',
            'base_url': 'https://adindex.ru',
            'news_url': 'https://adindex.ru/news/hr/'
        },
        {
            'filepath': 'sources/comnews.py',
            'class_name': 'ComnewsParser',
            'source_name': 'comnews',
            'base_url': 'https://www.comnews.ru',
            'news_url': 'https://www.comnews.ru/manpower'
        },
        {
            'filepath': 'sources/rbc_companies.py',
            'class_name': 'RbcCompaniesParser',
            'source_name': 'rbc_companies',
            'base_url': 'https://companies.rbc.ru',
            'news_url': 'https://companies.rbc.ru/'
        },
        {
            'filepath': 'sources/ria_companies.py',
            'class_name': 'RiaCompaniesParser',
            'source_name': 'ria_companies',
            'base_url': 'https://ria.ru',
            'news_url': 'https://ria.ru/company/'
        },
        {
            'filepath': 'sources/forbes_companies.py',
            'class_name': 'ForbesCompaniesParser',
            'source_name': 'forbes_companies',
            'base_url': 'https://www.forbes.ru',
            'news_url': 'https://www.forbes.ru/novosti-kompaniy/'
        },
    ]
    
    for parser in parsers_info:
        update_parser_file(**parser)
    
    print("\n" + "=" * 60)
    print("ВАЖНО: Парсеры обновлены, но требуют настройки!")
    print("Каждому парсеру нужно настроить метод _parse_page()")
    print("для специфичной структуры соответствующего сайта.")
    print("\nДля тестирования запустите:")
    print("  py test_simple.py")
    print("  py main.py")


if __name__ == "__main__":
    main()