from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple
from storage import get_connection
from models import NewsItem


# Словарь алиасов компаний для поиска по именам
COMPANY_ALIASES: Dict[str, List[str]] = {
    # Крупные российские компании
    "Газпром": ["газпром", "gazprom", "Газпром", "ГАЗПРОМ"],
    "Сбербанк": ["сбербанк", "sberbank", "Сбербанк", "СБЕРБАНК", "Сбер", "sber"],
    "ВТБ": ["втб", "ВТБ", "vtb", "VTB", "банк ВТБ"],
    "Роснефть": ["роснефть", "rosneft", "Роснефть", "РОСНЕФТЬ"],
    "Лукойл": ["лукойл", "lukoil", "Лукойл", "ЛУКОЙЛ"],
    "Норильский никель": ["норильский никель", "norilsk nickel", "Норильский никель", "Норильск"],
    "Северсталь": ["северсталь", "severstal", "Северсталь", "СЕВЕРСТАЛЬ"],
    "Магнит": ["магнит", "magnit", "Магнит", "МАГНИТ"],
    "Яндекс": ["яндекс", "yandex", "Яндекс", "YANDEX", "Yandex"],
    "МТС": ["мтс", "mts", "МТС", "MTS"],
    "Мегафон": ["мегафон", "megafon", "Мегафон", "MEGAFON"],
    "РЖД": ["ржд", "rzd", "РЖД", "Российские железные дороги"],
    "Аэрофлот": ["аэрофлот", "aeroflot", "Аэрофлот", "АЭРОФЛОТ"],
    "Татнефть": ["татнефть", "tatneft", "Татнефть", "ТАТНЕФТЬ"],
    "Сургутнефтегаз": ["сургутнефтегаз", "surgutneftegas", "Сургутнефтегаз", "СУРГУТНЕФТЕГАЗ"],
    
    # Иностранные компании
    "Apple": ["apple", "Apple", "APPLE", "эпл"],
    "Microsoft": ["microsoft", "Microsoft", "MICROSOFT", "майкрософт"],
    "Google": ["google", "Google", "GOOGLE", "гугл"],
    "Amazon": ["amazon", "Amazon", "AMAZON", "амазон"],
    "Meta": ["meta", "Meta", "META", "facebook", "Facebook", "FACEBOOK"],
    "Tesla": ["tesla", "Tesla", "TESLA", "тесла"],
    "BP": ["bp", "BP", "British Petroleum", "бритиш петролеум"],
    "Shell": ["shell", "Shell", "SHELL", "шелл"],
    "Exxon": ["exxon", "Exxon", "EXXON", "экссон"],
    "Chevron": ["chevron", "Chevron", "CHEVRON", "шеврон"],
    
    # Банки
    "Альфа-Банк": ["альфа-банк", "альфа банк", "alfabank", "Альфа-Банк", "Альфа Банк"],
    "Тинькофф": ["тинькофф", "tinkoff", "Тинькофф", "ТИНЬКОФФ", "Тинькофф банк"],
    "Райффайзенбанк": ["райффайзенбанк", "raiffeisen", "Raiffeisen", "Райффайзенбанк", "Райффайзен"],
    "Открытие": ["открытие", "открытие банк", "открытие", "Открытие", "Банк Открытие"],
    
    # Телеком
    "Билайн": ["билайн", "beeline", "Билайн", "BEELINE"],
    "Теле2": ["теле2", "tele2", "Теле2", "TELE2"],
    "Ростелеком": ["ростелеком", "rostelecom", "Ростелеком", "РОСТЕЛЕКОМ"],
    
    # Ретейл
    "X5 Retail Group": ["x5", "x5 retail", "x5 retail group", "X5", "X5 Retail Group"],
    "Дикси": ["дикси", "dixy", "Дикси", "ДИКСИ"],
    "Лента": ["лента", "lenta", "Лента", "ЛЕНТА"],
    "О'Кей": ["окей", "o'key", "о'кей", "О'Кей", "ОКЕЙ"],
    
    # Автопроизводители
    "АвтоВАЗ": ["автоваз", "avtovaz", "АвтоВАЗ", "АВТОВАЗ", "Lada", "лада"],
    "КамАЗ": ["камаз", "kamaz", "КамАЗ", "КАМАЗ"],
    "Группа ГАЗ": ["газ", "группа газ", "group gaz", "ГАЗ", "Группа ГАЗ"],
    "Уралвагонзавод": ["уралвагонзавод", "uralvagonzavod", "Уралвагонзавод", "УРАЛВАГОНЗАВОД"],
    
    # IT и телеком
    "Mail.ru Group": ["mail.ru", "mailru", "mail.ru group", "Mail.ru", "Mail.ru Group"],
    "Ростех": ["ростех", "rosteh", "Ростех", "РОСТЕХ"],
    "Роскосмос": ["роскосмос", "roscosmos", "Роскосмос", "РОСКОСМОС"],
}


