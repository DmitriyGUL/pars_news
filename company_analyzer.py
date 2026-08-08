from __future__ import annotations

import re
from typing import Dict, List, Tuple
from storage import get_connection
from models import NewsItem
from tagging import analyze_text


# Словарь алиасов компаний для поиска по именам.
#
# ВАЖНО: алиасы задаются ТОЛЬКО в нижнем регистре и без повторов.
# Поиск идёт по лоуркейс-тексту, поэтому регистровые варианты одного и того же
# слова ("Газпром" / "ГАЗПРОМ" / "газпром") давали бы кратное завышение
# счётчика упоминаний.
COMPANY_ALIASES: Dict[str, List[str]] = {
    # ------------------------------------------------------------------
    # Обязательный список отслеживаемых компаний
    # ------------------------------------------------------------------
    "2GIS": ["2gis", "2гис", "дубльгис", "дубль гис"],
    "Холдинг Т1": ["холдинг т1", "т1 холдинг", "группа т1", "t1 холдинг", "t1 group"],
    "AliExpress Россия": ["aliexpress", "алиэкспресс", "али экспресс"],
    "Контур": ["скб контур", "skb kontur", "kontur", "контур"],
    "Билайн": ["билайн", "beeline"],
    "Лемана Про": ["лемана про", "лемана", "леруа мерлен", "leroy merlin"],
    "Bell Integrator": ["bell integrator", "белл интегратор"],
    "Магнит": ["магнит", "magnit"],
    "Промсвязьбанк": ["промсвязьбанк", "promsvyazbank", "псб"],
    "Самокат": ["самокат"],
    "Авито": ["авито", "avito"],
    "EPAM": ["epam", "эпам"],
    "Спортмастер": ["спортмастер", "sportmaster"],
    "HeadHunter Group": ["headhunter", "хедхантер", "хэдхантер", "hh.ru", "хх.ру"],
    "Лига Цифровой Экономики": ["лига цифровой экономики"],
    "Huawei": ["huawei", "хуавэй", "хуавей"],
    "ВТБ": ["втб", "vtb"],
    "Гринатом": ["гринатом", "greenatom"],
    "Газпромбанк": ["газпромбанк", "gazprombank"],
    "Дом.РФ": ["дом.рф", "дом рф", "domrf", "дом. рф"],
    "Lamoda": ["lamoda", "ламода"],
    "iTechArt": ["itechart", "айтекарт"],
    "МТС": ["мтс", "mts"],
    "Лаборатория Касперского": [
        "лаборатория касперского", "kaspersky", "касперского", "касперский",
    ],
    "ЦИАН": ["циан", "cian"],
    "Naumen": ["naumen", "наумен"],
    "Netcracker": ["netcracker", "нэткрэкер"],
    "Nexign": ["nexign", "нэксайн", "петер-сервис", "петер сервис"],
    "Ozon": ["ozon", "озон"],
    "Группа Астра": ["группа астра", "astra linux", "астра линукс", "astralinux", "астра"],
    "МегаФон": ["мегафон", "megafon"],
    "Positive Technologies": [
        "positive technologies", "позитив текнолоджиз", "позитив технолоджиз",
        "группа позитив",
    ],
    "Совкомбанк": ["совкомбанк", "sovcombank"],
    "QIWI": ["qiwi", "киви"],
    "Яндекс": ["яндекс", "yandex"],
    "Rambler&Co": ["rambler", "рамблер"],
    "Сбер": ["сбер", "сбербанк", "sber", "sberbank"],
    "VK": ["vk", "вк", "вконтакте", "mail.ru", "mail ru", "mailru"],
    "X5 Group": ["x5", "x5 group", "x5 retail group", "пятерочка", "пятёрочка"],
    "Ренессанс Кредит": ["ренессанс кредит", "renaissance credit"],
    "YADRO": ["yadro", "ядро"],
    "Россельхозбанк": ["россельхозбанк", "рсхб"],
    "SimbirSoft": ["simbirsoft", "симбирсофт"],
    "Центр финансовых технологий": ["центр финансовых технологий", "цфт"],
    "Альфа-Банк": ["альфа-банк", "альфа банк", "alfabank", "alfa-bank"],
    "Ростелеком": ["ростелеком", "rostelecom"],
    "Wildberries": ["wildberries", "вайлдберриз", "вайлдберис", "рвб"],
    "Skyeng": ["skyeng", "скайэнг"],
    "Usetech": ["usetech", "юзтех"],
    "Самолет": ["самолет", "самолёт"],

    # ------------------------------------------------------------------
    # Российский бигтех и крупнейшие IT-работодатели
    # ------------------------------------------------------------------
    "Т-Банк": ["т-банк", "т банк", "тинькофф", "tinkoff", "t-bank"],
    "Т2": ["теле2", "tele2", "т2 мобайл"],
    "1С": ["1с", "фирма 1с"],
    "1С-Битрикс": ["1с-битрикс", "битрикс", "bitrix"],
    "Диасофт": ["диасофт", "diasoft"],
    "Arenadata": ["arenadata", "аренадата"],
    "Иннотех": ["иннотех", "innotech"],
    "СберТех": ["сбертех", "sbertech"],
    "IBS": ["ibs"],
    "ЛАНИТ": ["ланит", "lanit"],
    "КРОК": ["крок", "croc"],
    "Softline": ["softline", "софтлайн"],
    "ICL": ["icl", "icl техно"],
    "Тензор": ["тензор"],
    "Райффайзенбанк": ["райффайзенбанк", "райффайзен", "raiffeisen"],
    "Ростех": ["ростех", "rostec"],
    "Росатом": ["росатом", "rosatom"],
    "Роскосмос": ["роскосмос", "roscosmos"],

    # ------------------------------------------------------------------
    # Прочий крупный бизнес РФ (частые ньюсмейкеры)
    # ------------------------------------------------------------------
    "Газпром": ["газпром", "gazprom"],
    "Роснефть": ["роснефть", "rosneft"],
    "Лукойл": ["лукойл", "lukoil"],
    "Норильский никель": ["норильский никель", "norilsk nickel", "норникель", "nornickel"],
    "Северсталь": ["северсталь", "severstal"],
    "РЖД": ["ржд", "rzd", "российские железные дороги"],
    "Аэрофлот": ["аэрофлот", "aeroflot"],
    "Лента": ["лента", "lenta"],
    "АвтоВАЗ": ["автоваз", "avtovaz", "lada", "лада"],
    "КамАЗ": ["камаз", "kamaz"],
    "Группа ГАЗ": ["газ", "группа газ", "group gaz"],
}


