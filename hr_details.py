"""
Разбор кадровых событий: кто, откуда, куда и в каком объёме.

Работает поверх материалов с кадровым сигналом. Обычная разметка (tagging.py)
отвечает на вопрос «о чём новость», а этот модуль вытаскивает из текста
конкретику, ради которой новость и читают:

* персоны и их должности («Гендиректором назначен Иван Петров»);
* организации, включая те, которых нет в словаре отслеживаемых компаний, —
  в кадровых новостях сплошь и рядом фигурируют «ВкусВилл», «ГК ЭнергоПроф»
  и прочие, и терять их нельзя;
* масштаб («сократит 200 сотрудников», «штат вырос на 15%»);
* ключевые фрагменты — предложения, из-за которых материал попал в выборку.

Всё на правилах: морфологических словарей и сетевых вызовов нет. Полнота на
живых текстах — около трёх четвертей; остальное съедают падежи и редкие
конструкции. Для отчёта, который читает человек, этого достаточно: рядом
всегда лежит исходный текст с подсветкой.
"""

from __future__ import annotations

import re
from typing import Dict, List, NamedTuple, Optional, Sequence, Tuple

from tagging import TAG_MARKERS, _MARKER_PATTERNS, _marker_hits


# --------------------------------------------------------------------------
# Персоны
# --------------------------------------------------------------------------

# Заглавная кириллическая буква и продолжение слова.
_CAP = r"[А-ЯЁ][а-яё]+"

# «Иван Петров» и «Иван Петрович Сидоров» — имя впереди.
NAME_FIRST = re.compile(rf"\b({_CAP})\s+({_CAP}(?:ов|ев|ин|ын|ский|цкий|ко|ук|юк|ян|дзе)\w*)\b")

# «Петров Иван» и «Петров Иван Иванович» — фамилия впереди.
NAME_LAST = re.compile(rf"\b({_CAP}(?:ов|ев|ин|ын|ский|цкий)\w*)\s+({_CAP})\b")

# «И. Петров», «И.И. Петров»
NAME_INITIALS = re.compile(rf"\b([А-ЯЁ]\.\s?(?:[А-ЯЁ]\.\s?)?)({_CAP}\w*)\b")

# Слова с большой буквы, которые ловятся шаблонами имён, но людьми не являются.
NOT_A_PERSON = frozenset({
    # география
    "россии", "россия", "москве", "москвы", "москва", "санкт", "петербурге",
    "рф", "украины", "украина", "мексике", "сша", "китая", "европы",
    # организации и должности
    "компании", "компания", "группы", "группа", "холдинга", "банка", "банк",
    "сети", "директор", "директора", "руководство", "правительство",
    "министерство", "ведомство", "агентство", "корпорация",
    "генеральный", "исполнительный", "коммерческий", "финансовый",
    # календарь
    "январь", "февраль", "март", "апрель", "май", "июнь", "июль", "август",
    "сентябрь", "октябрь", "ноябрь", "декабрь",
})


class Person(NamedTuple):
    """Человек, упомянутый в кадровом событии."""

    name: str
    position: str = ""


# --------------------------------------------------------------------------
# Должности
# --------------------------------------------------------------------------

POSITION_MARKERS = (
    "генеральный директор", "генеральным директором", "гендиректор",
    "гендиректором", "исполнительный директор", "исполнительным директором",
    "финансовый директор", "финансовым директором", "коммерческий директор",
    "коммерческим директором", "технический директор", "техническим директором",
    "операционный директор", "hr-директор", "директор по персоналу",
    "директором по персоналу", "директор по развитию", "директор по маркетингу",
    "директор по продажам", "ит-директор", "директор департамента",
    "директор", "директором",
    "председатель правления", "председателем правления", "председатель совета директоров",
    "член совета директоров", "вице-президент", "вице-президентом",
    "первый заместитель", "заместитель генерального", "замгендиректора",
    "руководитель направления", "руководитель департамента", "руководитель отдела",
    "руководитель", "руководителем", "глава", "главой", "начальник отдела",
    "управляющий директор", "ceo", "cto", "cfo", "coo", "hrd",
    "топ-менеджер", "топ-менеджером", "партнёр", "партнер",
)

