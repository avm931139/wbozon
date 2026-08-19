"""
Модуль тестирования маппинга характеристик люстры через GPT-5.4
Преобразует сырые данные (30-35 полей) в стандартные поля Wildberries (15 полей)
"""

import json
import os
from typing import Dict, Any, List
from datetime import datetime

from wb.gpt.gpt_client import GPTClient
from core.db.models import GPTModels
from core.db.connection import get_db_session

# ============================================================
# 1. ТЕСТОВЫЕ ДАННЫЕ (СЫРЫЕ ХАРАКТЕРИСТИКИ ЛЮСТРЫ - 35 полей)
# ============================================================

RAW_LUSTER_DATA = {
    # Основная информация
    "название_товара": "Люстра подвесная Crystal Lux Gold CL-GLD-806 6 рожков",
    "страна_производства": "Китай",
    "гарантия": "12 месяцев",

    # Размеры и вес
    "высота": 20,
    "коробки высота мм": 5200,
    "ширина": 80,
    "коробки ширина_мм": 6800,
    "глубина_мм": 80,
    "коробки глубина_мм": 6800,
    "диаметр_мм": 680,
    "вес_кг": 4.8,
    "высота_подвеса_мин_мм": 400,
    "высота_подвеса_макс_мм": 1200,

    # Электрические характеристики
    "тип_цоколя": "E14",
    "количество_ламп": 6,
    "макс_мощность_лампы_вт": 40,
    "общая_мощность_вт": 240,
    "напряжение_в": "220-240",
    "класс_энергоэффективности": "A++",
    "класс_защиты_ip": "IP20",
    "тип_ламп_в_комплекте": "нет",
    "световой_поток_лм": 3600,
    "цветовая_температура_к": 3000,
    "индекс_цветопередачи_cri": ">80",

    # Материалы и цвет
    "материал_арматуры": "металл, сталь",
    "цвет_арматуры": "золото, золотистый, brushed gold",
    "материал_плафонов": "стекло, хрусталь",
    "цвет_плафонов": "прозрачный, хрустальный",
    "отделка": "полировка, гальваническое покрытие",

    # Стиль и дизайн
    "стиль": "классика, модерн, арт-деко",
    "форма": "круглая, каскадная",
    "направление_света": "вниз, рассеянный",
    "количество_ярусов": 1,
    "тип_крепления": "крюк, монтажная пластина",

    # Дополнительно
    "пульт_д/у": "нет",
    "диммирование": "нет",
    "влагостойкость": "нет",
    "помещение": "гостиная, спальня, столовая",
    "серия": "Crystal Collection",
    "коллекция": "Lux Gold Series",
    "наличие_в_наличии": "да",
    "цена_руб": 12500,
    "скидка_%": 15,
    "рейтинг": 4.8,
    "отзывов": 127
}

# ============================================================
# 2. ЦЕЛЕВАЯ СТРУКТУРА WILDBERRIES (15 полей)
# ============================================================

WB_TARGET_SCHEMA = {
    "description": "Структура для загрузки товара в Wildberries",
    "fields": [
        {"name": "name", "type": "string", "required": True, "description": "Название товара"},
        {"name": "brand", "type": "string", "required": True, "description": "Бренд"},
        {"name": "article", "type": "string", "required": True, "description": "Артикул продавца"},
        {"name": "category", "type": "string", "required": True, "description": "Категория (Люстры/Светильники)"},
        {"name": "price", "type": "number", "required": True, "description": "Цена в рублях"},
        {"name": "height_cm", "type": "number", "required": True, "description": "Высота в см"},
        {"name": "width_cm", "type": "number", "required": True, "description": "Ширина в см"},
        {"name": "depth_cm", "type": "number", "required": True, "description": "Глубина в см"},
        {"name": "weight_kg", "type": "number", "required": True, "description": "Вес в кг"},
        {"name": "lamp_type", "type": "string", "required": True, "description": "Тип цоколя (E14/E27/GU10)"},
        {"name": "lamp_count", "type": "integer", "required": True, "description": "Количество ламп"},
        {"name": "max_power_w", "type": "integer", "required": True, "description": "Макс. мощность лампы (Вт)"},
        {"name": "material", "type": "string", "required": True, "description": "Материал арматуры"},
        {"name": "color", "type": "string", "required": True, "description": "Цвет"},
        {"name": "room", "type": "string", "required": True, "description": "Рекомендуемое помещение"}
    ]
}


# ============================================================
# 3. ФУНКЦИЯ ДЛЯ РАСЧЕТА СТОИМОСТИ ЗАПРОСА
# ============================================================