def detect_companies_in_text(text: str) -> List[Tuple[str, int]]:
    """
    Обнаруживает упоминания компаний в тексте.
    Возвращает список кортежей (имя_компании, количество_упоминаний).
    """
    text_lower = text.lower()
    detected = {}
    
    for company_name, aliases in COMPANY_ALIASES.items():
        total_count = 0
        for alias in aliases:
            # Ищем точные вхождения (с границами слов)
            pattern = r'\b' + re.escape(alias.lower()) + r'\b'
            count = len(re.findall(pattern, text_lower))
            total_count += count
        
        if total_count > 0:
            detected[company_name] = total_count
    
    # Сортируем по количеству упоминаний (по убыванию)
    return sorted(detected.items(), key=lambda x: x[1], reverse=True)


def analyze_news_for_companies(news_items: List[NewsItem]) -> Dict[str, List[Dict]]:
    """
    Анализирует список новостей и возвращает словарь с компаниями и связанными новостями.
    Формат: {company_name: [news_data_dict, ...]}
    """
    company_news = {}
    
    for news in news_items:
        # Анализируем заголовок и описание (если есть)
        text_to_analyze = news.title
        if news.summary:
            text_to_analyze += " " + news.summary
        
        companies_found = detect_companies_in_text(text_to_analyze)
        
        for company_name, count in companies_found:
            if company_name not in company_news:
                company_news[company_name] = []
            
            company_news[company_name].append({
                'title': news.title,
                'url': news.url,
                'source': news.source,
                'published_at': news.published_at.isoformat() if news.published_at else None,
                'summary': news.summary,
                'mention_count': count,
                'text_snippet': _extract_snippet_with_company(text_to_analyze, company_name)
            })
    
    return company_news


def _extract_snippet_with_company(text: str, company_name: str, snippet_length: int = 100) -> Optional[str]:
    """
    Извлекает сниппет текста с упоминанием компании.
    """
    text_lower = text.lower()
    company_aliases = COMPANY_ALIASES.get(company_name, [company_name.lower()])
    
    for alias in company_aliases:
        alias_lower = alias.lower()
        if alias_lower in text_lower:
            start = text_lower.find(alias_lower)
            
            # Вычисляем границы для сниппета
            snippet_start = max(0, start - snippet_length // 2)
            snippet_end = min(len(text), start + len(alias_lower) + snippet_length // 2)
            
            snippet = text[snippet_start:snippet_end]
            
            # Добавляем многоточие если текст обрезан
            if snippet_start > 0:
                snippet = "..." + snippet
            if snippet_end < len(text):
                snippet = snippet + "..."
            
            return snippet
    
    return None


def get_news_with_companies_from_db(limit: int = 1000) -> Dict[str, List[Dict]]:
    """
    Получает новости из базы данных и анализирует их на предмет упоминаний компаний.
    """
    from storage import get_latest
    
    news_items = get_latest(limit=limit)
    return analyze_news_for_companies(news_items)


def get_all_companies_from_db() -> List[Dict]:
    """
    Получает все компании из базы данных companies.
    """
    with get_connection() as conn:
        cursor = conn.execute(
            """
            SELECT name, source, rank, year, url, created_at
            FROM companies
            ORDER BY name
            """
        )
        rows = cursor.fetchall()
    
    companies = []
    for name, source, rank, year, url, created_at in rows:
        companies.append({
            'name': name,
            'source': source,
            'rank': rank,
            'year': year,
            'url': url,
            'created_at': created_at
        })
    
    return companies


def find_news_by_company_name(company_name: str, limit: int = 50) -> List[Dict]:
    """
    Находит новости, связанные с конкретной компанией.
    """
    from storage import get_latest
    
    news_items = get_latest(limit=1000)  # Берем больше для поиска
    company_news = analyze_news_for_companies(news_items)
    
    return company_news.get(company_name, [])[:limit]