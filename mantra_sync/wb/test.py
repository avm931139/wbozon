"""
Модуль нормализации товаров для Wildberries
Этап 1: Сопоставление групп сайта с категориями WB (с автопоиском по загруженным категориям)
Этап 2: Заполнение нормализованных товаров
Этап 3: Сопоставление характеристик
"""

"Это копия"

import re
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple
from sqlalchemy.orm import Session

from core.db.connection import get_db_session
from core.db.models import (
    ParserProduct, ParserCharacteristics,
    WBSubject, WBCharacteristic,
    WBSubjectMapping, WBCharacteristicMapping,
    WBNormalizedProduct, WBNormalizedCharacteristic, WBNormalizedSize
)


class WBNormalizer:
    """Нормализует спарсенные товары для загрузки на WB"""

    # Словарь ключевых слов для автопоиска категорий
    KEYWORD_MAPPING = {
        'люстра': ['люстра', 'люстры', 'потолочная', 'потолочные', 'подвесная', 'подвесные'],
        'бра': ['бра', 'настенный', 'настенные', 'настенное'],
        'настольный': ['настольный', 'настольная', 'настольные', 'лампа настольная'],
        'торшер': ['торшер', 'торшеры', 'напольный', 'напольная'],
        'светильник': ['светильник', 'светильники', 'панно', 'накладной', 'накладные'],
        'подвес': ['подвесной', 'подвесные', 'подвес'],
        'трековый': ['трековый', 'трековые', 'трек'],
        'спот': ['спот', 'споты'],
    }

    # Рекомендованные названия категорий WB для каждого типа товара
    # Это точные названия из таблицы WBSubject.subject_name
    RECOMMENDED_SUBJECTS = {
        'люстра': ['Люстры', 'Потолочные светильники', 'Подвесные светильники'],
        'бра': ['Настенные светильники', 'Бра'],
        'настольный': ['Настольные лампы'],
        'торшер': ['Торшеры', 'Напольные светильники'],
        'светильник': ['Светильники', 'Настольные лампы', 'Настенные светильники', 'Бра', 'Торшеры', 'Люстры', 'Подвесные светильники', 'Потолочные светильники', 'Панно', 'Накладные светильники'],
        'подвес': ['Подвесные светильники', 'Люстры'],
        'трековый': ['Трековые светильники', 'Споты'],
        'спот': ['Споты', 'Трековые светильники'],
    }

    def __init__(self, db: Session):
        self.db = db

    # ==================== ЭТАП 1: СОПОСТАВЛЕНИЕ ГРУПП ====================

    def _find_matching_category(self, site_group: str, product_name: str = None) -> Optional[Tuple[int, str, str]]:
        """
        Ищет подходящую категорию WB по ключевым словам
        Возвращает (subject_id, parent_name, subject_name) или None
        """
        search_text = site_group.lower()
        if product_name:
            search_text += " " + product_name.lower()

        # Определяем тип товара по ключевым словам
        found_type = None
        for category, keywords in self.KEYWORD_MAPPING.items():
            for keyword in keywords:
                if keyword in search_text:
                    found_type = category
                    break
            if found_type:
                break

        if not found_type:
            return None

        # Получаем рекомендованные названия для этого типа
        recommended_names = self.RECOMMENDED_SUBJECTS.get(found_type, [])

        # Ищем в базе WBSubject по названию (точное совпадение или LIKE)
        for rec_name in recommended_names:
            subject = self.db.query(WBSubject).filter(
                WBSubject.subject_name.ilike(f"%{rec_name}%")
            ).first()

            if subject:
                return subject.subject_id, None, subject.subject_name

        return None

    def sync_groups_mapping(self):
        """
        Сопоставляет все уникальные groupe_site с категориями WB
        """
        # Получаем все уникальные пары (domain, groupe_site) из parser_product
        products = self.db.query(ParserProduct).all()

        # Собираем уникальные пары с извлечением домена
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

        # Автопоиск категории
        auto_match = self._find_matching_category(site_group, example_name)

        if auto_match:
            subject_id, _, subject_name = auto_match
            print(f"\n🔍 АВТОПОИСК: найдена категория:")
            print(f"   {subject_name} (ID: {subject_id})")

            auto_choice = input("\n   Использовать эту категорию? (Enter - да, n - выбрать другую): ").strip().lower()
            if auto_choice != 'n':
                # Сохраняем сопоставление
                new_mapping = WBSubjectMapping(
                    domain=domain,
                    site_group=site_group,
                    subject_id=subject_id,
                    subject_name=subject_name
                )
                self.db.add(new_mapping)
                self.db.commit()
                print(f"✅ Сохранено: {domain} / {site_group} → {subject_name} (ID: {subject_id})")
                return

        # Ручной выбор - показываем все загруженные категории
        self._manual_group_selection(domain, site_group, example_name)

    def _manual_group_selection(self, domain: str, site_group: str, example_name: str = None):
        """Ручной выбор категории WB из всех загруженных"""

        # Получаем все категории WB (все предметы)
        all_subjects = self.db.query(WBSubject).filter(
            WBSubject.parent_id.isnot(None)  # Только предметы (не родительские категории)
        ).order_by(WBSubject.subject_name).all()

        if not all_subjects:
            print("⚠️ Нет загруженных категорий WB. Сначала загрузите категории через WB API.")
            return

        print(f"\n📂 ВСЕ КАТЕГОРИИ WILDBERRIES (всего {len(all_subjects)}):")
        print("   Введите номер для выбора категории, или текст для поиска\n")

        # Показываем категории с пагинацией
        page_size = 20
        current_page = 0
        total_pages = (len(all_subjects) + page_size - 1) // page_size

        while True:
            start = current_page * page_size
            end = min(start + page_size, len(all_subjects))

            print(f"\n   Страница {current_page + 1}/{total_pages}:")
            for i, subj in enumerate(all_subjects[start:end], start + 1):
                # Получаем родительскую категорию
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
                continue
            elif choice == "p":
                if current_page > 0:
                    current_page -= 1
                else:
                    print("   Это первая страница")
                continue
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
                        selected = matches[sub_num - 1]
                        # Сохраняем сопоставление
                        new_mapping = WBSubjectMapping(
                            domain=domain,
                            site_group=site_group,
                            subject_id=selected.subject_id,
                            subject_name=selected.subject_name
                        )
                        self.db.add(new_mapping)
                        self.db.commit()
                        print(f"✅ Сохранено: {domain} / {site_group} → {selected.subject_name} (ID: {selected.subject_id})")
                        return
                continue

            elif choice.isdigit():
                choice_num = int(choice)
                if 1 <= choice_num <= len(all_subjects):
                    selected = all_subjects[choice_num - 1]
                    # Сохраняем сопоставление
                    new_mapping = WBSubjectMapping(
                        domain=domain,
                        site_group=site_group,
                        subject_id=selected.subject_id,
                        subject_name=selected.subject_name
                    )
                    self.db.add(new_mapping)
                    self.db.commit()
                    print(f"✅ Сохранено: {domain} / {site_group} → {selected.subject_name} (ID: {selected.subject_id})")
                    return
                else:
                    print("   ❌ Неверный номер")
            else:
                print("   ❌ Неверная команда")

    # ==================== ЭТАП 2: ЗАПОЛНЕНИЕ НОРМАЛИЗОВАННЫХ ТОВАРОВ ====================

    def normalize_products(self, limit: int = None):
        """
        Заполняет wb_normalized_product для всех товаров, у которых есть сопоставление группы
        """
        # Получаем товары, которые еще не нормализованы
        existing_ids = set(
            row[0] for row in self.db.query(WBNormalizedProduct.product_id_ms).all()
        )

        query = self.db.query(ParserProduct).filter(
            ParserProduct.id_ms.notin_(existing_ids) if existing_ids else True
        )

        if limit:
            query = query.limit(limit)

        products = query.all()

        if not products:
            print("✅ Все товары уже нормализованы")
            return

        # Фильтруем товары, у которых есть сопоставление группы
        valid_products = []
        skipped = []

        for product in products:
            domain = self._extract_domain(product.url)
            mapping = self.db.query(WBSubjectMapping).filter(
                WBSubjectMapping.domain == domain,
                WBSubjectMapping.site_group == product.groupe_site
            ).first()

            if mapping:
                valid_products.append((product, mapping))
            else:
                skipped.append((product.code_ms, product.groupe_site))

        if skipped:
            print(f"\n⚠️ Пропущено {len(skipped)} товаров без сопоставления группы:")
            for code, group in skipped[:10]:
                print(f"   - {code}: {group}")
            if len(skipped) > 10:
                print(f"   ... и еще {len(skipped) - 10}")

        if not valid_products:
            print("❌ Нет товаров для нормализации (все пропущены)")
            return

        print(f"\n{'=' * 70}")
        print(f"ЭТАП 2: ЗАПОЛНЕНИЕ НОРМАЛИЗОВАННЫХ ТОВАРОВ")
        print(f"{'=' * 70}")
        print(f"\n📦 Начинаем нормализацию {len(valid_products)} товаров\n")

        for idx, (product, mapping) in enumerate(valid_products, 1):
            print(f"{idx}. {product.code_ms} | {product.name_site[:50]}...")

            try:
                self._normalize_single_product(product, mapping)
                print(f"   ✅ Нормализован")
            except Exception as e:
                print(f"   ❌ Ошибка: {e}")
                continue

        print(f"\n✅ Нормализация товаров завершена")

    def _normalize_single_product(self, product: ParserProduct, mapping: WBSubjectMapping):
        """Нормализует один товар"""

        # Получаем характеристики товара
        characteristics = self.db.query(ParserCharacteristics).filter(
            ParserCharacteristics.product_id_ms == product.id_ms
        ).all()

        # Собираем характеристики в словарь
        specs = {}
        for char in characteristics:
            if char.group:
                specs[char.group.name] = char.value

        # Извлекаем габариты
        dimensions = {
            "length": self._extract_dimension(specs, ['длина', 'глубина']),
            "width": self._extract_dimension(specs, ['ширина']),
            "height": self._extract_dimension(specs, ['высота']),
            "weight": self._extract_weight(specs)
        }

        # Создаем нормализованный товар
        normalized = WBNormalizedProduct(
            product_id_ms=product.id_ms,
            subject_mapping_id=mapping.id,
            subject_id=mapping.subject_id,
            subject_name=mapping.subject_name,
            vendor_code=product.code_ms,
            wb_title=product.name_site[:60] if product.name_site else "",
            wb_description=product.description[:5000] if product.description else "",
            wb_brand=product.brand,
            length=dimensions["length"],
            width=dimensions["width"],
            height=dimensions["height"],
            weight=dimensions["weight"],
            status="ready"
        )

        self.db.add(normalized)
        self.db.flush()

        # Сохраняем размер
        normalized_size = WBNormalizedSize(
            product_id=normalized.id,
            tech_size="0",
            barcode=product.code_ms,
            stock=0
        )
        self.db.add(normalized_size)

        self.db.commit()

    # ==================== ЭТАП 3: СОПОСТАВЛЕНИЕ ХАРАКТЕРИСТИК ====================

    def sync_characteristics_mapping(self, limit: int = None):
        """
        Сопоставляет характеристики для нормализованных товаров
        """
        # Получаем нормализованные товары
        query = self.db.query(WBNormalizedProduct).filter(
            WBNormalizedProduct.status == "ready"
        )

        if limit:
            query = query.limit(limit)

        products = query.all()

        if not products:
            print("✅ Нет товаров для сопоставления характеристик")
            return

        print(f"\n{'=' * 70}")
        print(f"ЭТАП 3: СОПОСТАВЛЕНИЕ ХАРАКТЕРИСТИК")
        print(f"{'=' * 70}")
        print(f"\n📊 Найдено {len(products)} товаров для обработки\n")

        for idx, normalized in enumerate(products, 1):
            # Получаем исходный товар
            product = self.db.query(ParserProduct).filter(
                ParserProduct.id_ms == normalized.product_id_ms
            ).first()

            if not product:
                continue

            print(f"\n{idx}. {product.code_ms} | {product.name_site[:50]}...")

            # Получаем характеристики товара
            characteristics = self.db.query(ParserCharacteristics).filter(
                ParserCharacteristics.product_id_ms == product.id_ms
            ).all()

            # Собираем характеристики в словарь
            specs = {}
            for char in characteristics:
                if char.group:
                    specs[char.group.name] = char.value

            # Сопоставляем каждую характеристику
            for site_char_name, site_char_value in specs.items():
                # Пропускаем служебные
                if site_char_name.lower() in ['артикул', 'код товара', 'артикул сайта', 'бренд']:
                    continue

                # Проверяем, есть ли уже сопоставление
                char_mapping = self.db.query(WBCharacteristicMapping).filter(
                    WBCharacteristicMapping.domain == self._extract_domain(product.url),
                    WBCharacteristicMapping.site_characteristic == site_char_name,
                    WBCharacteristicMapping.subject_id == normalized.subject_id
                ).first()

                if char_mapping:
                    # Проверяем, есть ли уже характеристика у товара
                    existing_char = self.db.query(WBNormalizedCharacteristic).filter(
                        WBNormalizedCharacteristic.product_id == normalized.id,
                        WBNormalizedCharacteristic.charc_id == char_mapping.charc_id
                    ).first()

                    if not existing_char:
                        # Добавляем характеристику
                        normalized_value = self.normalize_value(site_char_value, char_mapping.value_transformer)
                        new_char = WBNormalizedCharacteristic(
                            product_id=normalized.id,
                            charc_id=char_mapping.charc_id,
                            charc_name=char_mapping.charc_name,
                            value=str(normalized_value) if normalized_value else site_char_value
                        )
                        self.db.add(new_char)
                        self.db.commit()
                        print(f"   ✅ Добавлена: '{site_char_name}' → '{char_mapping.charc_name}' = {site_char_value}")
                    continue

                # Предлагаем сопоставить
                self._map_single_characteristic(
                    domain=self._extract_domain(product.url),
                    site_char=site_char_name,
                    site_char_value=site_char_value,
                    subject_id=normalized.subject_id,
                    normalized_product_id=normalized.id,
                    product_name=product.name_site
                )

    def _map_single_characteristic(self, domain: str, site_char: str, site_char_value: str,
                                   subject_id: int, normalized_product_id: int, product_name: str = None):
        """Сопоставляет одну характеристику"""

        print(f"\n{'=' * 70}")
        if product_name:
            print(f"📦 Товар: {product_name[:80]}...")
        print(f"📌 ХАРАКТЕРИСТИКА ДЛЯ СОПОСТАВЛЕНИЯ:")
        print(f"   Домен: {domain}")
        print(f"   Название: {site_char}")
        print(f"   Значение: {site_char_value[:100] if site_char_value else ''}")
        print(f"   Категория WB ID: {subject_id}")
        print(f"{'=' * 70}")

        # Получаем характеристики для категории
        chars = self.db.query(WBCharacteristic).filter(
            WBCharacteristic.subject_id == subject_id
        ).order_by(WBCharacteristic.char_name).all()

        if not chars:
            print("   ⚠️ Нет характеристик для этой категории")
            return

        # Показываем характеристики с пагинацией
        page_size = 20
        current_page = 0
        total_pages = (len(chars) + page_size - 1) // page_size

        while True:
            start = current_page * page_size
            end = min(start + page_size, len(chars))

            print(f"\n📋 Доступные характеристики Wildberries (страница {current_page + 1}/{total_pages}):")
            for i, char in enumerate(chars[start:end], start + 1):
                unit = f" ({char.unit_name})" if char.unit_name else ""
                required = " [обязательная]" if char.is_required else ""
                print(f"  {i}. {char.char_name}{unit}{required} (ID: {char.char_id})")

            print(f"\n   Команды:")
            print(f"     n - следующая страница")
            print(f"     p - предыдущая страница")
            print(f"     s - поиск по названию")
            print(f"     0 - пропустить эту характеристику")
            print(f"     a - пропустить все оставшиеся характеристики этого товара")

            choice = input(f"\nВведите номер, ID, текст для поиска или команду: ").strip().lower()

            if choice == "0":
                return
            elif choice == "a":
                raise StopIteration("Пропуск всех характеристик товара")
            elif choice == "n":
                if current_page < total_pages - 1:
                    current_page += 1
                else:
                    print("   Это последняя страница")
                continue
            elif choice == "p":
                if current_page > 0:
                    current_page -= 1
                else:
                    print("   Это первая страница")
                continue
            elif choice == "s":
                search_term = input("   Введите текст для поиска: ").strip().lower()
                matches = [c for c in chars if search_term in c.char_name.lower()]

                if not matches:
                    print(f"   ❌ Ничего не найдено для '{search_term}'")
                    continue

                print(f"\n   🔍 Найдено {len(matches)} характеристик:")
                for j, char in enumerate(matches[:20], 1):
                    unit = f" ({char.unit_name})" if char.unit_name else ""
                    print(f"     {j}. {char.char_name}{unit} (ID: {char.char_id})")

                sub_choice = input(f"\n   Введите номер (или 0 для отмены): ").strip()
                if sub_choice == "0":
                    continue
                if sub_choice.isdigit():
                    sub_num = int(sub_choice)
                    if 1 <= sub_num <= len(matches):
                        selected = matches[sub_num - 1]
                        transformer = self._suggest_transformer(site_char, selected)
                        self._save_char_mapping(domain, site_char, subject_id,
                                               selected.char_id, selected.char_name, transformer,
                                               normalized_product_id, site_char_value)
                        return
                continue

            elif choice.isdigit():
                choice_num = int(choice)
                if 1 <= choice_num <= len(chars):
                    selected = chars[choice_num - 1]
                    transformer = self._suggest_transformer(site_char, selected)
                    self._save_char_mapping(domain, site_char, subject_id,
                                           selected.char_id, selected.char_name, transformer,
                                           normalized_product_id, site_char_value)
                    return
                else:
                    # Пробуем как прямой ID
                    for char in chars:
                        if char.char_id == choice_num:
                            transformer = self._suggest_transformer(site_char, char)
                            self._save_char_mapping(domain, site_char, subject_id,
                                                   char.char_id, char.char_name, transformer,
                                                   normalized_product_id, site_char_value)
                            return
                    print("   ❌ Неверный номер")
            else:
                print("   ❌ Неверная команда")

    def _save_char_mapping(self, domain: str, site_char: str, subject_id: int,
                          charc_id: int, charc_name: str, transformer: str,
                          normalized_product_id: int, site_char_value: str):
        """Сохраняет сопоставление характеристики и добавляет ее в товар"""

        # Сохраняем в таблицу сопоставлений
        new_mapping = WBCharacteristicMapping(
            domain=domain,
            site_characteristic=site_char,
            subject_id=subject_id,
            charc_id=charc_id,
            charc_name=charc_name,
            value_transformer=transformer
        )
        self.db.add(new_mapping)
        self.db.flush()

        # Нормализуем значение
        normalized_value = self.normalize_value(site_char_value, transformer)

        # Сохраняем характеристику для товара
        normalized_char = WBNormalizedCharacteristic(
            product_id=normalized_product_id,
            charc_id=charc_id,
            charc_name=charc_name,
            value=str(normalized_value) if normalized_value else site_char_value
        )
        self.db.add(normalized_char)
        self.db.commit()

        print(f"   ✅ Сопоставлено: '{site_char}' → '{charc_name}'")
        print(f"      Значение: {site_char_value} → {normalized_value if normalized_value else site_char_value}")

    # ==================== ВСПОМОГАТЕЛЬНЫЕ МЕТОДЫ ====================

    def _suggest_transformer(self, site_char: str, wb_char: WBCharacteristic) -> str:
        """Предлагает трансформатор значения"""
        site_char_lower = site_char.lower()

        if any(x in site_char_lower for x in ['длина', 'ширина', 'высота', 'глубина', 'диаметр']):
            return "mm_to_cm"
        if any(x in site_char_lower for x in ['вес', 'масса']):
            return "g_to_kg"

        return "direct"

    def normalize_value(self, value: str, transformer: str) -> Any:
        """Трансформирует значение"""
        if not value:
            return None

        value = str(value).strip()

        if transformer == "mm_to_cm":
            try:
                num = float(re.sub(r'[^0-9.,]', '', value.replace(',', '.')))
                return round(num / 10, 1)
            except:
                return value

        if transformer == "g_to_kg":
            try:
                num = float(re.sub(r'[^0-9.,]', '', value.replace(',', '.')))
                return round(num / 1000, 3)
            except:
                return value

        return value

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

    def _extract_dimension(self, specs: Dict[str, str], keywords: List[str]) -> int:
        """Извлекает размер из характеристик"""
        for key, value in specs.items():
            if any(kw in key.lower() for kw in keywords):
                try:
                    num = float(re.sub(r'[^0-9.,]', '', str(value).replace(',', '.')))
                    if num > 100:
                        return int(round(num / 10))
                    return int(round(num))
                except:
                    pass
        return 0

    def _extract_weight(self, specs: Dict[str, str]) -> float:
        """Извлекает вес из характеристик"""
        for key, value in specs.items():
            if 'вес' in key.lower():
                try:
                    num = float(re.sub(r'[^0-9.,]', '', str(value).replace(',', '.')))
                    if 'г' in str(value) and num > 10:
                        return round(num / 1000, 3)
                    return round(num, 3)
                except:
                    pass
        return 0.0