_POSITION_PATTERNS = {
    marker: re.compile(r"\b" + re.escape(marker) + r"\w*", re.IGNORECASE)
    for marker in POSITION_MARKERS
}

# Должность в тексте почти всегда стоит в творительном падеже («назначен
# генеральным директором»), а в отчёте нужна начальная форма — иначе одна и
# та же должность выглядит как несколько разных.
POSITION_CANONICAL = {
    "генеральным директором": "генеральный директор",
    "гендиректором": "генеральный директор",
    "гендиректор": "генеральный директор",
    "исполнительным директором": "исполнительный директор",
    "финансовым директором": "финансовый директор",
    "коммерческим директором": "коммерческий директор",
    "техническим директором": "технический директор",
    "директором по персоналу": "директор по персоналу",
    "председателем правления": "председатель правления",
    "вице-президентом": "вице-президент",
    "руководителем": "руководитель",
    "директором": "директор",
    "главой": "глава",
    "топ-менеджером": "топ-менеджер",
    "партнером": "партнёр",
}

# Сколько символов вокруг имени просматривать в поисках должности.
POSITION_WINDOW = 120


# --------------------------------------------------------------------------
# Организации
# --------------------------------------------------------------------------

# Организационно-правовая форма с названием: ООО «Ромашка», АО "Вектор".
LEGAL_ENTITY = re.compile(
    r"\b(?:ООО|ОАО|ЗАО|ПАО|АО|ГК|НКО|АНО)\s+[«\"']([^»\"']{2,60})[»\"']"
)

# Название в кавычках рядом со словом-квалификатором: сеть «ВкусВилл».
QUOTED_ORG = re.compile(
    r"(?:компани\w*|холдинг\w*|группа\w*|группы|сет[ьи]|банк\w*|ритейлер\w*|"
    r"оператор\w*|сервис\w*|маркетплейс\w*|платформ\w*|застройщик\w*|"
    r"разработчик\w*|интегратор\w*|производител\w*)\s+[«\"']([^»\"']{2,60})[»\"']",
    re.IGNORECASE,
)

# Название в кавычках без квалификатора — слабый признак: в кавычки берут и
# цитаты, и заголовки («Инвалиды нам не нужны»). Поэтому требуем, чтобы внутри
# было не больше трёх слов и не встречалось знаков препинания предложения.
BARE_QUOTED = re.compile(r"[«]([А-ЯЁA-Z][^»]{2,40})[»]")
BARE_QUOTED_MAX_WORDS = 3
SENTENCE_PUNCT = re.compile(r"[,.;:!?]")

# Слова, с которых название начинаться не может, — признак цитаты или заголовка.
_NOT_ORG_START = frozenset({
    "инвалиды", "рост", "работа", "применяет", "почему", "как", "что", "это",
    "мы", "они", "все", "наш", "наши", "если", "когда", "зачем", "кто",
})


# --------------------------------------------------------------------------
# Масштаб события
# --------------------------------------------------------------------------

# «сократит 200 сотрудников», «уволили 1,5 тыс. человек»
HEADCOUNT = re.compile(
    r"(\d[\d\s.,]*)\s*(тыс\.?|тысяч\w*|млн|миллион\w*)?\s*"
    r"(сотрудник\w*|работник\w*|человек\w*|специалист\w*|ваканси\w*|мест)",
    re.IGNORECASE,
)

# «на 15%», «до 30 процентов»
PERCENT = re.compile(r"(?:на|до|более чем на)\s+(\d[\d.,]*)\s*(?:%|процент\w*)", re.IGNORECASE)

# Деньги — контекст масштаба события
MONEY = re.compile(
    r"(\d[\d\s.,]*)\s*(млрд|миллиард\w*|млн|миллион\w*|тыс\.?|тысяч\w*)?\s*"
    r"(руб\w*|₽|долл\w*|\$|евро)",
    re.IGNORECASE,
)


class HrDetails(NamedTuple):
    """Извлечённая конкретика кадрового события."""

    persons: List[Person]
    organizations: List[str]
    headcount: List[str]
    percents: List[str]
    money: List[str]
    key_sentences: List[str]

    @property
    def is_empty(self) -> bool:
        return not (self.persons or self.organizations or self.headcount
                    or self.percents or self.key_sentences)


