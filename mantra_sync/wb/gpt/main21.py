
from core.db.connection import get_db_session
from wb_pipeline_runner import WBPipelineRunner
from wb.gpt.service import WBNormalizationService
from settings import Config
from wb.gpt.gpt_client import GPTClient
from core.db.models import ParserProduct


def run_pipeline():
    with get_db_session() as session:
        # 1. GPT CLIENT
        client = GPTClient()

        gpt_service = WBNormalizationService(
            client=client,
            model="gpt-5.4"
        )

        # 2. PIPELINE
        runner = WBPipelineRunner(
            gpt_service=gpt_service,
            session=session
        )

        # 3. ЗАГРУЗКА ТОВАРОВ ИЗ БД
        products = (
            session.query(ParserProduct)
            .filter(ParserProduct.status == "new")
            .limit(2)
            .all()
        )

        print(f"FOUND PRODUCTS: {len(products)}")

        # 4. ОБРАБОТКА
        for p in products:
            try:
                result = runner.run(
                    parser_product=p,
                    domain="market-sveta.ru",
                    site_group=p.site_group  # или как у тебя хранится
                )

                print(f"OK: {p.id_ms}")

                # TODO: сохранить result в БД
                save_to_db(session, result)

            except Exception as e:
                print(f"ERROR: {p.id_ms} -> {e}")

                p.status = "error"
                session.commit()

        session.close()


def save_to_db(session, result: dict):
    product = result["product"]
    characteristics = result["characteristics"]

    # 1. WBNormalizedProduct
    wb_product = WBNormalizedProduct(**product)
    session.add(wb_product)
    session.flush()  # получаем id

    # 2. characteristics
    for c in characteristics:
        session.add(WBNormalizedCharacteristic(
            product_id=wb_product.id,
            **c
        ))

    session.commit()


if __name__ == "__main__":
    run_pipeline()