import json

from core.db.connection import get_db_session
from core.db.models import (
    GPTModels,
    WBNormalizedProduct,
    ParserCharacteristics,
    WBCharacteristic
)

from gpt_product_selector import GPTProductSelector
from gpt_prompt_builder import GPTPromptBuilder
from wb.gpt.gpt_client import GPTClient

# -------------------------------------------------
# 1. ВЫБОР МОДЕЛИ
# -------------------------------------------------

def select_model():
    with get_db_session() as db:
        models = (
            db.query(GPTModels)
            .filter(GPTModels.is_active == True)
            .all()
        )

        if not models:
            print("❌ Нет активных моделей")
            return "gpt-5.4"

        print("\n=== AVAILABLE MODELS ===")
        for i, m in enumerate(models, 1):
            print(f"{i}. {m.id} ({m.title})")

        print("\nEnter → gpt-5.4 (default)")

        user_input = input("Select model: ").strip()

        if not user_input:
            return "gpt-5.4"

        if user_input.isdigit():
            idx = int(user_input) - 1
            if 0 <= idx < len(models):
                return models[idx].id

        print("⚠️ fallback → gpt-5.4")
        return "gpt-5.4"


# -------------------------------------------------
# 2. ЗАГРУЗКА ДАННЫХ ТОВАРА
# -------------------------------------------------

def load_product_data(product: WBNormalizedProduct):
    with get_db_session() as db:

        # характеристики товара
        characteristics_rows = (
            db.query(ParserCharacteristics)
            .filter(ParserCharacteristics.product_id_ms == product["product_id_ms"])
            .all()
        )

        characteristics = [
            {
                "value": c.value,
                "group": c.group.name if c.group else None
            }
            for c in characteristics_rows
        ]


        # характеристики WB по subject
        wb_chars = (
            db.query(WBCharacteristic)
            .filter(WBCharacteristic.subject_id == product["subject_id"])
            .all()
        )

        wb_characteristics = [
            {
                "char_id": w.char_id,
                "char_name": w.char_name,
                "type": w.char_type,
                "required": w.is_required,
                "unit": w.unit_name
            }
            for w in wb_chars
        ]


        return characteristics, wb_characteristics


# -------------------------------------------------
# 3. ТЕСТ ПРОМПТА
# -------------------------------------------------

def run_test():
    print("\n" + "=" * 60)
    print("🚀 GPT PIPELINE TEST")
    print("=" * 60)

    # --- модель
    model_id = select_model()
    print(f"\n✅ Selected model: {model_id}")

    # --- товары
    selector = GPTProductSelector()
    products = selector.select_products_interactive()

    if not products:
        print("❌ Нет товаров")
        return

    builder = GPTPromptBuilder()

    client = GPTClient()

    # --- тестируем первые N товаров
    for product in products:
        print("\n" + "-" * 60)
        print(f"PRODUCT: {product['product_id_ms']}")

        try:
            characteristics, wb_characteristics = load_product_data(product)

            prompt = builder.build_prompt(
                product=product,
                characteristics=characteristics,
                wb_characteristics=wb_characteristics
            )

            print('Отправляю в модель')

            prompt_text = json.dumps(prompt, ensure_ascii=False, indent=2)
            prompt_text = 'привет'

            response = client.chat_completion(
                model=model_id,
                messages=[
                    {
                        "role": "user",
                        "content": prompt_text
                    }
                ],
                temperature=0.2
            )

            print(response)

            #
            # print("\n=== PROMPT PREVIEW ===")
            # print(json.dumps(prompt, ensure_ascii=False, indent=2)[:5000])  # ограничим вывод

        except Exception as e:
            print(f"❌ Ошибка: {e}")


# -------------------------------------------------
# ENTRY POINT
# -------------------------------------------------

if __name__ == "__main__":
    run_test()