def calculate_request_cost(model_id: str, prompt_text: str, response_tokens: int = 500) -> Dict[str, Any]:
    """Расчет стоимости запроса к GPT"""
    from core.db.connection import get_db_session

    # Оценка токенов (~4 символа = 1 токен)
    prompt_tokens = len(prompt_text) // 4

    # Получаем цены из БД
    try:
        with get_db_session() as session:
            model = session.query(GPTModels).filter(GPTModels.id == model_id).first()
            if model:
                cost_context = float(model.cost_context)
                cost_completion = float(model.cost_completion)
            else:
                # Дефолтные цены для GPT-5.4 (примерные)
                cost_context = 1.35  # $ за 1K токенов
                cost_completion = 2.70
    except:
        cost_context = 1.35
        cost_completion = 2.70

    # Расчет
    cost_prompt = (prompt_tokens / 1000) * cost_context
    cost_completion = (response_tokens / 1000) * cost_completion
    total_cost = cost_prompt + cost_completion

    return {
        "model": model_id,
        "prompt_tokens": prompt_tokens,
        "response_tokens": response_tokens,
        "total_tokens": prompt_tokens + response_tokens,
        "cost_prompt_usd": round(cost_prompt, 6),
        "cost_completion_usd": round(cost_completion, 6),
        "total_cost_usd": round(total_cost, 6),
        "cost_context_per_1k": cost_context,
        "cost_completion_per_1k": cost_completion
    }


# ============================================================
# 4. СОЗДАНИЕ ПРОМПТА ДЛЯ GPT
# ============================================================

def create_mapping_prompt(raw_data: Dict, target_schema: Dict) -> str:
    """Создает промпт для GPT"""

    prompt = f"""
Ты - эксперт по заполнению карточек товаров на Wildberries.

У тебя есть сырые данные о товаре "Люстра" в формате JSON. 
Твоя задача - преобразовать их в структуру Wildberries.

=== СЫРЫЕ ДАННЫЕ (30+ характеристик) ===
{json.dumps(raw_data, ensure_ascii=False, indent=2)}

=== ТРЕБУЕМАЯ СТРУКТУРА WILDBERRIES ===
Нужно заполнить следующие поля:
{json.dumps(target_schema['fields'], ensure_ascii=False, indent=2)}

=== ПРАВИЛА ===
1. В поле "name" составь продающее название: [Бренд] [Тип] [Кол-во ламп]рожк. [Цвет] [Ключевые особенности]
2. Все размеры переведи в сантиметры (если в мм - раздели на 10)
3. Вес оставь в кг
4. Тип цоколя приведи к формату E14/E27/GU10
5. Материал укажи основной (металл/стекло/дерево)
6. Цвет приведи к единому формату (золото/черный/белый)
7. Рекомендуемое помещение выбери из: гостиная, спальня, кухня, столовая, прихожая, кабинет
8. Если данных нет - оставь поле пустым или укажи "Не указано"

=== ОТВЕТ ===
Ответь ТОЛЬКО в формате JSON, без пояснений, по следующей структуре:
{{
    "name": "название товара",
    "brand": "бренд",
    "article": "артикул",
    "category": "Люстры",
    "price": 12500,
    "height_cm": 52.0,
    "width_cm": 68.0,
    "depth_cm": 68.0,
    "weight_kg": 4.8,
    "lamp_type": "E14",
    "lamp_count": 6,
    "max_power_w": 40,
    "material": "металл",
    "color": "золото",
    "room": "гостиная"
}}
"""
    return prompt


# ============================================================
# 5. ОСНОВНАЯ ФУНКЦИЯ ТЕСТИРОВАНИЯ
# ============================================================

