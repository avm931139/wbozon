
from settings import Config

API_KEY = Config.API_TOKEN_GPT_TUN
PROMPT = "та же люстра в другом ракурсе для карточки на маркетплейс"

import requests
import base64
import time
import sys
import json



# --- 1. ЗАГРУЗКА И ОТПРАВКА ИЗОБРАЖЕНИЯ (без изменений) ---
try:
    with open("photo.jpeg", "rb") as f:
        img_base64 = base64.b64encode(f.read()).decode('ascii')
        img = f"data:image/jpeg;base64,{img_base64}"
    print("✅ Фото загружено")
except FileNotFoundError:
    print("❌ Файл photo.jpeg не найден")
    sys.exit(1)

# PROMPT = "the same chandelier in a minimalist bedroom with gray walls, soft lighting, photorealistic, 4k"

url = "https://api.fireworks.ai/inference/v1/workflows/accounts/fireworks/models/flux-kontext-pro"
headers = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json"
}
data = {
    "prompt": PROMPT,
    "input_image": img,
    "output_format": "jpeg"
}

print("📤 Отправка запроса на генерацию...")
response = requests.post(url, headers=headers, json=data)

if response.status_code != 200:
    print(f"❌ Ошибка при отправке: {response.status_code}")
    print(f"Текст ошибки: {response.text}")
    sys.exit(1)

result = response.json()
# Используем .get() для безопасного получения ID
request_id = result.get("request_id") or result.get("id")

if not request_id:
    print(f"❌ Не удалось получить ID запроса. Ответ API: {result}")
    sys.exit(1)

print(f"✅ Запрос отправлен. ID задачи: {request_id}")

# --- 2. ОЖИДАНИЕ РЕЗУЛЬТАТА (УЛУЧШЕННЫЙ ОПРОС) ---
# Формируем правильный URL для получения результата, как в документации [citation:1][citation:2]
# Используем POST-запрос на эндпоинт /get_result для нашей модели
result_endpoint = f"https://api.fireworks.ai/inference/v1/workflows/accounts/fireworks/models/flux-kontext-pro/get_result"

print("\n⏳ Ожидание генерации изображения...")

max_attempts = 90  # Увеличим до 90 попыток (1.5 минуты)
for attempt in range(max_attempts):
    time.sleep(1)

    # Отправляем POST-запрос для проверки статуса
    poll_response = requests.post(
        result_endpoint,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {API_KEY}",
        },
        json={"id": request_id}  # ID передается в теле запроса
    )

    # Проверяем, успешно ли выполнился запрос к API
    if poll_response.status_code != 200:
        print(f"⚠️ Ошибка при опросе API (HTTP {poll_response.status_code}), попытка {attempt + 1}/{max_attempts}")
        # Не прерываем, возможно, временная ошибка
        continue

    # Парсим ответ
    poll_result = poll_response.json()
    status = poll_result.get("status")

    # --- Логика обработки статусов ---
    if status == "Ready":
        # Успех! Получаем URL или данные изображения
        image_data_or_url = poll_result.get("result", {}).get("sample")

        if isinstance(image_data_or_url, str) and image_data_or_url.startswith("http"):
            # Скачиваем по URL
            print("✅ Генерация завершена. Скачивание изображения...")
            img_response = requests.get(image_data_or_url)
            with open("result.jpg", "wb") as f:
                f.write(img_response.content)
            print("🎉 Готово! Результат сохранен как 'result.jpg'")
            break

        elif image_data_or_url:
            # Сохраняем из base64
            print("✅ Генерация завершена. Сохранение изображения...")
            with open("result.jpg", "wb") as f:
                f.write(base64.b64decode(image_data_or_url))
            print("🎉 Готово! Результат сохранен как 'result.jpg'")
            break
        else:
            print("❌ Не удалось получить данные изображения из ответа API.")
            print(f"Ответ: {poll_result}")
            break

    elif status in ["Failed", "Error"]:
        # Ошибка генерации
        error_details = poll_result.get('details', 'Неизвестная ошибка')
        print(f"❌ Генерация не удалась. Статус: {status}. Детали: {error_details}")
        break

    elif status in ["Task not found", "Pending"]:
        # Эти статусы ожидаемы, просто ждем дальше
        # Выводим сообщение раз в 5 секунд, чтобы не засорять консоль
        if attempt % 5 == 0:
            print(f"⏳ Статус: '{status}'. Ждем... попытка {attempt + 1}/{max_attempts}")

    elif status in ["Request Moderated", "Content Moderated"]:
        print(f"❌ Запрос или содержимое не прошли модерацию. Статус: {status}")
        break

    else:
        # На случай появления других статусов
        print(f"⚠️ Получен неизвестный статус: '{status}'. Попытка {attempt + 1}/{max_attempts}")
        # Продолжаем ждать, возможно, это временное состояние

# Если цикл завершился без break
else:
    print("\n❌ Превышено максимальное время ожидания. Попробуйте позже или проверьте статус задачи в логах.")
