"""
Модуль нормализации характеристик для Wildberries (ЭТАП 3)

Особенности:
- Автосопоставление по WBCharacteristicMapping
- Ручной выбор WB-характеристики
- Преобразование значений (мм->см, г->кг, extract_number)
- ВАЖНО: если характеристику пропустили, она больше не предлагается в рамках домена
- ВАЖНО: несколько характеристик сайта могут сопоставляться с одной WB-характеристикой
- Есть явные выходы:
  * пропустить текущую характеристику (глобально для домена)
  * пропустить весь товар
  * завершить модуль
"""

import re
from urllib.parse import urlparse
from typing import Optional, Dict, Any, List, Tuple, Set

from sqlalchemy.orm import Session

from core.db.connection import get_db_session
from core.db.models import (
    ParserProduct,
    ParserCharacteristics,
    WBCharacteristic,
    WBCharacteristicMapping,
    WBNormalizedProduct,
    WBNormalizedCharacteristic,
    WBSubjectCharacteristic,
)


class WBNormalizerCharacteristics:
    def __init__(self, db: Session, interactive: bool = True):
        self.db = db
        self.interactive = interactive

    def normalize_characteristics(
        self,
        limit: Optional[int] = None,
        statuses: Optional[List[str]] = None,
    ) -> None:
        query = self.db.query(WBNormalizedProduct)

        if statuses:
            query = query.filter(WBNormalizedProduct.status.in_(statuses))

        if limit:
            query = query.limit(limit)

        products = query.all()
        if not products:
            print("❌ Нет товаров для обработки")
            return

        # Исключаем уже обработанные
        ids = [p.id for p in products]
        done_ids = {
            row[0]
            for row in self.db.query(WBNormalizedCharacteristic.product_id)
            .filter(WBNormalizedCharacteristic.product_id.in_(ids))
            .distinct()
            .all()
        }
        products = [p for p in products if p.id not in done_ids]

        if not products:
            print("✅ Все товары уже имеют нормализованные характеристики")
            return

        print(f"📦 К обработке: {len(products)} товаров")

        success = 0
        skipped = 0
        errors = 0

        for i, p in enumerate(products, 1):
            print(f"\n{i}. {p.vendor_code} | {(p.wb_title or '')[:60]}...")
            try:
                count, product_skipped = self._normalize_one_product(p)
                if product_skipped:
                    skipped += 1
                    print("   ⏭️ Товар пропущен")
                elif count > 0:
                    success += 1
                    print(f"   ✅ Добавлено характеристик: {count}")
                else:
                    skipped += 1
                    print("   ⚠️ Нет характеристик для нормализации")
            except KeyboardInterrupt:
                print("\n👋 Остановлено пользователем")
                raise
            except Exception as exc:
                errors += 1
                self.db.rollback()
                print(f"   ❌ Ошибка: {exc}")

        print("\n📊 Итог:")
        print(f"   ✅ Успешно: {success}")
        print(f"   ⏭️ Пропущено: {skipped}")
        print(f"   ❌ Ошибок: {errors}")

    def _normalize_one_product(self, np: WBNormalizedProduct) -> Tuple[int, bool]:
        parser_chars = (
            self.db.query(ParserCharacteristics)
            .filter(ParserCharacteristics.product_id_ms == np.product_id_ms)
            .all()
        )
        if not parser_chars:
            return 0, False

        wb_char_dict, allowed_ids = self._get_available_wb_chars(np.subject_id)
        if not wb_char_dict:
            print(f"   ❌ Нет WB-характеристик для subject_id={np.subject_id}")
            return 0, False

        domain = self._extract_domain(np.product_id_ms)

        # Получаем все сопоставления для домена и subject
        mappings = (
            self.db.query(WBCharacteristicMapping)
            .filter(
                WBCharacteristicMapping.domain == domain,
                WBCharacteristicMapping.subject_id == np.subject_id,
            )
            .all()
        )
        map_dict = {m.site_characteristic: m for m in mappings}

        # Множество уже обработанных пар (site_name, site_value)
        used_pairs: set[Tuple[str, str]] = set()
        added = 0

        # ---------- Фаза 1: авто ----------
        for pc in parser_chars:
            if not pc.group or not pc.group.name:
                continue

            site_name = pc.group.name.strip()
            site_value = (pc.value or "").strip()
            if not site_value:
                continue

            pair = (site_name, site_value)
            if pair in used_pairs:
                continue

            mapping = map_dict.get(site_name)

            # Проверяем, не пропущена ли эта характеристика глобально
            if mapping and (mapping.charc_id == 0 or mapping.charc_name == "__SKIP__"):
                print(f"   ⏭️ Пропущена (глобально): {site_name} = {site_value}")
                used_pairs.add(pair)
                continue

            if not mapping:
                continue

            wb_char_pk = mapping.charc_id
            if wb_char_pk not in allowed_ids:
                continue

            wb_char = wb_char_dict.get(wb_char_pk)
            if not wb_char:
                continue

            # Разрешаем множественное сопоставление - НЕ проверяем used_wb_chars_in_product
            transformed = self._apply_transformer(site_value, mapping.value_transformer or "direct")

            self.db.add(
                WBNormalizedCharacteristic(
                    product_id=np.id,
                    charc_id=wb_char.char_id,
                    charc_name=wb_char.char_name,
                    value=str(transformed),
                    value_type=self._infer_value_type(transformed),
                    source_char_id=getattr(pc, "id", None),
                )
            )

            used_pairs.add(pair)
            added += 1
            print(f"   📌 Авто: {site_name} -> {wb_char.char_name} = {transformed}")

        # ---------- Фаза 2: ручная (только для тех, у кого нет mapping) ----------
        remaining = []
        for pc in parser_chars:
            if not pc.group or not pc.group.name:
                continue
            site_name = pc.group.name.strip()
            site_value = (pc.value or "").strip()
            if not site_value:
                continue

            # Пропускаем уже обработанные
            if (site_name, site_value) in used_pairs:
                continue

            # Проверяем, есть ли mapping (включая SKIP)
            mapping = map_dict.get(site_name)

            # Если есть mapping с SKIP - пропускаем без вопроса
            if mapping and (mapping.charc_id == 0 or mapping.charc_name == "__SKIP__"):
                print(f"   ⏭️ Пропущена (глобально): {site_name} = {site_value}")
                used_pairs.add((site_name, site_value))
                continue

            # Если есть mapping с нормальной характеристикой, но почему-то не обработался - проверим
            if mapping and mapping.charc_id != 0:
                # Такого быть не должно, но на всякий случай пропускаем
                used_pairs.add((site_name, site_value))
                continue

            # Нет mapping - нужно спросить
            remaining.append((pc, site_name, site_value))

        if self.interactive and remaining:
            print(f"   📝 Без сопоставления: {len(remaining)}")

            for pc, site_name, site_value in remaining:
                if (site_name, site_value) in used_pairs:
                    continue

                added_flag, skip_product, skip_current = self._ask_mapping(
                    domain=domain,
                    subject_id=np.subject_id,
                    normalized_product_id=np.id,
                    site_char_name=site_name,
                    site_char_value=site_value,
                    wb_char_dict=wb_char_dict,
                    source_char_id=getattr(pc, "id", None),
                )

                if skip_current:
                    # Пользователь выбрал "Пропустить эту характеристику"
                    # Сохраняем глобальный skip для этого домена
                    self._save_skip_mapping(domain, site_name, np.subject_id)
                    used_pairs.add((site_name, site_value))
                    continue

                if skip_product:
                    self.db.commit()
                    return added, True

                if added_flag:
                    used_pairs.add((site_name, site_value))
                    added += 1

        self.db.commit()
        return added, False

    def _get_available_wb_chars(self, subject_id: int) -> Tuple[Dict[int, WBCharacteristic], Set[int]]:
        """Возвращает словарь WB-характеристик и множество допустимых ID"""
        # 1) через таблицу связей
        links = (
            self.db.query(WBSubjectCharacteristic)
            .filter(WBSubjectCharacteristic.subject_id == subject_id)
            .all()
        )

        if links:
            ids = {l.wb_characteristic_id for l in links}
            chars = self.db.query(WBCharacteristic).filter(WBCharacteristic.id.in_(ids)).all()
            d = {c.id: c for c in chars}
            if d:
                return d, set(d.keys())

        # 2) fallback по subject_id
        chars = (
            self.db.query(WBCharacteristic)
            .filter(WBCharacteristic.subject_id == subject_id)
            .all()
        )
        d = {c.id: c for c in chars}
        return d, set(d.keys())

    def _ask_mapping(
        self,
        domain: str,
        subject_id: int,
        normalized_product_id: int,
        site_char_name: str,
        site_char_value: str,
        wb_char_dict: Dict[int, WBCharacteristic],
        source_char_id: Optional[int] = None,
    ) -> Tuple[bool, bool, bool]:
        """
        returns: (added, skip_product, skip_current)
        """
        print(f"\n   🔍 Характеристика сайта: '{site_char_name}' = '{site_char_value}'")

        # Показываем ВСЕ доступные WB-характеристики (разрешаем множественное сопоставление)
        available_options = []
        for pk, ch in wb_char_dict.items():
            available_options.append((pk, ch.char_name, ch.unit_name))

        if not available_options:
            print("   ⚠️ Нет доступных WB-характеристик")
            return False, False, True

        available_options.sort(key=lambda x: x[1] or "")

        print("\n   Доступные WB-характеристики:")
        for i, (_, name, unit) in enumerate(available_options, 1):
            unit_txt = f" [{unit}]" if unit else ""
            print(f"      {i}. {name}{unit_txt}")

        skip_current_idx = len(available_options) + 1
        skip_product_idx = len(available_options) + 2

        print(f"\n      {skip_current_idx}. Пропустить эту характеристику (глобально для домена)")
        print(f"      {skip_product_idx}. Пропустить весь товар")
        print("      0. Ввести новую WB-характеристику вручную")
        print("      -1. Завершить модуль")

        raw = input(f"\n   Выбор (-1..{skip_product_idx}): ").strip()

        if raw == "-1":
            raise KeyboardInterrupt("Остановлено пользователем")

        if not raw.isdigit():
            print("   ❌ Неверный ввод")
            return False, False, True

        n = int(raw)

        if n == skip_current_idx:
            print("   ⏭️ Характеристика будет пропущена (глобально для этого домена)")
            return False, False, True

        if n == skip_product_idx:
            print("   ⏭️ Весь товар пропущен")
            return False, True, False

        if n == 0:
            wb_char = self._create_manual_wb_char(subject_id)
            if not wb_char:
                return False, False, True
        elif 1 <= n <= len(available_options):
            wb_char_pk, _, _ = available_options[n - 1]
            wb_char = wb_char_dict[wb_char_pk]
        else:
            print("   ❌ Неверный выбор")
            return False, False, True

        # Разрешаем множественное сопоставление - НЕ проверяем, использовалась ли уже эта WB-характеристика

        transformer = self._ask_transformer(wb_char.unit_name)
        transformed = self._apply_transformer(site_char_value, transformer)

        self._ensure_subject_link(subject_id, wb_char.id)
        self._save_mapping(
            domain=domain,
            site_char=site_char_name,
            subject_id=subject_id,
            wb_char_pk=wb_char.id,
            wb_char_name=wb_char.char_name,
            transformer=transformer,
        )

        self.db.add(
            WBNormalizedCharacteristic(
                product_id=normalized_product_id,
                charc_id=wb_char.char_id,
                charc_name=wb_char.char_name,
                value=str(transformed),
                value_type=self._infer_value_type(transformed),
                source_char_id=source_char_id,
            )
        )

        print(f"   ✅ Сохранено: {wb_char.char_name} = {transformed}")
        return True, False, False

    def _create_manual_wb_char(self, subject_id: int) -> Optional[WBCharacteristic]:
        name = input("   Название новой WB-характеристики: ").strip()
        if not name:
            return None

        # Ищем по названию (без привязки к subject)
        existing = self.db.query(WBCharacteristic).filter(
            WBCharacteristic.char_name == name
        ).first()

        if existing:
            print(f"   ℹ️ Найдена существующая характеристика: {existing.char_name}")
            self._ensure_subject_link(subject_id, existing.id)
            return existing

        # Создаем новую
        import time
        temp_char_id = -abs(int(time.time()) % 1000000)

        row = WBCharacteristic(
            subject_id=subject_id,
            char_id=temp_char_id,
            char_name=name,
            char_type="string",
            is_required=False,
            is_collection=False,
            is_multiple=False,
        )
        self.db.add(row)
        self.db.flush()
        print(f"   ✅ Создана новая характеристика: {name}")
        return row

    def _ensure_subject_link(self, subject_id: int, wb_char_pk: int) -> None:
        """Добавляет связь между subject и характеристикой, если её нет"""
        exists = self.db.query(WBSubjectCharacteristic).filter(
            WBSubjectCharacteristic.subject_id == subject_id,
            WBSubjectCharacteristic.wb_characteristic_id == wb_char_pk,
        ).first()

        if not exists:
            self.db.add(
                WBSubjectCharacteristic(
                    subject_id=subject_id,
                    wb_characteristic_id=wb_char_pk,
                    is_required=False,
                )
            )
            self.db.flush()

    def _save_mapping(
        self,
        domain: str,
        site_char: str,
        subject_id: int,
        wb_char_pk: int,
        wb_char_name: str,
        transformer: str,
    ) -> None:
        """Сохраняет сопоставление характеристики сайта с WB-характеристикой"""
        exists = self.db.query(WBCharacteristicMapping).filter(
            WBCharacteristicMapping.domain == domain,
            WBCharacteristicMapping.site_characteristic == site_char,
            WBCharacteristicMapping.subject_id == subject_id,
        ).first()

        if exists:
            print(f"   ℹ️ Сопоставление уже существует: '{site_char}' -> '{wb_char_name}'")
            return

        self.db.add(
            WBCharacteristicMapping(
                domain=domain,
                site_characteristic=site_char,
                subject_id=subject_id,
                charc_id=wb_char_pk,
                charc_name=wb_char_name,
                value_transformer=transformer,
            )
        )
        self.db.flush()
        print(f"   ✅ Сохранено сопоставление: '{site_char}' -> '{wb_char_name}'")

    def _save_skip_mapping(self, domain: str, site_char: str, subject_id: int) -> None:
        """Сохраняет пропуск характеристики (глобально для домена)"""
        exists = self.db.query(WBCharacteristicMapping).filter(
            WBCharacteristicMapping.domain == domain,
            WBCharacteristicMapping.site_characteristic == site_char,
            WBCharacteristicMapping.subject_id == subject_id,
        ).first()

        if exists:
            print(f"   ℹ️ Пропуск уже сохранен для '{site_char}'")
            return

        self.db.add(
            WBCharacteristicMapping(
                domain=domain,
                site_characteristic=site_char,
                subject_id=subject_id,
                charc_id=0,
                charc_name="__SKIP__",
                value_transformer="direct",
            )
        )
        self.db.flush()
        print(f"   ✅ Сохранен пропуск для '{site_char}' (больше не будет предлагаться для этого домена)")

    @staticmethod
    def _ask_transformer(unit_name: Optional[str]) -> str:
        print("\n   Трансформатор значения:")
        if unit_name:
            print(f"   Подсказка (единица измерения): {unit_name}")
        print("      1. direct (без изменений)")
        print("      2. mm_to_cm (мм → см)")
        print("      3. g_to_kg (г → кг)")
        print("      4. extract_number (только число)")

        raw = input("   Выбор (1-4, Enter=1): ").strip()
        result = {
            "1": "direct",
            "2": "mm_to_cm",
            "3": "g_to_kg",
            "4": "extract_number",
            "": "direct",
        }.get(raw, "direct")

        transformer_names = {
            "direct": "без изменений",
            "mm_to_cm": "мм → см",
            "g_to_kg": "г → кг",
            "extract_number": "только число"
        }
        print(f"   ✅ Выбран трансформатор: {transformer_names[result]}")
        return result

    @staticmethod
    def _apply_transformer(value: str, transformer: str) -> Any:
        try:
            cleaned = re.sub(r"[^0-9.,]", "", str(value)).replace(",", ".")
            if transformer == "mm_to_cm":
                return round(float(cleaned) / 10, 1)
            if transformer == "g_to_kg":
                return round(float(cleaned) / 1000, 3)
            if transformer == "extract_number":
                return float(cleaned)
            return str(value).strip()
        except Exception:
            return str(value).strip()

    @staticmethod
    def _infer_value_type(value: Any) -> str:
        return "number" if isinstance(value, (int, float)) else "string"

    def _extract_domain(self, product_id_ms: str) -> str:
        p = self.db.query(ParserProduct).filter(ParserProduct.id_ms == product_id_ms).first()
        if not p or not p.url:
            return ""
        parsed = urlparse(p.url)
        domain = (parsed.netloc or "").lower()
        # Убираем www.
        if domain.startswith("www."):
            domain = domain[4:]
        return domain


