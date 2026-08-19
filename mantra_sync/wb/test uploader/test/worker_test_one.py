from sqlalchemy.orm import Session
from core.db.connection import get_db_session
from wb.uploader.worker import WBWorker
from wb_prepared_product_service import WBPreparedProductService
from wb_repository import WbRepository


def run_test_one(
    db: Session,
    product_id_ms: str,
    api_token: str = "TEST_TOKEN",
    api_url: str = "https://api-wb-test.ru"
):
    """
    Тестовый запуск pipeline на 1 товаре
    """

    # MOCK repository (чтобы не отправлять в WB)
    class MockWbRepository(WbRepository):
        def process_batch(self, limit: int = 1000):
            return {"mock": True, "message": "WB send skipped (test mode)"}

    wb_repo = MockWbRepository(db, api_token, api_url)
    prepared_service = WBPreparedProductService(db)

    worker = WBWorker(
        db=db,
        wb_repo=wb_repo,
        prepared_service=prepared_service
    )

    print("\n=== START TEST PIPELINE ===")

    # 1. PREPARE ONLY ONE PRODUCT
    try:
        prepared = worker.process_single(product_id_ms)
        print("\n[PREPARED]")
        print("status:", prepared.status)
        print("errors:", prepared.validation_errors)
        print("id:", prepared.id)

    except Exception as e:
        print("\n[ERROR IN PREPARE]")
        print(str(e))
        return

    # 2. SHOW PAYLOAD
    print("\n[PAYLOAD]")
    print(prepared.payload)

    # 3. DRY RUN SEND PHASE
    print("\n=== SEND PHASE (DRY RUN) ===")
    send_result = worker.send_batch(limit=1)

    print(send_result)

    print("\n=== TEST DONE ===")
with get_db_session() as session:
    run_test_one(
        db=session,
        product_id_ms="dd44f127-acae-11ef-0a80-11b900cad7c1"
    )