def test_gpt_mapping(model_id: str = "gpt-5.4") -> Dict[str, Any]:
    """
    Тестирование маппинга характеристик через GPT-5.4

    Args:
        model_id: ID модели для тестирования

    Returns:
        Результат теста с ответом GPT и стоимостью
    """
    print("=" * 60)
    print(f"ТЕСТИРОВАНИЕ МОДЕЛИ: {model_id}")
    print("=" * 60)

    # 1. Создаем промпт
    print("\n1. СОЗДАНИЕ ПРОМПТА...")
    prompt = create_mapping_prompt(RAW_LUSTER_DATA, WB_TARGET_SCHEMA)
    print(f"Размер промпта: {len(prompt)} символов (~{len(prompt) // 4} токенов)")

    # 2. Расчет стоимости
    print("\n2. РАСЧЕТ СТОИМОСТИ...")
    cost_info = calculate_request_cost(model_id, prompt, response_tokens=500)
    print(f"   Входные токены: {cost_info['prompt_tokens']}")
    print(f"   Выходные токены: ~{cost_info['response_tokens']}")
    print(f"   Стоимость: ${cost_info['total_cost_usd']:.6f} USD")
    print(f"   По курсу ЦБ (~95 руб): ≈ {cost_info['total_cost_usd'] * 95:.2f} руб")

    # 3. Отправка запроса к GPT
    print("\n3. ОТПРАВКА ЗАПРОСА К GPT...")
    try:
        gpt = GPTClient()

        response = gpt.chat_completion(
            messages=[
                {"role": "system", "content": "Ты - эксперт по Wildberries. Отвечай только JSON."},
                {"role": "user", "content": prompt}
            ],
            model=model_id,
            temperature=0.2  # Низкая температура для точности
        )

        # Извлекаем ответ
        if "choices" in response and len(response["choices"]) > 0:
            gpt_response = response["choices"][0]["message"]["content"]

            # Получаем реальное количество токенов
            usage = response.get("usage", {})
            actual_tokens = {
                "prompt": usage.get("prompt_tokens", 0),
                "completion": usage.get("completion_tokens", 0),
                "total": usage.get("total_tokens", 0)
            }

            # Пересчитываем стоимость с реальными токенами
            if actual_tokens["completion"] > 0:
                actual_cost = calculate_request_cost(model_id, prompt, actual_tokens["completion"])

            print(f"\n4. РЕЗУЛЬТАТ ОТ GPT:")
            print("-" * 60)

            # Парсим JSON ответ
            try:
                # Очищаем ответ от markdown
                if gpt_response.startswith("```json"):
                    gpt_response = gpt_response[7:]
                if gpt_response.startswith("```"):
                    gpt_response = gpt_response[3:]
                if gpt_response.endswith("```"):
                    gpt_response = gpt_response[:-3]

                mapped_data = json.loads(gpt_response.strip())

                print("\n=== ЗАПОЛНЕННЫЕ ПОЛЯ WILDBERRIES ===\n")
                for field, value in mapped_data.items():
                    print(f"{field:15} : {value}")

                print("\n" + "-" * 60)
                print("\n=== СТАТИСТИКА ===\n")
                print(f"Фактические токены:")
                print(f"  Вход:  {actual_tokens['prompt']}")
                print(f"  Выход: {actual_tokens['completion']}")
                print(f"  Всего: {actual_tokens['total']}")

                if 'actual_cost' in locals():
                    print(f"\nФактическая стоимость:")
                    print(f"  ${actual_cost['total_cost_usd']:.6f} USD")
                    print(f"  ≈ {actual_cost['total_cost_usd'] * 95:.2f} руб")

                return {
                    "success": True,
                    "model": model_id,
                    "raw_response": gpt_response,
                    "mapped_data": mapped_data,
                    "tokens": actual_tokens,
                    "cost_usd": actual_cost['total_cost_usd'] if 'actual_cost' in locals() else cost_info[
                        'total_cost_usd']
                }

            except json.JSONDecodeError as e:
                print(f"Ошибка парсинга JSON: {e}")
                print(f"\nСырой ответ GPT:\n{gpt_response}")
                return {
                    "success": False,
                    "error": "JSON parsing error",
                    "raw_response": gpt_response
                }
        else:
            print("Ошибка: пустой ответ от GPT")
            return {"success": False, "error": "Empty response"}

    except Exception as e:
        print(f"Ошибка при запросе: {e}")
        return {"success": False, "error": str(e)}


# ============================================================
# 6. СРАВНЕНИЕ С ДРУГИМИ МОДЕЛЯМИ
# ============================================================

def compare_models() -> Dict[str, Any]:
    """Сравнение стоимости запроса на разных моделях"""

    models_to_test = [
        "gpt-5.4",
        "gpt-5.4-pro",
        "gpt-5.4-mini",
        "gpt-4o",
        "claude-opus-4.6",
        "deepseek-3.2"
    ]

    results = []
    prompt = create_mapping_prompt(RAW_LUSTER_DATA, WB_TARGET_SCHEMA)
    prompt_tokens = len(prompt) // 4

    print("\n" + "=" * 70)
    print("СРАВНЕНИЕ СТОИМОСТИ ЗАПРОСА НА РАЗНЫХ МОДЕЛЯХ")
    print("=" * 70)
    print(f"{'Модель':<20} {'Цена входа':<12} {'Цена выхода':<12} {'Стоимость':<12} {'Стоимость руб':<12}")
    print("-" * 70)

    for model_id in models_to_test:
        try:
            cost = calculate_request_cost(model_id, prompt, response_tokens=500)
            results.append(cost)

            print(f"{model_id:<20} ${cost['cost_context_per_1k']:<10.4f} ${cost['cost_completion_per_1k']:<10.4f} "
                  f"${cost['total_cost_usd']:<10.6f} ≈ {cost['total_cost_usd'] * 95:<10.2f} руб")
        except Exception as e:
            print(f"{model_id:<20} {'Ошибка':<12} {'Ошибка':<12} {'Ошибка':<12} {'Ошибка':<12}")

    return {"results": results}


# ============================================================
# 7. ЗАПУСК ТЕСТА
# ============================================================

if __name__ == "__main__":
    print("\n" + "🔥" * 30)
    print("ТЕСТИРОВАНИЕ МАППИНГА ХАРАКТЕРИСТИК ЛЮСТРЫ ЧЕРЕЗ GPT-5.4")
    print("🔥" * 30)

    # Тест на GPT-5.4
    result = test_gpt_mapping("gpt-5.4")

    # # Опционально: сравнение моделей
    # print("\n" + "📊" * 30)
    # compare_models()

    # Вывод итогов
    print("\n" + "✅" * 30)
    if result.get("success"):
        print("ТЕСТ УСПЕШНО ЗАВЕРШЕН!")
        print(f"Затрачено: ${result.get('cost_usd', 0):.6f} USD")
        print(f"≈ {result.get('cost_usd', 0) * 95:.2f} рублей")
    else:
        print("ТЕСТ ЗАВЕРШЕН С ОШИБКОЙ")
        print(f"Ошибка: {result.get('error')}")