# Окончания прилагательных: «Великая Законодательница», «Московский завод» —
# это не имена, а определения с большой буквы.
_ADJECTIVE_ENDINGS = ("ая", "ое", "ые", "ый", "ий", "ой", "юю", "ую")


def _looks_like_person(first: str, second: str) -> bool:
    """Отсекает пары слов с большой буквы, которые именем не являются."""
    if len(first) <= 2 or len(second) <= 2:
        return False
    if first.lower() in NOT_A_PERSON or second.lower() in NOT_A_PERSON:
        return False
    # Прилагательное на месте имени — верный признак, что это не человек.
    # Фамилии на -ий/-ый (Горский, Белый) отсекать нельзя, поэтому проверяем
    # только первое слово: имя прилагательным не бывает.
    return not first.lower().endswith(_ADJECTIVE_ENDINGS)


def extract_persons(text: str) -> List[Person]:
    """
    Имена людей и их должности.

    Должность ищется рядом с именем — в пределах POSITION_WINDOW символов:
    в кадровых новостях они почти всегда стоят в одном предложении.
    """
    if not text:
        return []

    found: Dict[str, Person] = {}

    for pattern in (NAME_FIRST, NAME_LAST, NAME_INITIALS):
        for match in pattern.finditer(text):
            first, second = match.group(1).strip(), match.group(2).strip()
            if pattern is not NAME_INITIALS and not _looks_like_person(first, second):
                continue

            name = f"{first} {second}".strip()
            # Ключ по началу слов: «Михаил Федоров», «Михаилом Федоровым» и
            # «Михаилу Федорову» — один человек, и в отчёте он должен быть
            # одной строкой.
            key = _person_key(name)

            previous = found.get(key)
            position = _position_near(text, match.start(), match.end())

            if previous is None:
                found[key] = Person(name=name, position=position)
                continue

            # Из падежных вариантов оставляем самый короткий — обычно это
            # именительный. Должность берём ту, что вообще нашлась.
            best_name = min(previous.name, name, key=len)
            found[key] = Person(name=best_name, position=previous.position or position)

    return list(found.values())


# Сколько первых букв слова участвуют в ключе. Меньше — начнут сливаться
# разные фамилии, больше — перестанут склеиваться падежные формы.
_PERSON_KEY_PREFIX = 5


def _person_key(name: str) -> str:
    """Ключ, общий у падежных форм одного имени."""
    return " ".join(word[:_PERSON_KEY_PREFIX].lower() for word in name.split())


def _position_near(text: str, start: int, end: int) -> str:
    """Должность, упомянутая рядом с именем. Возвращает самую конкретную."""
    window = text[max(0, start - POSITION_WINDOW):end + POSITION_WINDOW].lower()

    # Маркеры перечислены от частных к общим, поэтому первое совпадение —
    # самое конкретное: «финансовый директор» важнее, чем просто «директор».
    for marker in POSITION_MARKERS:
        if _POSITION_PATTERNS[marker].search(window):
            return POSITION_CANONICAL.get(marker, marker)

    return ""


def extract_organizations(text: str) -> List[str]:
    """
    Организации из текста, включая отсутствующие в словаре компаний.

    Кадровые новости часто про компании вне списка отслеживания («ВкусВилл»,
    «ГК ЭнергоПроф»), и без этого они терялись бы целиком.
    """
    if not text:
        return []

    names: List[str] = []
    seen = set()

    for pattern in (LEGAL_ENTITY, QUOTED_ORG, BARE_QUOTED):
        for match in pattern.finditer(text):
            name = match.group(1).strip()
            key = name.lower()
            if key in seen or len(key) < 3:
                continue

            if pattern is BARE_QUOTED and not _looks_like_org_name(name):
                continue

            seen.add(key)
            names.append(name)

    return _dedupe_by_case(names)


def _looks_like_org_name(name: str) -> bool:
    """
    Похоже ли содержимое кавычек на название, а не на цитату.

    В кавычки берут и прямую речь, и заголовки материалов, поэтому без этой
    проверки в организации попадали «Инвалиды нам не нужны» и «Рост прибыли».
    """
    if SENTENCE_PUNCT.search(name):
        return False
    words = name.split()
    if len(words) > BARE_QUOTED_MAX_WORDS:
        return False
    # Название не начинается с глагола или служебного слова.
    return words[0].lower() not in _NOT_ORG_START


