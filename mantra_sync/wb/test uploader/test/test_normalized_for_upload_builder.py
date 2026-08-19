from wb.uploader.normalized_for_upload_builder import NormalizedForUploadBuilder


class MockProduct:
    def __init__(self):
        self.id_ms = "TEST_001"
        self.title = "Test Lamp"
        self.description = "Test description"
        self.brand = "TestBrand"
        self.subject_id = 330

        self.dimensions = {
            "length": 2,
            "width": 3,
            "height": 100,   # специально аномалия
            "weight": 0      # ошибка
        }

        self.characteristics = [
            {"id": 14177449, "name": "Цвет", "value": "Белый"},
            {"id": 14177449, "name": "Цвет", "value": "Белый"},  # дубль
            {"id": 17596, "name": "Материал изделия", "value": "Металл"},
            {"id": 17596, "name": "Материал изделия", "value": "Пластик"},
            {"id": 17596, "name": "Материал изделия", "value": "Пластиковый"},  # дубль
        ]

        self.images = [
            "https://img.lu.ru/1.jpg",
            "https://img.lu.ru/2.jpg",
            "https://img.lu.ru/2.jpg",  # дубль
            " invalid_url ",
        ]


def run_test():
    builder = NormalizedForUploadBuilder()

    product = MockProduct()

    result, validation = builder.build(product)

    print("\n=== RESULT ===")
    print(result)

    print("\n=== VALIDATION ===")
    print("is_valid:", validation.is_valid)
    print("errors:")
    for e in validation.errors:
        print(" -", e)


if __name__ == "__main__":
    run_test()