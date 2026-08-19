"""
Модуль для парсинга vseinstrumenti.ru
Версия с проверкой содержимого на наличие капчи
"""

import json
import time
import logging
import re
from pathlib import Path
from datetime import datetime
from playwright.sync_api import sync_playwright

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


class VseinstrumentiParser:
    def __init__(self, headless=False):
        self.base_url = 'https://www.vseinstrumenti.ru'
        self.headless = headless
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None

    def __enter__(self):
        self._init_browser()
        return self

    def __exit__(self, *args):
        self._close()

    def _init_browser(self):
        """Запуск браузера с реальным профилем Chrome"""
        logger.info("🚀 Запуск Chrome с реальным профилем...")

        # ВАЖНО: Укажите ваш реальный путь к профилю Chrome
        chrome_profile_path = r"C:\Users\rooot\AppData\Local\Google\Chrome\User Data\Default"

        try:
            self.playwright = sync_playwright().start()

            self.context = self.playwright.chromium.launch_persistent_context(
                user_data_dir=chrome_profile_path,
                headless=self.headless,
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--disable-web-security',
                ]
            )

            # Создаем страницу
            if self.context.pages:
                self.page = self.context.pages[0]
            else:
                self.page = self.context.new_page()

            self.page.set_default_timeout(60000)

            logger.info("✅ Браузер с профилем запущен")

        except Exception as e:
            logger.error(f"❌ Ошибка при запуске браузера: {e}")
            raise

    def check_for_captcha(self):
        """
        Проверяет, есть ли на странице капча (по содержимому, а не по URL)
        """
        try:
            # Получаем содержимое страницы
            content = self.page.content()
            content_lower = content.lower()

            # Получаем видимый текст
            visible_text = self.page.evaluate("() => document.body.innerText")
            visible_text_lower = visible_text.lower()

            # Проверяем наличие признаков капчи в содержимом
            captcha_indicators = [
                # 'captcha',
                'just a moment',
                'проверка',
                'security check',
                'подтвердите',
                'verify',
                # 'robot',
                # 'bot',
                'turnstile',
                'cf-turnstile',
                'g-recaptcha',
                'recaptcha'
            ]

            # Проверяем в HTML
            for indicator in captcha_indicators:
                if indicator in content_lower:
                    logger.info(f"🔍 Найден признак капчи в HTML: {indicator}")
                    return True

            # Проверяем в видимом тексте
            for indicator in captcha_indicators:
                if indicator in visible_text_lower:
                    logger.info(f"🔍 Найден признак капчи в тексте: {indicator}")
                    return True

            # Проверяем наличие iframe от reCAPTCHA или Cloudflare
            iframe_check = self.page.evaluate("""
                () => {
                    const iframes = document.querySelectorAll('iframe');
                    for (const iframe of iframes) {
                        const src = iframe.src || '';
                        if (src.includes('captcha') || 
                            src.includes('recaptcha') || 
                            src.includes('turnstile') ||
                            src.includes('challenge')) {
                            return true;
                        }
                    }
                    return false;
                }
            """)

            if iframe_check:
                logger.info("🔍 Найден iframe с капчей")
                return True

            return False

        except Exception as e:
            logger.error(f"❌ Ошибка при проверке капчи: {e}")
            return False

    def wait_for_captcha_solve(self, timeout=180):
        """
        Ждет ручного прохождения капчи пользователем
        """
        logger.info("⏳ Ожидание прохождения капчи...")
        logger.info("=" * 60)
        logger.info("🔴 ВНИМАНИЕ: На странице обнаружена капча!")
        logger.info("✅ Пройдите проверку вручную в открытом окне браузера")
        logger.info("   (нажмите галочку 'Я не робот' или решите задачку)")
        logger.info("⏳ Программа будет ждать до 3 минут")
        logger.info("=" * 60)

        # Делаем скриншот капчи
        try:
            self.page.screenshot(path='captcha_detected.png')
            logger.info("📸 Скриншот капчи сохранен: captcha_detected.png")
        except:
            pass

        start_time = time.time()

        while time.time() - start_time < timeout:
            try:
                # Проверяем, исчезла ли капча
                if not self.check_for_captcha():
                    logger.info("✅ Капча успешно пройдена!")

                    # Делаем скриншот после прохождения
                    try:
                        self.page.screenshot(path='captcha_passed.png')
                        logger.info("📸 Скриншот после капчи: captcha_passed.png")
                    except:
                        pass

                    # Сохраняем состояние
                    self._save_state()
                    return True

            except Exception as e:
                # Игнорируем ошибки во время ожидания
                pass

            # Ждем немного
            time.sleep(2)

            # Показываем прогресс
            elapsed = int(time.time() - start_time)
            if elapsed % 10 == 0:
                print(f"\r⏳ Ожидание прохождения капчи... прошло {elapsed} сек", end='')

        print()
        logger.warning("⚠️ Время ожидания капчи истекло")
        return False

    def check_and_handle_verification(self, target_url):
        """
        Проверяет наличие проверки и ждет её прохождения
        """
        logger.info("🔍 Проверка доступа...")

        try:
            # Переходим на целевой URL
            logger.info(f"🎯 Переход на товар...")
            self.page.goto(target_url, wait_until='domcontentloaded')

            # Даем время на загрузку
            time.sleep(3)

            current_url = self.page.url
            logger.info(f"📍 URL в адресной строке: {current_url}")

            # Проверяем наличие капчи ПО СОДЕРЖИМОМУ
            if self.check_for_captcha():
                logger.warning("⚠️ Обнаружена капча на странице!")
                return self.wait_for_captcha_solve(timeout=180)
            else:
                logger.info("✅ Капчи нет, можно работать")
                self._save_state()
                return True

        except Exception as e:
            logger.error(f"❌ Ошибка при проверке: {e}")
            # В случае ошибки проверяем, может это капча?
            time.sleep(2)
            if self.check_for_captcha():
                return self.wait_for_captcha_solve(timeout=60)
            return False

    def _save_state(self):
        """Сохраняет состояние браузера"""
        try:
            cookies = self.context.cookies()
            with open('chrome_state.json', 'w', encoding='utf-8') as f:
                json.dump({
                    'cookies': cookies,
                    'url': self.page.url
                }, f, indent=2)
            logger.info("💾 Состояние сохранено в chrome_state.json")
        except Exception as e:
            logger.error(f"❌ Ошибка при сохранении состояния: {e}")

    # def parse_product(self, url):
    #     """Парсит карточку товара"""
    #     logger.info(f"🔄 Парсинг товара...")
    #
    #     # try:
    #     #     # Ждем полной загрузки
    #     #     self.page.wait_for_load_state('networkidle', timeout=30000)
    #     #     time.sleep(2)
    #     #
    #     #     # Проверяем, не появилась ли капча снова
    #     #     if self.check_for_captcha():
    #     #         logger.warning("⚠️ Снова обнаружена капча!")
    #     #         if self.wait_for_captcha_solve(timeout=60):
    #     #             # После прохождения пробуем снова
    #     #             self.page.goto(url, wait_until='networkidle')
    #     #             time.sleep(2)
    #     #
    #     #     # Сохраняем HTML для отладки
    #     #     html_content = self.page.content()
    #     #     with open('page_debug.html', 'w', encoding='utf-8') as f:
    #     #         f.write(html_content)
    #     #     logger.info("💾 HTML сохранен в page_debug.html")
    #     #
    #     #     # Делаем скриншот
    #     #     self.page.screenshot(path='page_debug.png')
    #     #     logger.info("📸 Скриншот сохранен в page_debug.png")
    #     #
    #     #     # Извлекаем данные
    #     #     product_data = self.page.evaluate("""
    #     #         () => {
    #     #             const data = {};
    #     #
    #     #             // Название
    #     #             const title = document.querySelector('h1');
    #     #             if (title) data.name = title.innerText.trim();
    #     #
    #     #             // Цена
    #     #             const priceEl = document.querySelector('[data-testid="price"], .price, [itemprop="price"]');
    #     #             if (priceEl) {
    #     #                 data.price = priceEl.innerText.trim().replace(/[^0-9]/g, '');
    #     #             }
    #     #
    #     #             return data;
    #     #         }
    #     #     """)
    #     #
    #     #     product_data['url'] = url
    #     #     product_data['parsed_at'] = datetime.now().isoformat()
    #     #
    #     #     if product_data.get('name'):
    #     #         logger.info(f"✅ Название: {product_data['name'][:50]}...")
    #     #         return product_data
    #     #     else:
    #     #         logger.warning("⚠️ Не удалось извлечь название")
    #     #         return None
    #     #
    #     # except Exception as e:
    #     #     logger.error(f"❌ Ошибка парсинга: {e}")
    #     #     return None
    #     return 1

    def parse_product(self, url):
        """Парсит карточку товара"""
        logger.info(f"🔄 Парсинг товара...")

        try:
            # Ждем полной загрузки
            # self.page.wait_for_load_state('networkidle', timeout=30000)
            time.sleep(5)

            # Проверяем, не появилась ли капча
            if self.check_for_captcha():
                logger.warning("⚠️ Обнаружена капча!")
                if self.wait_for_captcha_solve(timeout=60):
                    # После прохождения пробуем снова
                    self.page.goto(url, wait_until='networkidle')
                    time.sleep(2)

            # Сохраняем HTML для отладки
            html_content = self.page.content()
            with open('page_debug.html', 'w', encoding='utf-8') as f:
                f.write(html_content)
            logger.info("💾 HTML сохранен в page_debug.html")

            # Делаем скриншот
            self.page.screenshot(path='page_debug.png')
            logger.info("📸 Скриншот сохранен в page_debug.png")

            # Извлекаем данные с правильными селекторами
            product_data = self.extract_product_data()

            product_data['url'] = url
            product_data['parsed_at'] = datetime.now().isoformat()

            if product_data.get('name'):
                logger.info(f"✅ Название: {product_data['name'][:50]}...")
                logger.info(f"✅ Найдено характеристик: {len(product_data.get('specifications', {}))}")
                return product_data
            else:
                logger.warning("⚠️ Не удалось извлечь название товара")
                return None

        except Exception as e:
            logger.error(f"❌ Ошибка парсинга: {e}")
            return None

    def extract_product_data(self):
        """
        Извлекает все данные из карточки товара используя стабильные селекторы
        """
        return self.page.evaluate("""
            () => {
                const data = {};

                // ===== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ =====

                function getText(selector) {
                    const el = document.querySelector(selector);
                    return el ? el.innerText.trim() : null;
                }

                function getAttribute(selector, attr) {
                    const el = document.querySelector(selector);
                    return el ? el.getAttribute(attr) : null;
                }

                function getAllTexts(selector) {
                    const els = document.querySelectorAll(selector);
                    return Array.from(els).map(el => el.innerText.trim()).filter(t => t);
                }

                // ===== ОСНОВНАЯ ИНФОРМАЦИЯ =====

                // 1. Название товара (всегда в h1)
                data.name = getText('h1');

                // 2. Код товара - ищем по data-qa
                const codeEl = document.querySelector('[data-qa="product-code"] span');
                if (codeEl) {
                    data.vendor_code = codeEl.innerText.trim();
                }

                // 3. Цена - ищем по data-qa или data-behavior
                const priceSelectors = [
                    '[data-qa="price-now"]',
                    '[data-behavior="price-now"]',
                    '[data-qa="product-price-current"]'
                ];

                for (const selector of priceSelectors) {
                    const el = document.querySelector(selector);
                    if (el) {
                        const priceText = el.innerText.trim();
                        data.price = {
                            raw: priceText,
                            value: priceText.replace(/[^0-9]/g, '')
                        };
                        break;
                    }
                }

                // 4. Рейтинг (скрытое поле)
                const ratingInput = document.querySelector('input[name="rating"]');
                if (ratingInput) {
                    data.rating = ratingInput.value;
                }

                // 5. Отзывы - ищем по data-qa
                const reviewsLink = document.querySelector('[data-qa="responses"]');
                if (reviewsLink) {
                    const reviewsText = reviewsLink.innerText;
                    const match = reviewsText.match(/(\\d+)/);
                    if (match) {
                        data.reviews_count = match[1];
                    }
                }

                // 6. Вопросы - ищем по data-qa
                const questionsLink = document.querySelector('[data-qa="comments"]');
                if (questionsLink) {
                    const questionsText = questionsLink.innerText;
                    const match = questionsText.match(/(\\d+)/);
                    if (match) {
                        data.questions_count = match[1];
                    }
                }

                // ===== ХАРАКТЕРИСТИКИ (СТАБИЛЬНЫЕ DATA-QA) =====

                const specifications = {};

                // Используем data-qa="specification-item" - это стабильно!
                document.querySelectorAll('[data-qa="specification-item"]').forEach(item => {
                    const nameEl = item.querySelector('[data-qa="specification-item-name"]');
                    const valueEl = item.querySelector('[data-qa="specification-item-value"]');

                    if (nameEl && valueEl) {
                        const name = nameEl.innerText.replace(/[\\n\\t]/g, ' ').replace(/\\s+/g, ' ').trim();
                        const value = valueEl.innerText.replace(/[\\n\\t]/g, ' ').replace(/\\s+/g, ' ').trim();
                        if (name && value) {
                            specifications[name] = value;
                        }
                    }
                });

                data.specifications = specifications;

                // ===== ИЗОБРАЖЕНИЯ =====

                const images = [];

                // Основное изображение - ищем по стабильному классу для контейнера
                const mainImageEl = document.querySelector('.yUIzN3 img.image, [data-qa="open-product-image"] img');
                if (mainImageEl) {
                    images.push({
                        url: mainImageEl.src,
                        alt: mainImageEl.alt || 'product image',
                        type: 'main'
                    });
                }

                // Миниатюры в карусели - ищем по стабильному data-qa
                document.querySelectorAll('[data-qa="carousel-image"] .image').forEach(img => {
                    const src = img.src || img.dataset.url;
                    if (src && src.includes('http')) {
                        // Проверяем, не дубликат ли это основного изображения
                        if (!images.some(i => i.url === src)) {
                            images.push({
                                url: src,
                                alt: img.alt || 'thumbnail',
                                type: 'thumbnail'
                            });
                        }
                    }
                });

                data.images = images;

                // ===== ДОКУМЕНТАЦИЯ =====

                const documents = [];

                // Ищем все ссылки на PDF в блоке документации
                document.querySelectorAll('.w2N6l8 a[href*=".pdf"]').forEach(doc => {
                    documents.push({
                        title: doc.innerText.trim() || 'Техническая документация',
                        url: doc.href,
                        type: 'pdf'
                    });
                });

                // Сертификаты (ссылки на внешние сайты или изображения)
                document.querySelectorAll('.w2N6l8 a[target="_blank"]:not([href*=".pdf"])').forEach(cert => {
                    const text = cert.innerText.trim();
                    if (text && (text.includes('Сертификат') || text.includes('сертификат'))) {
                        documents.push({
                            title: text,
                            url: cert.href,
                            type: 'certificate'
                        });
                    }
                });

                // Архив со всеми документами
                const allDocsLink = document.querySelector('.w2N6l8 a[href*="docs_download"]');
                if (allDocsLink) {
                    documents.push({
                        title: 'Все документы',
                        url: allDocsLink.href,
                        type: 'archive'
                    });
                }

                data.documents = documents;


                // ===== ОПИСАНИЕ =====

                // Ищем по стабильному id или data-qa
                const descriptionEl = document.querySelector('#description .lg3mvd, [data-qa="product-description"]');
                if (descriptionEl) {
                    data.description = descriptionEl.innerText.trim();
                }

                // ===== ИНФОРМАЦИЯ ОБ УПАКОВКЕ =====

                const package_info = {};

                // Ищем по тексту "Информация об упаковке"
                const packageSection = document.evaluate(
                    "//h3[contains(text(), 'упаковке')]/following-sibling::p",
                    document,
                    null,
                    XPathResult.ORDERED_NODE_SNAPSHOT_TYPE,
                    null
                );

                for (let i = 0; i < packageSection.snapshotLength; i++) {
                    const p = packageSection.snapshotItem(i);
                    const text = p.innerText.trim();
                    if (text.includes('Вес, кг')) {
                        package_info.weight = text.replace('Вес, кг:', '').trim();
                    } else if (text.includes('Длина, мм')) {
                        package_info.length = text.replace('Длина, мм:', '').trim();
                    } else if (text.includes('Ширина, мм')) {
                        package_info.width = text.replace('Ширина, мм:', '').trim();
                    } else if (text.includes('Высота, мм')) {
                        package_info.height = text.replace('Высота, мм:', '').trim();
                    } else if (text.includes('Единица товара')) {
                        package_info.unit = text.replace('Единица товара:', '').trim();
                    }
                }

                data.package_info = package_info;

                // ===== ТЕГИ И ПОДБОРКИ =====

                const tags = [];
                document.querySelectorAll('.DPC1PM .kttPZ1 a, [data-qa="tag-list"] a').forEach(tag => {
                    tags.push({
                        name: tag.innerText.trim(),
                        url: tag.href
                    });
                });

                data.tags = tags;

                // ===== ССЫЛКИ НА АНАЛОГИ =====

                const analogs = [];
                document.querySelectorAll('#analogs [data-qa="products-tile"]').forEach(tile => {
                    const link = tile.querySelector('a[href*="/product/"]');
                    const price = tile.querySelector('[data-qa="product-price-current"]');
                    if (link) {
                        analogs.push({
                            name: link.getAttribute('title') || link.innerText.trim(),
                            url: link.href,
                            price: price ? price.innerText.trim() : null
                        });
                    }
                });

                data.analogs = analogs;

                // ===== МЕТА-ИНФОРМАЦИЯ =====

                data.url = window.location.href;
                data.parsed_at = new Date().toISOString();

                return data;
            }
        """)
    def _close(self):
        """Закрытие браузера"""
        try:
            if self.context:
                self.context.close()
            if self.playwright:
                self.playwright.stop()
        except:
            pass
        logger.info("👋 Браузер закрыт")

    def parse_products(self, urls, delay=5):
        """
        Парсит несколько товаров по списку URL

        Args:
            urls: список URL товаров для парсинга
            delay: задержка между запросами в секундах (по умолчанию 5)

        Returns:
            list: список результатов парсинга
        """
        results = []
        total = len(urls)

        logger.info(f"📦 Начинаем парсинг {total} товаров")

        for idx, url in enumerate(urls, 1):
            logger.info(f"\n{'=' * 50}")
            logger.info(f"Товар {idx}/{total}")
            logger.info(f"{'=' * 50}")

            try:
                # Переходим на страницу товара
                self.page.goto(url, wait_until='domcontentloaded')
                time.sleep(3)

                # Проверяем капчу
                if self.check_for_captcha():
                    logger.warning("⚠️ Обнаружена капча!")
                    if self.wait_for_captcha_solve(timeout=60):
                        self.page.goto(url, wait_until='domcontentloaded')
                        time.sleep(2)

                # Парсим товар
                product_data = self.parse_product(url)

                if product_data:
                    results.append(product_data)
                    logger.info(f"✅ Товар {idx} успешно распарсен")

                    # Сохраняем промежуточные результаты каждые 5 товаров
                    if idx % 5 == 0:
                        self._save_intermediate_results(results, idx)

                # Задержка между запросами (кроме последнего)
                if idx < total:
                    logger.info(f"⏳ Ожидание {delay} секунд перед следующим запросом...")
                    time.sleep(delay)

            except Exception as e:
                logger.error(f"❌ Ошибка при парсинге товара {idx}: {e}")
                continue

        return results

    def _save_intermediate_results(self, results, index):
        """Сохраняет промежуточные результаты в JSON файл"""
        filename = f'products_partial_{index}.json'
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        logger.info(f"💾 Промежуточные результаты сохранены в {filename}")