def main():
    """Главная функция"""
    print("\n" + "=" * 70)
    print("НОРМАЛИЗАЦИЯ ТОВАРОВ ДЛЯ WILDBERRIES")
    print("=" * 70)
    print("\n🔹 ЭТАП 1: Сопоставление групп сайта с категориями WB")
    print("   - Автоматический поиск по ключевым словам")
    print("   - Ручной выбор из всех загруженных категорий")
    print("🔹 ЭТАП 2: Заполнение нормализованных товаров")
    print("🔹 ЭТАП 3: Сопоставление характеристик")
    print("=" * 70 + "\n")

    with get_db_session() as db:
        normalizer = WBNormalizer(db)

        # ЭТАП 1
        print("\n" + "=" * 70)
        print("ЭТАП 1: СОПОСТАВЛЕНИЕ ГРУПП")
        print("=" * 70)
        proceed = input("\nВыполнить этап 1? (Enter - да, n - пропустить): ").strip().lower()
        if proceed != 'n':
            normalizer.sync_groups_mapping()

        # ЭТАП 2
        print("\n" + "=" * 70)
        print("ЭТАП 2: ЗАПОЛНЕНИЕ НОРМАЛИЗОВАННЫХ ТОВАРОВ")
        print("=" * 70)
        proceed = input("\nВыполнить этап 2? (Enter - да, n - пропустить): ").strip().lower()
        if proceed != 'n':
            try:
                limit = input("Сколько товаров обработать (Enter - все): ").strip()
                limit = int(limit) if limit else None
            except:
                limit = None
            normalizer.normalize_products(limit=limit)

        # ЭТАП 3
        print("\n" + "=" * 70)
        print("ЭТАП 3: СОПОСТАВЛЕНИЕ ХАРАКТЕРИСТИК")
        print("=" * 70)
        proceed = input("\nВыполнить этап 3? (Enter - да, n - пропустить): ").strip().lower()
        if proceed != 'n':
            try:
                limit = input("Сколько товаров обработать (Enter - все): ").strip()
                limit = int(limit) if limit else None
            except:
                limit = None
            normalizer.sync_characteristics_mapping(limit=limit)

    print("\n✅ Нормализация завершена!")
    input("\nНажмите Enter для выхода...")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n👋 Программа остановлена пользователем")
    except Exception as e:
        print(f"❌ Критическая ошибка: {e}")
        import traceback
        traceback.print_exc()