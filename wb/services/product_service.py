from datetime import datetime
from typing import Any

from app.db import SessionLocal
from app.models import (
    WBCharacteristic,
    WBProduct,
    WBProductCharacteristic,
    WBProductDimensions,
    WBProductPhoto,
    WBProductSize,
    WBSizeBarcode,
    WBSubject,
)
from wb.products import ProductsAPI
from wb.repositories.product_repository import ProductRepository


def _parse_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


class ProductService:
    """Loads WB cards and persists their complete catalog structure."""

    def __init__(self):
        self.api = ProductsAPI()

    def sync_from_api(self, **kwargs: Any) -> list[dict[str, Any]]:
        payload = self.api.list(**kwargs)
        if not isinstance(payload, list):
            return []

        with SessionLocal() as session:
            repository = ProductRepository(session)
            for item in payload:
                nm_id = item.get("nmID") or item.get("nmId")
                if nm_id is None:
                    continue

                product = repository.get_by_nm_id(int(nm_id))
                if product is None:
                    product = repository.add(WBProduct(nm_id=int(nm_id)))

                self._update_product(session, product, item)
                # Make shared subjects and characteristics visible to queries
                # used while processing the next card in the same transaction.
                session.flush()

            session.commit()

        return payload

    @staticmethod
    def _update_product(session, product: WBProduct, item: dict[str, Any]) -> None:
        product.imt_id = item.get("imtID")
        product.nm_uuid = item.get("nmUUID")
        product.vendor_code = item.get("vendorCode")
        product.brand = item.get("brand")
        product.title = item.get("title")
        product.description = item.get("description")
        product.need_kiz = bool(item.get("needKiz", False))
        product.kiz_marked = bool(item.get("kizMarked", False))
        product.wb_created_at = _parse_datetime(item.get("createdAt"))
        product.wb_updated_at = _parse_datetime(item.get("updatedAt"))
        product.documents = item.get("documents")
        product.raw_data = item

        subject_wb_id = item.get("subjectID")
        if subject_wb_id is not None:
            subject = session.query(WBSubject).filter_by(wb_id=int(subject_wb_id)).first()
            if subject is None:
                subject = WBSubject(
                    wb_id=int(subject_wb_id),
                    name=item.get("subjectName") or str(subject_wb_id),
                )
                session.add(subject)
            else:
                subject.name = item.get("subjectName") or subject.name
            product.subject = subject

        ProductService._sync_photos(product, item.get("photos") or [])

        dimensions = item.get("dimensions")
        if isinstance(dimensions, dict):
            if product.dimensions is None:
                product.dimensions = WBProductDimensions()
            product.dimensions.width = dimensions.get("width")
            product.dimensions.height = dimensions.get("height")
            product.dimensions.length = dimensions.get("length")
            product.dimensions.weight_brutto = dimensions.get("weightBrutto")
            product.dimensions.is_valid = dimensions.get("isValid")
        else:
            product.dimensions = None

        ProductService._sync_characteristics(session, product, item.get("characteristics") or [])
        ProductService._sync_sizes(session, product, item.get("sizes") or [])

    @staticmethod
    def _sync_photos(product: WBProduct, items: list[Any]) -> None:
        existing = {photo.position: photo for photo in product.photos}
        retained: set[int] = set()
        for position, item in enumerate(items):
            if not isinstance(item, dict):
                continue
            retained.add(position)
            photo = existing.get(position)
            if photo is None:
                photo = WBProductPhoto(position=position)
                product.photos.append(photo)
            photo.big_url = item.get("big")
            photo.c246x328_url = item.get("c246x328")
            photo.c516x688_url = item.get("c516x688")
            photo.hq_url = item.get("hq")
            photo.square_url = item.get("square")
            photo.tm_url = item.get("tm")

        for position, photo in existing.items():
            if position not in retained:
                product.photos.remove(photo)

    @staticmethod
    def _sync_characteristics(session, product: WBProduct, items: list[Any]) -> None:
        existing = {link.characteristic.wb_id: link for link in product.characteristic_values}
        retained: set[int] = set()
        for item in items:
            if not isinstance(item, dict) or item.get("id") is None:
                continue
            wb_id = int(item["id"])
            retained.add(wb_id)
            link = existing.get(wb_id)
            if link is None:
                characteristic = session.query(WBCharacteristic).filter_by(wb_id=wb_id).first()
                if characteristic is None:
                    characteristic = WBCharacteristic(wb_id=wb_id, name=item.get("name") or str(wb_id))
                    session.add(characteristic)
                link = WBProductCharacteristic(characteristic=characteristic)
                product.characteristic_values.append(link)
            link.characteristic.name = item.get("name") or link.characteristic.name
            link.value = item.get("value")

        for wb_id, link in existing.items():
            if wb_id not in retained:
                product.characteristic_values.remove(link)

    @staticmethod
    def _sync_sizes(session, product: WBProduct, items: list[Any]) -> None:
        existing = {size.chrt_id: size for size in product.sizes}
        retained: set[int] = set()
        for item in items:
            if not isinstance(item, dict) or item.get("chrtID") is None:
                continue
            chrt_id = int(item["chrtID"])
            retained.add(chrt_id)
            size = existing.get(chrt_id)
            if size is None:
                size = WBProductSize(chrt_id=chrt_id)
                product.sizes.append(size)
            size.tech_size = item.get("techSize")
            size.wb_size = item.get("wbSize")
            existing_barcodes = {barcode.barcode: barcode for barcode in size.barcodes}
            requested_barcodes = {str(value) for value in item.get("skus") or [] if value}
            for barcode in requested_barcodes - existing_barcodes.keys():
                size.barcodes.append(WBSizeBarcode(barcode=barcode))
            for barcode, instance in existing_barcodes.items():
                if barcode not in requested_barcodes:
                    size.barcodes.remove(instance)

        for chrt_id, size in existing.items():
            if chrt_id not in retained:
                product.sizes.remove(size)