# Компании из обязательного списка отслеживания. Остальные записи словаря —
# российский бигтех и прочие частые ньюсмейкеры, они дополняют выборку.
REQUIRED_COMPANIES = frozenset({
    "2GIS", "Холдинг Т1", "AliExpress Россия", "Контур", "Билайн", "Лемана Про",
    "Bell Integrator", "Магнит", "Промсвязьбанк", "Самокат", "Авито", "EPAM",
    "Спортмастер", "HeadHunter Group", "Лига Цифровой Экономики", "Huawei",
    "ВТБ", "Гринатом", "Газпромбанк", "Дом.РФ", "Lamoda", "iTechArt", "МТС",
    "Лаборатория Касперского", "ЦИАН", "Naumen", "Netcracker", "Nexign",
    "Ozon", "Группа Астра", "МегаФон", "Positive Technologies", "Совкомбанк",
    "QIWI", "Яндекс", "Rambler&Co", "Сбер", "VK", "X5 Group",
    "Ренессанс Кредит", "YADRO", "Россельхозбанк", "SimbirSoft",
    "Центр финансовых технологий", "Альфа-Банк", "Ростелеком", "Wildberries",
    "Skyeng", "Usetech", "Самолет",
})


# Алиасы, совпадающие с обычными словами русского языка ("лента публикаций",
# "цена на газ", "запуск ядра", "самолет вылетел"). Такие алиасы засчитываются
# только если подтверждён контекст организации — см. _accepted_matches().
AMBIGUOUS_ALIASES = frozenset({
    # общеупотребительные слова
    "газ", "лента", "магнит", "лада", "самокат", "самолет", "самолёт",
    "ядро", "киви", "контур", "астра", "тензор", "крок", "озон",
    # короткие аббревиатуры, легко дающие ложные срабатывания
    "псб", "вк", "ibs", "icl", "1с", "x5",
})

