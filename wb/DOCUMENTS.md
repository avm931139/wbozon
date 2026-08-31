# Документы и бухгалтерия Wildberries

Модуль синхронизирует метаданные документов, локальные файлы и снимки баланса продавца. Он работает отдельной ежедневной oneshot-задачей и не входит в постоянный `wbozon-wb.service`, поэтому сбой Documents API не останавливает остальные WB-контуры.

## Доступы и лимиты

Для одного `WB_API_KEY` должны быть разрешены две категории:

- **Документы** — категории, список и скачивание документов;
- **Финансы** — текущий баланс продавца.

Основные лимиты WB на аккаунт продавца:

| Метод | Интервал | Всплеск |
|---|---:|---:|
| категории, список, один документ | 1 запрос / 10 секунд | 5 запросов |
| пакет до 50 документов | 1 запрос / 5 минут | 5 запросов |
| баланс | 1 запрос / минуту | 1 запрос |

Автоматический worker выбирает не более `WB_DOCUMENT_DOWNLOAD_LIMIT=5` отсутствующих или повреждённых файлов за запуск. Это консервативно соответствует разрешённому всплеску одиночного endpoint. Увеличивать значение следует только после проверки типа токена и фактических ответов API.

## API и данные

`DocumentsAPI` реализует:

- `categories(locale="ru")`;
- `list(begin_time, end_time, ..., limit=50)` со всей offset-пагинацией;
- `download(service_name, extension)`;
- `download_all(documents)` для массива от 1 до 50 ссылок.

Список WB содержит `serviceName`, стабильный ID категории `name`, локализованное название `category`, доступные `extensions`, время `creationTime` и признак `viewed`.

В PostgreSQL используются таблицы:

- `wb_document_categories` — справочник категорий;
- `wb_documents` — метаданные документов;
- `wb_document_files` — отдельная строка на каждый формат документа, путь, размер, SHA-256 и время скачивания;
- `wb_finance_balance_snapshots` — валюта, текущий и доступный к выводу баланс плюс исходный JSON;
- `wb_document_sync_runs` — результаты независимых шагов ежедневного worker.

## Локальные файлы

Корень задаётся `WB_DOCUMENT_STORAGE_DIR`, по умолчанию `data/wb/documents/`. Каталог исключён из Git.

`DocumentStorage` строго декодирует Base64, ограничивает размер, нормализует имя, проверяет сигнатуру PDF, структуру ZIP и обязательные части XLSX, запрещает выход за корень и атомарно заменяет целевой файл. Перед пропуском существующий файл проверяется по размеру и SHA-256.

Один документ может иметь несколько `extensions`; worker скачивает каждый формат независимо. Повреждённый или исчезнувший файл снова попадает в очередь.

Для некоторых документов при запросе логического формата `xlsx` Wildberries
возвращает внешний файл `zip`. Worker принимает только этот известный переход,
проверяет, что архив действительно содержит `.xlsx`, сохраняет ZIP без распаковки,
а в `wb_document_files.extension` оставляет `xlsx`. Поэтому такой файл считается
загруженным и не попадает в бесконечную повторную очередь.

Пакетный endpoint возвращает единый `documents.zip`. Он доступен через `DocumentsAPI.download_all()`, но ежедневный worker намеренно использует одиночный endpoint: так каждый файл однозначно связан с `serviceName + extension` в БД. Пакетный ZIP автоматически не распаковывается.

Локальный каталог не входит в дамп PostgreSQL. Если сами файлы нужны для восстановления, отдельно копируйте `data/wb/documents/` во внешнее защищённое хранилище.

## Ручной запуск

```bash
cd /home/wbozon/wbozon
./.venv/bin/python -m alembic upgrade head
./.venv/bin/python -m wb.document_sync --help
./.venv/bin/python -m wb.document_sync
```

Обычный запуск обновляет последние `WB_DOCUMENT_LOOKBACK_DAYS=90` дней. Первичная загрузка всех доступных метаданных:

```bash
./.venv/bin/python -m wb.document_sync --all-history --download-limit 5
```

Явный период:

```bash
./.venv/bin/python -m wb.document_sync \
  --begin-date 2026-08-01 \
  --end-date 2026-08-31 \
  --download-limit 5
```

Шаги `categories`, `documents`, `balance` и `files` изолированы. Итог `partial` или `failed` возвращает ненулевой код, но успешные шаги остаются зафиксированы. PostgreSQL advisory lock не допускает параллельные запуски.

## Production timer

После успешной ручной проверки:

```bash
sudo cp deploy/systemd/wbozon-wb-documents.service /etc/systemd/system/
sudo cp deploy/systemd/wbozon-wb-documents.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now wbozon-wb-documents.timer
sudo systemctl start wbozon-wb-documents.service
sudo journalctl -u wbozon-wb-documents.service -n 100 --no-pager
```

Timer запускается ежедневно в 04:10 МСК. Только после успешного запуска добавьте в `.env`:

```dotenv
WB_DOCUMENT_SYNC_REQUIRED=true
```

Healthcheck проверит timer и свежесть `wb_document_sync_runs`. Личный операционный бот отправляет результат и расшифровку ошибки независимо от обязательности healthcheck.
