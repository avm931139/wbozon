from typing import Dict, Any, List


class WBMapper:

    def build_card(
        self,
        product,
        characteristics: Dict[str, Any]
    ) -> dict:

        return {
            "vendorCode": product.id_ms,
            "name": product.name,
            "description": product.description or "",
            "brand": product.brand or "NoName",

            "sizes": [
                {
                    "price": int(product.price),
                    "skus": []
                }
            ],

            "characteristics": [
                {
                    "name": str(k),
                    "value": str(v)
                }
                for k, v in (characteristics or {}).items()
            ],

            "images": self._get_images(product)
        }

    def _get_images(self, product) -> List[str]:

        if not product.images:
            return []

        # сортировка по position
        sorted_images = sorted(product.images, key=lambda x: x.position or 0)

        return [img.url for img in sorted_images if img.url]