# Дополнительный признак организации для неоднозначных алиасов: если где-то в
# тексте есть отраслевое слово из этого набора, упоминание засчитывается даже
# без кавычек и слова-квалификатора рядом. Держим списки узкими, чтобы не
# приписывать компаниям чужие новости.
ALIAS_CONTEXT: Dict[str, Tuple[str, ...]] = {
    "самокат": ("доставк", "фудтех", "ритейл", "даркстор", "экспресс-доставк"),
    "самолет": ("застройщик", "девелопер", "недвижим", "жилищн", "жк "),
    "самолёт": ("застройщик", "девелопер", "недвижим", "жилищн", "жк "),
    "ядро": ("серверн", "процессор", "микроэлектроник", "оборудован", "вычислительн"),
    "киви": ("платеж", "банк", "кошел", "финтех"),
    "контур": ("эдо", "бухгалтер", "отчетност", "отчётност", "электронн подпис", "экстерн"),
    "астра": ("linux", "линукс", "ос ", "операционн", "импортозамещ", "софт"),
    "тензор": ("сбис", "эдо", "документооборот", "отчетност", "отчётност"),
    "крок": ("интегратор", "цод", "ит-инфраструктур", "it-инфраструктур"),
    "озон": ("маркетплейс", "ozon", "селлер", "e-commerce", "интернет-магазин"),
    "псб": ("банк", "кредит", "вклад", "финанс"),
    "вк": ("вконтакте", "соцсет", "vk ", "мессенджер", "max", "мax"),
    "ibs": ("интегратор", "ит-компан", "it-компан", "консалтинг"),
    "icl": ("техно", "ноутбук", "серверн", "оборудован", "казан"),
    "1с": ("erp", "учет", "учёт", "бухгалтер", "внедрен", "битрикс", "предприяти"),
    "x5": ("ритейл", "ретейл", "пятероч", "перекрест", "перекрёст", "чижик", "торгов"),
    "магнит": ("ритейл", "ретейл", "торгов", "магазин", "сеть"),
    "лента": ("ритейл", "ретейл", "гипермаркет", "торгов", "магазин"),
}

# Слова-квалификаторы, подтверждающие, что рядом стоит название организации.
_QUALIFIERS = frozenset({
    "пао", "оао", "зао", "ооо", "ао", "гк", "группа", "группы", "компания",
    "компании", "корпорация", "холдинг", "холдинга", "концерн", "сеть", "сети",
    "банк", "банка", "ритейлер", "ретейлер", "завод", "магазин", "магазины",
    "бренд", "сервис", "сервиса", "сервисе", "маркетплейс", "маркетплейса",
    "оператор", "оператора", "разработчик", "разработчика", "вендор",
    "платформа", "платформы", "застройщик", "застройщика", "девелопер",
    "интегратор", "интегратора", "фирма", "фирмы", "структура",
})

# Кавычки, которыми в новостях оборачивают названия компаний.
_QUOTES_OPEN = "«\"'“„‘"
_QUOTES_CLOSE = "»\"'”“’"


# Падежные окончания, которые допускаются в конце названия компании:
# «Яндекса», «Ростелекома», «в Яндексе». Без них терялось около трети
# упоминаний, и как раз кадровых — «топ-менеджер Яндекса перешёл в ...».
#
# Список фиксированный, а не «любые несколько букв»: иначе «Сбер» склеивался бы
# со «СберТехом», который в словаре отдельной компанией.
_CASE_ENDINGS = (
    "ами", "ами", "ах", "ам", "ов", "ом", "ой", "ей", "ем", "ые", "ый",
    "а", "у", "е", "ы", "и", "я", "ю", "о",
)

