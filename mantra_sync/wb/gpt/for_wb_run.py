import json

from core.db.connection import get_db_session
from core.db.models import (
    GPTModels,
    WBNormalizedProduct,
    ParserCharacteristics,
    WBCharacteristic, GPTChatLog
)

from wb.gpt.gpt_product_selector import GPTProductSelector
from wb.gpt.gpt_prompt_builder import GPTPromptBuilder
from wb.gpt.gpt_client import GPTClient
from wb.gpt.classes import GPTLogWriter
from wb.gpt.wb_normalized_writer import WBNormalizedWriter



# -------------------------------------------------
# MODEL SELECTION
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
# LOAD PRODUCT DATA (FIXED ORM)
# -------------------------------------------------

def load_product_data(db, product: WBNormalizedProduct):

    characteristics_rows = (
        db.query(ParserCharacteristics)
        .filter(ParserCharacteristics.product_id_ms == product['product_id_ms'])
        .all()
    )

    characteristics = [
        {
            "value": c.value,
            "group": c.group.name if c.group else "unknown"
        }
        for c in characteristics_rows
    ]

    wb_chars = (
        db.query(WBCharacteristic)
        .filter(WBCharacteristic.subject_id == product['subject_id'])
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
# MAIN PIPELINE
# -------------------------------------------------

def run_test():
    print("\n" + "=" * 60)
    print("🚀 GPT PIPELINE (PRODUCTION MODE)")
    print("=" * 60)

    model_id = select_model()
    print(f"\n✅ Selected model: {model_id}")

    selector = GPTProductSelector()
    products = selector.select_products_interactive()

    if not products:
        print("❌ Нет товаров")
        return

    builder = GPTPromptBuilder()
    client = GPTClient()

    for product in products:

        print("\n" + "-" * 60)
        print(f"PRODUCT: {product['product_id_ms']}")

        with get_db_session() as db:
            try:

                # -------------------------------------------------
                # LOAD DATA
                # -------------------------------------------------
                characteristics, wb_characteristics = load_product_data(db, product)

                # -------------------------------------------------
                # BUILD PROMPT
                # -------------------------------------------------
                prompt = builder.build_prompt(
                    product=product,
                    characteristics=characteristics,
                    wb_characteristics=wb_characteristics
                )

                prompt_text = json.dumps(prompt, ensure_ascii=False)

                print("📤 Sending to model...")

                # -------------------------------------------------
                # GPT CALL
                # -------------------------------------------------
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

                print("📥 Response received")

                # -------------------------------------------------
                # SAVE TO DB
                # -------------------------------------------------

                writer = WBNormalizedWriter()

                # response → распарсить!
                content = response["choices"][0]["message"]["content"]
                gpt_data = json.loads(content)

                writer.save(
                    product_id=product["id"],
                    product_id_ms=product["product_id_ms"],
                    gpt_data=gpt_data
                )


                # -------------------------------------------------
                # SAVE TO DB VIA WRITER
                # -------------------------------------------------

                GPTLogWriter.save(
                    product_id_ms=product['product_id_ms'],
                    response=response
                )

                print("💾 Saved log to DB")

            except Exception as e:

                print(f"❌ ERROR: {e}")

                # можно логировать даже ошибку как отдельный record
                try:
                    GPTLogWriter.save(
                        product_id_ms=product.product_id_ms,
                        response={
                            "id": None,
                            "model": model_id,
                            "object": "error",
                            "created": None,
                            "choices": [{
                                "message": {
                                    "role": "assistant",
                                    "content": None
                                }
                            }],
                            "usage": {},
                            "error": str(e)
                        }
                    )
                except:
                    pass


# -------------------------------------------------
# ENTRY
# -------------------------------------------------

if __name__ == "__main__":
    run_test()