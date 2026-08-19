import requests
import random
import json
from typing import List, Tuple, Optional


def test_proxy_via_api(proxy_server: str) -> Tuple[bool, dict]:
    """
    Проверяет работоспособность прокси через API proxylin.net

    Args:
        proxy_server: прокси в формате IP:PORT или IP:PORT:USERNAME:PASSWORD

    Returns:
        tuple: (is_working, result_dict)
        result_dict содержит: ip, country, speed, ping, anonymity, type и др.
    """
    try:
        # API endpoint
        api_url = "https://proxylin.net/api-info/"  # POST запрос

        # Формируем запрос
        payload = {
            "proxy_list": [proxy_server]  # список прокси для проверки
        }

        response = requests.post(
            api_url,
            json=payload,
            timeout=30
        )

        if response.status_code == 200:
            result = response.json()
            # Проверяем, что прокси рабочий
            if result.get('status') == 'success' and result.get('working'):
                return True, result
            else:
                return False, result
        else:
            return False, {'error': f'HTTP {response.status_code}'}

    except requests.exceptions.Timeout:
        return False, {'error': 'Timeout'}
    except requests.exceptions.ConnectionError:
        return False, {'error': 'Connection error'}
    except Exception as e:
        return False, {'error': str(e)}


def test_proxy_batch(proxy_list: List[str]) -> List[dict]:
    """
    Проверяет список прокси через API (пакетная проверка)

    Args:
        proxy_list: список прокси в формате IP:PORT или IP:PORT:USERNAME:PASSWORD

    Returns:
        list: список результатов для каждого прокси
    """
    try:
        api_url = "https://proxylin.net/api-info/"

        payload = {
            "proxy_list": proxy_list
        }

        response = requests.post(
            api_url,
            json=payload,
            timeout=60  # больше таймаут для пакетной проверки
        )

        if response.status_code == 200:
            results = response.json()
            return results if isinstance(results, list) else [results]
        else:
            return [{'error': f'HTTP {response.status_code}', 'proxy': p} for p in proxy_list]

    except Exception as e:
        return [{'error': str(e), 'proxy': p} for p in proxy_list]


def get_proxy_list() -> List[str]:
    """
    Возвращает список прокси серверов для тестирования
    """
    return [
        # HTTP/HTTPS прокси (IP:PORT)
        "89.222.132.31:3629",
        "217.150.43.249:8080",
        "38.242.204.27:3128",
        "185.198.27.38:3128",
        "45.12.151.226:2829",
        "54.90.206.52:8080",
        "108.161.135.118:80",
        "162.240.19.30:80",

        # SOCKS5 прокси
        "195.19.50.151:1080",
        "31.43.194.184:1080",
        "147.45.124.220:1080",
        "161.35.82.57:1080",
        "149.28.11.32:1080",
        "5.255.117.250:1080",
        "94.130.16.48:30141",

        # Пример прокси с авторизацией (IP:PORT:USERNAME:PASSWORD)
        # "185.198.27.38:3128:user123:pass456",
    ]


def get_working_proxies(verbose: bool = True) -> List[str]:
    """
    Тестирует все прокси через API и возвращает список рабочих

    Args:
        verbose: выводить подробную информацию

    Returns:
        list: список рабочих прокси
    """
    proxy_list = get_proxy_list()
    working_proxies = []
    results = []

    print(f"🔍 Тестирование {len(proxy_list)} прокси через API...")
    print("-" * 60)

    for i, proxy in enumerate(proxy_list, 1):
        print(f"[{i}/{len(proxy_list)}] Проверка {proxy}...", end=" ")

        is_working, result = test_proxy_via_api(proxy)

        if is_working:
            print("✅ РАБОТАЕТ")
            working_proxies.append(proxy)

            if verbose and result.get('country'):
                print(f"      🌍 Страна: {result.get('country')}")
            if verbose and result.get('speed'):
                print(f"      ⚡ Скорость: {result.get('speed')} мс")
            if verbose and result.get('anonymity'):
                print(f"      🕵️ Анонимность: {result.get('anonymity')}")

            results.append({
                'proxy': proxy,
                'status': 'working',
                'info': result
            })
        else:
            error_msg = result.get('error', 'Неизвестная ошибка')
            print(f"❌ НЕ РАБОТАЕТ ({error_msg})")
            results.append({
                'proxy': proxy,
                'status': 'not_working',
                'error': error_msg
            })

    print("-" * 60)
    print(f"✅ Найдено рабочих прокси: {len(working_proxies)}/{len(proxy_list)}")

    # Сохраняем результаты в файл
    with open('proxy_check_results.json', 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print("💾 Результаты сохранены в proxy_check_results.json")

    return working_proxies


def get_proxie(random_mode: bool = True, verbose: bool = True) -> Optional[str]:
    """
    Возвращает рабочий прокси из списка

    Args:
        random_mode: если True, возвращает случайный рабочий прокси
                    если False, возвращает первый рабочий прокси
        verbose: выводить подробную информацию

    Returns:
        str: рабочий прокси или None
    """
    # Получаем список рабочих прокси
    working_proxies = get_working_proxies(verbose=verbose)

    if not working_proxies:
        print("⚠️ Не найден ни один рабочий прокси")
        return None

    if random_mode:
        selected_proxy = random.choice(working_proxies)
        print(f"🎲 Случайный выбор из {len(working_proxies)} рабочих: {selected_proxy}")
    else:
        selected_proxy = working_proxies[0]
        print(f"📌 Выбран первый рабочий прокси: {selected_proxy}")

    return selected_proxy


def check_single_proxy(proxy_server: str) -> bool:
    """
    Быстрая проверка одного прокси

    Args:
        proxy_server: прокси в формате IP:PORT или IP:PORT:USERNAME:PASSWORD

    Returns:
        bool: True если прокси работает
    """
    is_working, _ = test_proxy_via_api(proxy_server)
    return is_working


def get_proxy_details(proxy_server: str) -> Optional[dict]:
    """
    Получает детальную информацию о прокси

    Returns:
        dict: информация о прокси (страна, скорость, пинг, тип, анонимность)
    """
    is_working, result = test_proxy_via_api(proxy_server)
    if is_working:
        return result
    return None


# Для обратной совместимости со старым кодом
def test_proxy(proxy_server):
    """
    Тестирует работоспособность прокси (обертка для совместимости)

    Returns:
        tuple: (is_working, proxy_server)
    """
    is_working, _ = test_proxy_via_api(proxy_server)
    return is_working, proxy_server


# Пример использования
if __name__ == "__main__":
    # Вариант 1: Получить случайный рабочий прокси
    print("\n" + "=" * 60)
    print("ПОИСК РАБОЧЕГО ПРОКСИ")
    print("=" * 60)

    proxie = get_proxie(random_mode=True, verbose=True)

    if proxie:
        print(f"\n✅ Используем прокси: {proxie}")

        # Получить детальную информацию о прокси
        details = get_proxy_details(proxie)
        if details:
            print(f"   🌍 Страна: {details.get('country')}")
            print(f"   ⚡ Скорость: {details.get('speed')} мс")
            print(f"   🎭 Тип: {details.get('type')}")
            print(f"   🕵️ Анонимность: {details.get('anonymity')}")
    else:
        print("❌ Не удалось найти рабочий прокси")

    # Вариант 2: Проверить конкретный прокси
    print("\n" + "=" * 60)
    test_proxy_single = "89.208.106.138:10808"
    print(f"Проверка прокси {test_proxy_single}...")

    if check_single_proxy(test_proxy_single):
        print("✅ Прокси работает")
    else:
        print("❌ Прокси не работает")