# Минимальная длина алиаса, которому разрешены окончания. Короткие («вк», «мтс»,
# «псб») — аббревиатуры: они не склоняются, а лишние буквы дали бы мусор.
_MIN_LENGTH_FOR_ENDINGS = 4


def _allows_case_endings(alias: str) -> bool:
    """Можно ли искать алиас вместе с падежным окончанием."""
    if len(alias) < _MIN_LENGTH_FOR_ENDINGS:
        return False
    if alias in AMBIGUOUS_ALIASES:
        # «лента», «магнит», «самолет» и так требуют подтверждения контекстом,
        # а с окончаниями («лентой», «магниты») ложных срабатываний стало бы
        # ещё больше.
        return False
    # Только кириллица: латинские названия в русском тексте не склоняются.
    return bool(re.fullmatch(r"[а-яё\s-]+", alias))


def _alias_pattern(alias: str) -> str:
    """Регулярное выражение для поиска алиаса по границам слов."""
    if not _allows_case_endings(alias):
        return r"\b" + re.escape(alias) + r"\b"

    endings = "|".join(sorted(set(_CASE_ENDINGS), key=len, reverse=True))
    return r"\b" + re.escape(alias) + r"(?:" + endings + r")?\b"


# Скомпилированные шаблоны всех алиасов. Алиасов около трёхсот, и внутренний
# кэш модуля re (512 записей) на такой нагрузке начинает вытеснять шаблоны —
# компилируем один раз при импорте.
_ALIAS_PATTERNS: Dict[str, re.Pattern] = {
    alias: re.compile(_alias_pattern(alias))
    for aliases in COMPANY_ALIASES.values()
    for alias in aliases
}


def _alias_regex(alias: str) -> re.Pattern:
    """Шаблон алиаса из кэша; неизвестные алиасы компилируются по требованию."""
    pattern = _ALIAS_PATTERNS.get(alias)
    if pattern is None:
        pattern = re.compile(_alias_pattern(alias))
        _ALIAS_PATTERNS[alias] = pattern
    return pattern


def _is_qualified_mention(text_lower: str, start: int, end: int) -> bool:
    """
    Проверяет, что вхождение неоднозначного алиаса действительно относится к
    компании: оно либо обёрнуто в кавычки, либо ему предшествует
    слово-квалификатор.
    """
    before = text_lower[start - 1] if start > 0 else ""
    after = text_lower[end] if end < len(text_lower) else ""
    if before in _QUOTES_OPEN and after in _QUOTES_CLOSE:
        return True

    # Слово-квалификатор в пределах двух слов слева
    prefix_words = re.findall(r"[\w.-]+", text_lower[:start])[-2:]
    return any(word in _QUALIFIERS for word in prefix_words)


def _has_industry_context(text_lower: str, alias: str) -> bool:
    """Есть ли в тексте отраслевое слово, подтверждающее компанию для алиаса."""
    return any(marker in text_lower for marker in ALIAS_CONTEXT.get(alias, ()))


def _accepted_matches(text_lower: str, alias: str) -> List[re.Match]:
    """
    Вхождения алиаса, которые засчитываются как упоминание компании.

    Однозначные алиасы засчитываются всегда. Неоднозначный — только если
    подтверждён контекст: отраслевое слово в тексте, кавычки вокруг названия
    или слово-квалификатор слева.
    """
    matches = list(_alias_regex(alias).finditer(text_lower))
    if not matches or alias not in AMBIGUOUS_ALIASES:
        return matches

    if _has_industry_context(text_lower, alias):
        return matches

    return [
        m for m in matches if _is_qualified_mention(text_lower, m.start(), m.end())
    ]


def _count_alias(text_lower: str, alias: str) -> int:
    """Считает вхождения одного алиаса с учётом его неоднозначности."""
    return len(_accepted_matches(text_lower, alias))