def main() -> None:
    print("\n" + "=" * 70)
    print("ЭТАП 3: НОРМАЛИЗАЦИЯ ХАРАКТЕРИСТИК ДЛЯ WILDBERRIES")
    print("=" * 70)
    print("\nОсобенности:")
    print("  • Несколько характеристик сайта могут сопоставляться с одной WB-характеристикой")
    print("  • Пропущенная характеристика больше не предлагается для этого домена")
    print("  • Автоматическое преобразование единиц измерения (мм→см, г→кг)")
    print("=" * 70 + "\n")

    raw_limit = input("Лимит товаров (Enter = все): ").strip()
    limit = int(raw_limit) if raw_limit.isdigit() else None

    raw_statuses = input("Статусы через запятую (Enter = все): ").strip()
    statuses = [x.strip() for x in raw_statuses.split(",") if x.strip()] if raw_statuses else None

    mode = input("Интерактивный режим? (y/n, Enter=y): ").strip().lower()
    interactive = mode != "n"

    print()

    with get_db_session() as db:
        normalizer = WBNormalizerCharacteristics(db=db, interactive=interactive)
        normalizer.normalize_characteristics(limit=limit, statuses=statuses)

    print("\n✅ Нормализация характеристик завершена!")
    input("\nНажмите Enter для выхода...")


if __name__ == "__main__":
    try:
        # main()
    except KeyboardInterrupt:
        print("\n\n👋 Программа остановлена пользователем")
    except Exception as exc:
        print(f"\n❌ Критическая ошибка: {exc}")
        import traceback
        traceback.print_exc()