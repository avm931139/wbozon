"""
Модуль нормализации товаров для Wildberries
ЭТАП 1: Сопоставление групп сайта с категориями WB
"""

import re
import json
import os
from typing import Optional, List, Tuple
from sqlalchemy.orm import Session

from core.db.connection import get_db_session
from core.db.models import (
    ParserProduct,
    WBSubject,
    WBSubjectMapping,
)


class WBNormalizer:
    """Нормализует спарсенные товары для загрузки на WB"""

    # Словарь: категория WB -> ключевые слова для поиска
    KEYWORDS_FOR_CATEGORY = {
        'Люстры': ['Потолочная', 'Подвесной', 'люстра'],
        'Светильники': ['Светильники', 'Настольная лампа', 'Панно', 'Накладной', 'Бра', 'Настенный', 'Торшер'],
    }

    def __init__(self, db: Session):
        self.db = db
        self._load_keywords_from_file()

    def _get_all_wb_categories(self) -> List[WBSubject]:
        """Получает все категории WB (только предметы, не родительские)"""
        return self.db.query(WBSubject).filter(
            WBSubject.parent_id.isnot(None)
        ).order_by(WBSubject.subject_name).all()

    def _find_matching_category(self, site_group: str, product_name: str = None) -> Optional[WBSubject]:
        """
        Ищет подходящую категорию WB по ключевым словам
        Возвращает объект WBSubject или None
        """
        search_text = site_group.lower()
        if product_name:
            search_text += " " + product_name.lower()

        # Перебираем все категории с их ключевыми словами
        for category_name, keywords in self.KEYWORDS_FOR_CATEGORY.items():
            for keyword in keywords:
                if keyword.lower() in search_text:
                    subject = self.db.query(WBSubject).filter(
                        WBSubject.subject_name == category_name
                    ).first()
                    if subject:
                        return subject

        return None

    def sync_groups_mapping(self):
        """
        Сопоставляет все уникальные groupe_site с категориями WB
        """
        # Получаем все уникальные пары (domain, groupe_site) из parser_product
        products = self.db.query(ParserProduct).all()

        # Собираем уникальные пары
        unique_groups = {}
        for product in products:
            domain = self._extract_domain(product.url)
            if domain and product.groupe_site:
                key = (domain, product.groupe_site)
                if key not in unique_groups:
                    unique_groups[key] = {
                        'domain': domain,
                        'site_group': product.groupe_site,
                        'example_name': product.name_site,
                        'example_code': product.code_ms
                    }

        # Фильтруем те, у которых нет сопоставления
        unmapped = []
        for key, group_info in unique_groups.items():
            mapping = self.db.query(WBSubjectMapping).filter(
                WBSubjectMapping.domain == group_info['domain'],
                WBSubjectMapping.site_group == group_info['site_group']
            ).first()

            if not mapping:
                unmapped.append(group_info)

        if not unmapped:
            print("✅ Все группы уже сопоставлены с категориями WB")
            return

        print(f"\n{'=' * 70}")
        print(f"ЭТАП 1: СОПОСТАВЛЕНИЕ ГРУПП САЙТА С КАТЕГОРИЯМИ WB")
        print(f"{'=' * 70}")
        print(f"\n📊 Найдено {len(unmapped)} групп без сопоставления:\n")

        for idx, group in enumerate(unmapped, 1):
            print(f"{idx}. Домен: {group['domain']}")
            print(f"   Группа: {group['site_group']}")
            print(f"   Пример: {group['example_name'][:80]}...")
            print()

        print("=" * 70)
        proceed = input("Начать сопоставление групп? (Enter - да, n - пропустить): ").strip().lower()

        if proceed == 'n':
            print("⚠️ Сопоставление групп пропущено")
            return

        # Сопоставляем каждую группу
        for group in unmapped:
            self._map_single_group(
                group['domain'],
                group['site_group'],
                group['example_name'],
                group['example_code']
            )

    def _map_single_group(self, domain: str, site_group: str, example_name: str = None, example_code: str = None):
        """Сопоставляет одну группу сайта с категорией WB"""
        print(f"\n{'=' * 70}")
        print(f"📌 СОПОСТАВЛЕНИЕ ГРУППЫ:")
        print(f"   Код МС: {example_code if example_code else '-'}")
        print(f"   Домен: {domain}")
        print(f"   Группа сайта: {site_group}")
        if example_name:
            print(f"   Название: {example_name[:100]}")
        print(f"{'=' * 70}")

        # АВТОПОИСК
        auto_match = self._find_matching_category(site_group, example_name)

        if auto_match:
            print(f"\n🔍 АВТОПОИСК: найдена категория:")
            print(f"   {auto_match.subject_name} (ID: {auto_match.subject_id})")

            auto_choice = input("\n   Использовать эту категорию? (Enter - да, n - выбрать другую): ").strip().lower()
            if auto_choice != 'n':
                self._save_mapping(domain, site_group, auto_match.subject_id, auto_match.subject_name)
                return

            # Если пользователь выбрал другую, переходим к ручному выбору
            self._manual_group_selection(domain, site_group, example_name)
        else:
            # Если автопоиск не нашел
            print(f"\n⚠️ АВТОПОИСК: не найдено подходящей категории для '{site_group}'")
            print(f"   Нужно выбрать категорию вручную и добавить ключевое слово")

            self._manual_group_selection(domain, site_group, example_name, prompt_add_keyword=True)

    def _manual_group_selection(self, domain: str, site_group: str, example_name: str = None, prompt_add_keyword: bool = False):
        """Ручной выбор категории WB из всех загруженных"""

        all_subjects = self._get_all_wb_categories()

        if not all_subjects:
            print("⚠️ Нет загруженных категорий WB. Сначала загрузите категории через WB API.")
            return

        print(f"\n📂 ВСЕ КАТЕГОРИИ WILDBERRIES (всего {len(all_subjects)}):")

        # Пагинация
        page_size = 20
        current_page = 0
        total_pages = (len(all_subjects) + page_size - 1) // page_size

        selected_subject = None

        while selected_subject is None:
            start = current_page * page_size
            end = min(start + page_size, len(all_subjects))

            print(f"\n   Страница {current_page + 1}/{total_pages}:")
            for i, subj in enumerate(all_subjects[start:end], start + 1):
                parent = self.db.query(WBSubject).filter(
                    WBSubject.subject_id == subj.parent_id
                ).first()
                parent_name = parent.subject_name if parent else "Без родителя"
                print(f"     {i}. {parent_name} → {subj.subject_name} (ID: {subj.subject_id})")

            print(f"\n   Команды:")
            print(f"     n - следующая страница")
            print(f"     p - предыдущая страница")
            print(f"     s - поиск по названию")
            print(f"     0 - пропустить эту группу")

            choice = input(f"\n   Введите номер категории (или команду): ").strip().lower()

            if choice == "0":
                print(f"⚠️ Группа '{site_group}' пропущена")
                return
            elif choice == "n":
                if current_page < total_pages - 1:
                    current_page += 1
                else:
                    print("   Это последняя страница")
            elif choice == "p":
                if current_page > 0:
                    current_page -= 1
                else:
                    print("   Это первая страница")
            elif choice == "s":
                search_term = input("   Введите текст для поиска: ").strip().lower()
                matches = [s for s in all_subjects if search_term in s.subject_name.lower()]

                if not matches:
                    print(f"   ❌ Ничего не найдено для '{search_term}'")
                    continue

                print(f"\n   🔍 Найдено {len(matches)} категорий:")
                for i, subj in enumerate(matches[:20], 1):
                    parent = self.db.query(WBSubject).filter(
                        WBSubject.subject_id == subj.parent_id
                    ).first()
                    parent_name = parent.subject_name if parent else "Без родителя"
                    print(f"     {i}. {parent_name} → {subj.subject_name} (ID: {subj.subject_id})")

                sub_choice = input(f"\n   Введите номер категории (или 0 для отмены): ").strip()
                if sub_choice == "0":
                    continue
                if sub_choice.isdigit():
                    sub_num = int(sub_choice)
                    if 1 <= sub_num <= len(matches):
                        selected_subject = matches[sub_num - 1]
                continue
            elif choice.isdigit():
                choice_num = int(choice)
                if 1 <= choice_num <= len(all_subjects):
                    selected_subject = all_subjects[choice_num - 1]
                else:
                    print("   ❌ Неверный номер")
            else:
                print("   ❌ Неверная команда")

        if selected_subject:
            self._save_mapping(domain, site_group, selected_subject.subject_id, selected_subject.subject_name)

            # Всегда спрашиваем о добавлении ключевого слова
            add_keyword = input(f"\n   Добавить ключевое слово '{site_group}' для автопоиска категории '{selected_subject.subject_name}'? (y/n): ").strip().lower()
            if add_keyword == 'y':
                self._add_keyword_for_category(selected_subject.subject_name, site_group, example_name)

    def _add_keyword_for_category(self, category_name: str, keyword: str, example_name: str = None):
        """
        Добавляет новое ключевое слово для категории
        """
        print(f"\n📌 ДОБАВЛЕНИЕ КЛЮЧЕВОГО СЛОВА:")
        print(f"   Категория WB: {category_name}")
        print(f"   Группа сайта: {keyword}")
        if example_name:
            print(f"   Пример товара: {example_name[:80]}...")

        # Добавляем ключевое слово в словарь
        if category_name in self.KEYWORDS_FOR_CATEGORY:
            if keyword not in self.KEYWORDS_FOR_CATEGORY[category_name]:
                self.KEYWORDS_FOR_CATEGORY[category_name].append(keyword)
                print(f"   ✅ Добавлено ключевое слово '{keyword}' для категории '{category_name}'")
            else:
                print(f"   ⚠️ Ключевое слово '{keyword}' уже существует для категории '{category_name}'")
        else:
            self.KEYWORDS_FOR_CATEGORY[category_name] = [keyword]
            print(f"   ✅ Создана новая категория '{category_name}' с ключевым словом '{keyword}'")

        # Сохраняем словарь в файл
        self._save_keywords_to_file()

    def _save_keywords_to_file(self):
        """Сохраняет словарь ключевых слов в файл"""
        try:
            with open('wb_keywords.json', 'w', encoding='utf-8') as f:
                json.dump(self.KEYWORDS_FOR_CATEGORY, f, ensure_ascii=False, indent=2)
            print(f"   💾 Ключевые слова сохранены в wb_keywords.json")
        except Exception as e:
            print(f"   ⚠️ Не удалось сохранить ключевые слова: {e}")

    def _load_keywords_from_file(self):
        """Загружает словарь ключевых слов из файла"""
        try:
            if os.path.exists('wb_keywords.json'):
                with open('wb_keywords.json', 'r', encoding='utf-8') as f:
                    loaded = json.load(f)
                    self.KEYWORDS_FOR_CATEGORY.update(loaded)
                print(f"   📂 Загружены ключевые слова из wb_keywords.json")
        except Exception as e:
            print(f"   ⚠️ Не удалось загрузить ключевые слова: {e}")

    def _save_mapping(self, domain: str, site_group: str, subject_id: int, subject_name: str):
        """Сохраняет сопоставление в базу"""
        # Проверяем, не было ли уже сохранено (на случай повторного выбора)
        existing = self.db.query(WBSubjectMapping).filter(
            WBSubjectMapping.domain == domain,
            WBSubjectMapping.site_group == site_group
        ).first()

        if existing:
            print(f"⚠️ Сопоставление уже существует: {domain} / {site_group} → {existing.subject_name}")
            return

        new_mapping = WBSubjectMapping(
            domain=domain,
            site_group=site_group,
            subject_id=subject_id,
            subject_name=subject_name
        )
        self.db.add(new_mapping)
        self.db.commit()
        print(f"✅ Сохранено: {domain} / {site_group} → {subject_name} (ID: {subject_id})")

    def _extract_domain(self, url: str) -> str:
        """Извлекает домен из URL"""
        if not url:
            return ""
        if '://' in url:
            start = url.find('://') + 3
            end = url.find('/', start)
            if end == -1:
                end = len(url)
            return url[start:end]
        return ""


def main():
    """Главная функция - только этап 1"""
    print("\n" + "=" * 70)
    print("НОРМАЛИЗАЦИЯ ТОВАРОВ ДЛЯ WILDBERRIES - ЭТАП 1")
    print("=" * 70)
    print("\n🔹 Сопоставление групп сайта с категориями WB")
    print("   - Автоматический поиск по ключевым словам")
    print("   - Если не найдено - ручной выбор")
    print("   - После выбора - добавление ключевого слова для автопоиска")
    print("=" * 70 + "\n")

    with get_db_session() as db:
        normalizer = WBNormalizer(db)
        normalizer.sync_groups_mapping()

    print("\n✅ Сопоставление групп завершено!")
    input("\nНажмите Enter для выхода...")


if __name__ == "__main__":
    try:
        # main()
    except KeyboardInterrupt:
        print("\n\n👋 Программа остановлена пользователем")
    except Exception as e:
        print(f"❌ Критическая ошибка: {e}")
        import traceback
        traceback.print_exc()