def _company_spans(text_lower: str, aliases: List[str]) -> List[Tuple[int, int]]:
    """
    Непересекающиеся вхождения компании в тексте, по позициям.

    Алиасы одной компании часто вложены друг в друга («лаборатория
    касперского» и «касперского», «группа газ» и «газ»), и простая сумма по
    алиасам давала кратное завышение счётчика. Из пересекающихся вхождений
    оставляем самое длинное — оно точнее называет компанию.
    """
    spans = [
        (match.start(), match.end())
        for alias in aliases
        for match in _accepted_matches(text_lower, alias)
    ]
    # Длинные вперёд, при равной длине — левые: жадный выбор тогда даёт
    # максимально конкретные совпадения.
    spans.sort(key=lambda span: (span[0] - span[1], span[0]))

    accepted: List[Tuple[int, int]] = []
    for start, end in spans:
        if any(start < taken_end and end > taken_start for taken_start, taken_end in accepted):
            continue
        accepted.append((start, end))

    accepted.sort()
    return accepted


def detect_companies_in_text(text: str) -> List[Tuple[str, int]]:
    """
    Обнаруживает упоминания компаний в тексте.
    Возвращает список кортежей (имя_компании, количество_упоминаний).
    """
    if not text:
        return []

    text_lower = text.lower()
    detected = {}

    for company_name, aliases in COMPANY_ALIASES.items():
        total_count = len(_company_spans(text_lower, aliases))

        if total_count > 0:
            detected[company_name] = total_count

    # Сортируем по количеству упоминаний (по убыванию)
    return sorted(detected.items(), key=lambda x: x[1], reverse=True)


def _analyze_news_items(news_items: List[NewsItem]) -> Tuple[List[Dict], Dict[str, List[Dict]]]:
    """
    Один проход по новостям: плоские строки для выгрузки и группировка по компаниям.

    Распознавание компаний — самая дорогая часть анализа (сотни регулярок на
    новость), поэтому обе структуры собираются за один проход, а не двумя
    независимыми вызовами detect_companies_in_text.
    """
    rows: List[Dict] = []
    company_news: Dict[str, List[Dict]] = {}

    for news in news_items:
        # Анализируем заголовок и описание (если есть)
        text_to_analyze = news.title
        if news.summary:
            text_to_analyze += " " + news.summary

        companies_found = detect_companies_in_text(text_to_analyze)
        published_at = news.published_at.isoformat() if news.published_at else None

        analysis = analyze_text(text_to_analyze, news.source)
        tags_str = ", ".join(analysis.tags)
        signal = analysis.signal

        rows.append({
            'title': news.title,
            'url': news.url,
            'source': news.source,
            'published_at': published_at,
            'summary': news.summary,
            'companies': ", ".join(name for name, _ in companies_found),
            'companies_count': len(companies_found),
            'material_type': analysis.material_type,
            'tags': tags_str,
            'hr_signal': signal.level,
            'hr_reason': signal.reason,
        })

        for company_name, count in companies_found:
            company_news.setdefault(company_name, []).append({
                'title': news.title,
                'url': news.url,
                'source': news.source,
                'published_at': published_at,
                'summary': news.summary,
                'mention_count': count,
                'text_snippet': _extract_snippet_with_company(text_to_analyze, company_name),
                'material_type': analysis.material_type,
                'tags': tags_str,
                'hr_signal': signal.level,
                'hr_reason': signal.reason,
            })

    return rows, company_news


def analyze_news_for_companies(news_items: List[NewsItem]) -> Dict[str, List[Dict]]:
    """
    Анализирует список новостей и возвращает словарь с компаниями и связанными новостями.
    Формат: {company_name: [news_data_dict, ...]}
    """
    return _analyze_news_items(news_items)[1]


