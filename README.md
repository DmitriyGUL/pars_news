## pars_news

Локальный агрегатор новостей компаний и маркетинга на Python.

### Стек

- Python 3.10+
- Парсинг: `requests` + `beautifulsoup4`
- Хранение: SQLite (`sqlite3`)

### Структура

- `main.py` — запуск всех парсеров и сохранение новостей.
- `models.py` — модель новости.
- `storage.py` — работа с базой данных SQLite.
- `sources/` — парсеры под конкретные сайты.

### Установка

```bash
pip install -r requirements.txt
```

### Запуск

```bash
python main.py
```

