import requests
from settings import Config
# 1. Данные для авторизации
TOKEN = Config.TOKEN_MAX

# 2. ID чата, куда отправить сообщение
CHAT_ID = Config.MAX_ORDER_WB  # Замените на реальный ID

# 3. Адрес для отправки сообщений
url = "https://platform-api.max.ru/messages"


headers = {
    "Authorization": TOKEN,   # <-- Передаем токен в заголовке
    "Content-Type": "application/json"
}
def send_max_groupe(text_mes: str):

    payload = {
        "chat_id": CHAT_ID,
        "text": text_mes
    }

    # 6. Отправляем запрос
    response = requests.post(url, headers=headers, json=payload)

    # 7. Проверяем результат
    if response.status_code == 200:
        print("Сообщение успешно отправлено!")
        print("Ответ от сервера:", response.json())
        print('ОТПРАВИЛ В МАКС!!!')
    else:
        print(f"Ошибка: {response.status_code}")
        print(response.text)
        print('ОШИБКА ОТПРАВИЛ В МАКС!!!')