def _extract_snippet_with_company(text: str, company_name: str, snippet_length: int = 100) -> str:
    """
    Извлекает сниппет текста с упоминанием компании.

    Использует те же правила поиска, что и detect_companies_in_text, поэтому
    для любой обнаруженной компании гарантированно возвращает непустую строку.
    """
    text_lower = text.lower()
    company_aliases = COMPANY_ALIASES.get(company_name, [company_name.lower()])

    for start, end in _company_spans(text_lower, company_aliases):
        # Вычисляем границы для сниппета
        snippet_start = max(0, start - snippet_length // 2)
        snippet_end = min(len(text), end + snippet_length // 2)

        snippet = text[snippet_start:snippet_end]

        # Добавляем многоточие если текст обрезан
        if snippet_start > 0:
            snippet = "..." + snippet
        if snippet_end < len(text):
            snippet = snippet + "..."

        return snippet

    return ""


def news_items_to_rows(news_items: List[NewsItem]) -> List[Dict]:
    """
    Приводит исходные новости к плоским словарям для выгрузки «как есть».

    Поле `companies` показывает, какие компании распознал анализатор, — по нему
    видно и то, что попало в фильтр, и то, что не попало ни в одну компанию.
    """
    return _analyze_news_items(news_items)[0]


def get_news_with_companies_from_db(limit: int = 1000) -> Dict[str, List[Dict]]:
    """
    Получает новости из базы данных и анализирует их на предмет упоминаний компаний.
    """
    from storage import get_latest

    news_items = get_latest(limit=limit)
    return analyze_news_for_companies(news_items)


def get_news_and_companies_from_db(
    limit: int = 1000,
    start_date=None,
    end_date=None,
) -> Tuple[List[Dict], Dict[str, List[Dict]]]:
    """
    Читает новости из БД один раз и возвращает пару:
    (все собранные новости, новости сгруппированные по компаниям).

    Если заданы обе границы периода, берутся новости за него — иначе последние
    `limit` записей. Отчёт за неделю иначе смешивался бы со старыми записями:
    выборка по «последним N» о датах ничего не знает.
    """
    from storage import get_latest, get_news_by_date_range

    if start_date and end_date:
        news_items = get_news_by_date_range(start_date, end_date)[:limit]
    else:
        news_items = get_latest(limit=limit)

    return _analyze_news_items(news_items)


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


def get_reference_companies() -> List[Dict]:
    """
    Справочный список компаний, которые умеет распознавать анализатор.

    Используется, когда таблица companies пуста: иначе лист «Компании» в Excel
    оставался бы с одной лишь шапкой.
    """
    return [
        {
            'name': name,
            'source': 'обязательная' if name in REQUIRED_COMPANIES else 'reference',
            'rank': None,
            'year': None,
            'url': None,
            'created_at': None,
        }
        for name in sorted(COMPANY_ALIASES)
    ]


def seed_reference_companies() -> int:
    """
    Записывает справочный список компаний в таблицу companies.
    Возвращает количество добавленных записей.

    Ранее засеянные справочные записи удаляются: иначе в таблице навсегда
    оставались бы компании, убранные из словаря (например, иностранные).
    Записи из парсеров (source = forbes/rbc/...) не трогаем.
    """
    from models import Company
    from storage import save_companies

    reference = get_reference_companies()

    with get_connection() as conn:
        conn.execute(
            "DELETE FROM companies WHERE source IN ('reference', 'обязательная')"
        )
        conn.commit()

    companies = [
        Company(name=item['name'], source=item['source']) for item in reference
    ]
    return save_companies(companies)


def find_news_by_company_name(
    company_name: str, limit: int = 50, scan_limit: int = 10000
) -> List[Dict]:
    """
    Находит новости, связанные с конкретной компанией.

    `limit` ограничивает выдачу, `scan_limit` — сколько последних новостей
    просматривается. Раньше просмотр был жёстко ограничен тысячей записей, и на
    базе большего размера старые новости не находились вообще.
    """
    from storage import get_latest

    news_items = get_latest(limit=max(limit, scan_limit))
    company_news = analyze_news_for_companies(news_items)

    return company_news.get(company_name, [])[:limit]