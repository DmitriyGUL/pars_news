from __future__ import annotations

from typing import List, Optional
from pathlib import Path

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

from models import Company
from storage import init_db, save_companies


RATING_URL = (
    "https://www.forbes.ru/biznes/521880-100-krupnejsih-kompanij-rossii-po-cistoj-"
    "pribyli-2024-rejting-forbes"
)


def collect_companies(page) -> List[Company]:
    companies: List[Company] = []

    # Селектор ниже рассчитан на карточки рейтинга; при необходимости его можно
    # подправить под актуальную верстку.
    items = page.locator("[data-testid='rating-item'], article, li")
    count = items.count()

    for i in range(count):
        item = items.nth(i)

        # Пытаемся найти ранг как число в начале текста карточки.
        rank: Optional[int] = None
        try:
            text = (item.inner_text() or "").strip()
        except Exception:
            text = ""
        if text:
            parts = text.split()
            if parts and parts[0].isdigit():
                try:
                    rank = int(parts[0])
                except ValueError:
                    rank = None

        # Название компании предполагаем в первой ссылке или заголовке внутри карточки.
        name_loc = item.locator("a, h2, h3, span").first
        try:
            name_text = (name_loc.text_content() or "").strip()
        except Exception:
            name_text = ""

        if not name_text:
            continue

        url: Optional[str] = None
        try:
            tag_name = name_loc.evaluate("el => el.tagName.toLowerCase()")
        except Exception:
            tag_name = ""

        if tag_name == "a":
            href = name_loc.get_attribute("href")
            if href:
                if href.startswith("http"):
                    url = href
                else:
                    url = "https://www.forbes.ru" + href

        companies.append(
            Company(
                name=name_text,
                source="forbes_100_profit_2024",
                rank=rank,
                year=2024,
                url=url,
            )
        )

    return companies


def main() -> None:
    init_db()

    project_root = Path(__file__).resolve().parent
    snapshot_path = project_root / "forbes_100_snapshot.html"

    with sync_playwright() as p:
        # Открываем браузер в обычном (не headless) режиме, чтобы вы могли вручную
        # решить капчу Яндекса, если она появится.
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        page.goto(RATING_URL)

        # Если попали на страницу "Вы не робот?", просим вас вручную пройти капчу.
        try:
            title = page.title()
        except Exception:
            title = ""
        if "Вы не робот" in title or "SmartCaptcha" in title:
            print(
                "Открылось окно с проверкой 'Вы не робот?'. "
                "Пожалуйста, пройдите капчу в браузере, "
                "дождитесь загрузки страницы рейтинга Forbes, "
                "после чего вернитесь в терминал и нажмите Enter."
            )
            input("Нажмите Enter, когда страница рейтинга будет полностью загружена...")

        # Кликаем «Показать еще» несколько раз, пока кнопка присутствует.
        # Ограничиваем количество кликов, чтобы не зациклиться.
        max_clicks = 10
        for _ in range(max_clicks):
            try:
                button = page.get_by_text("Показать еще", exact=False)
                if not button.is_visible():
                    break
                button.click()
                # Небольшая пауза на подгрузку новых элементов.
                page.wait_for_timeout(1500)
            except PlaywrightTimeoutError:
                break
            except Exception:
                break

        # Сохраняем финальное состояние страницы в HTML, чтобы можно было
        # детально посмотреть разметку и донастроить парсер при необходимости.
        try:
            html = page.content()
            snapshot_path.write_text(html, encoding="utf-8")
            print(f"Снимок страницы сохранен в {snapshot_path}")
        except Exception:
            pass

        companies = collect_companies(page)
        browser.close()

    inserted = save_companies(companies)
    print(f"Сохранено компаний в таблицу companies: {inserted}")


if __name__ == "__main__":
    main()