def load_urls_from_file(filename='urls.txt'):
    """
    Загружает список URL из текстового файла

    Args:
        filename: путь к файлу с URL (по одному на строку)

    Returns:
        list: список URL
    """
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            urls = [
                line.strip() for line in f
                if line.strip() and not line.startswith('#')
            ]
        logger.info(f"📚 Загружено {len(urls)} URL из {filename}")
        return urls
    except FileNotFoundError:
        logger.warning(f"⚠️ Файл {filename} не найден")
        return []


def main():
    """Главная функция"""
    print("\n" + "=" * 70)
    print("ПАРСЕР vseinstrumenti.ru")
    print("=" * 70)
    print("\n🔹 Программа определит наличие капчи по содержимому страницы")
    print("🔹 Если капча есть - вы её проходите, программа ждет")
    print("🔹 После прохождения данные будут извлечены")
    print("=" * 70 + "\n")

    # Способ 1: Загрузить URL из файла
    urls = load_urls_from_file('urls.txt')

    # Способ 2: Если файла нет, использовать тестовый URL
    if not urls:
        logger.info("📝 Файл urls.txt не найден, используем тестовый URL")
        urls = [
            "https://www.vseinstrumenti.ru/product/svetodiodnyj-prozhektor-feron-ip65-100w-6400k-ll-922-32103-817886/"
        ]

    # Запускаем парсер
    with VseinstrumentiParser(headless=False) as parser:
        # Проверяем доступ и обрабатываем капчу если есть
        if parser.check_and_handle_verification(urls[0]):
            # Парсим все товары
            results = parser.parse_products(urls, delay=5)

            if results:
                # Сохраняем финальные результаты
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                filename = f'all_products_{timestamp}.json'

                with open(filename, 'w', encoding='utf-8') as f:
                    json.dump(results, f, ensure_ascii=False, indent=2)

                print(f"\n✅ Результаты парсинга:")
                print(f"📊 Всего товаров: {len(results)} из {len(urls)}")
                print(f"💾 Результаты сохранены в {filename}")

                # Показываем первый результат для примера
                if results:
                    print(f"\n📋 Пример первого товара:")
                    print(json.dumps(results[0], ensure_ascii=False, indent=2)[:500] + "...")
            else:
                print("\n❌ Не удалось распарсить ни один товар")
        else:
            print("\n❌ Не удалось получить доступ к сайту")

    input("\nНажмите Enter для завершения...")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n👋 Программа остановлена пользователем")
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}")
        import traceback
        traceback.print_exc()