def _case_key(name: str) -> str:
    """
    Ключ, одинаковый у падежных форм названия: «Цифра», «Цифре», «Цифру».

    Отбрасываем последнюю гласную — этого хватает, чтобы склеить формы одного
    названия и при этом не слить разные («Квант» и «Квота» останутся разными).
    """
    key = name.lower().strip()
    if len(key) > 4 and key[-1] in "аеёиоуыэюя":
        key = key[:-1]
    return key


def _dedupe_by_case(names: Sequence[str]) -> List[str]:
    """
    Схлопывает падежные варианты, оставляя самый частый.

    В статье одна и та же компания склоняется по всему тексту, и без этого
    в отчёт попадало «Цифра, Цифре, Цифры, Цифру» вместо одной строки.
    """
    groups: Dict[str, List[str]] = {}
    for name in names:
        groups.setdefault(_case_key(name), []).append(name)

    result = []
    for variants in groups.values():
        # Самый частый вариант, при равенстве — первый встреченный.
        best = max(set(variants), key=lambda v: (variants.count(v), -variants.index(v)))
        result.append(best)
    return result


def _find_all(pattern: re.Pattern, text: str, limit: int = 5) -> List[str]:
    """Совпадения шаблона целиком, без повторов."""
    values: List[str] = []
    seen = set()
    for match in pattern.finditer(text or ""):
        value = " ".join(match.group(0).split())
        key = value.lower()
        if key in seen:
            continue
        seen.add(key)
        values.append(value)
        if len(values) >= limit:
            break
    return values


def extract_key_sentences(text: str, tags: Sequence[str], limit: int = 4) -> List[str]:
    """
    Предложения, из-за которых материал попал в кадровую выборку.

    Берутся те, где сработали маркеры темы: именно их человек и хочет увидеть,
    открыв отчёт, — остальной текст нужен лишь для проверки.
    """
    if not text:
        return []

    sentences = re.split(r"(?<=[.!?])\s+|\n", text)
    markers = [m for tag in tags for m in TAG_MARKERS.get(tag, ())]

    picked: List[str] = []
    for sentence in sentences:
        clean = " ".join(sentence.split())
        if len(clean) < 30:
            continue
        lowered = clean.lower()
        if any(_marker_hits(lowered, marker) for marker in markers):
            picked.append(clean)
            if len(picked) >= limit:
                break

    return picked


def extract_details(text: str, tags: Sequence[str] = ()) -> HrDetails:
    """Полный разбор одного материала."""
    text = text or ""
    return HrDetails(
        persons=extract_persons(text),
        organizations=extract_organizations(text),
        headcount=_find_all(HEADCOUNT, text),
        percents=_find_all(PERCENT, text),
        money=_find_all(MONEY, text),
        key_sentences=extract_key_sentences(text, tags),
    )


def highlight_spans(text: str, tags: Sequence[str] = ()) -> List[Tuple[int, int]]:
    """
    Отрезки текста, которые стоит подсветить в отчёте: маркеры тем, числа и
    упоминания людей. Пересекающиеся отрезки объединяются, чтобы разметка
    не рвала слова.
    """
    if not text:
        return []

    lowered = text.lower()
    spans: List[Tuple[int, int]] = []

    markers = [m for tag in tags for m in TAG_MARKERS.get(tag, ())]
    for marker in markers:
        pattern = _MARKER_PATTERNS.get(marker)
        if pattern is None:
            continue
        for match in pattern.finditer(lowered):
            # Подсвечиваем слово целиком, а не только основу.
            end = match.end()
            while end < len(text) and text[end].isalpha():
                end += 1
            spans.append((match.start(), end))

    for pattern in (HEADCOUNT, PERCENT, MONEY, NAME_FIRST, NAME_LAST):
        for match in pattern.finditer(text):
            spans.append((match.start(), match.end()))

    if not spans:
        return []

    spans.sort()
    merged = [spans[0]]
    for start, end in spans[1:]:
        last_start, last_end = merged[-1]
        if start <= last_end:
            merged[-1] = (last_start, max(last_end, end))
        else:
            merged.append((start, end))

    return merged
