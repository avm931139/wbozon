# Healthcheck и серверный мониторинг

Пакет `healthcheck` выполняет разовую прикладную проверку:

```bash
python -m healthcheck
```

Проверяются:

- активность отдельных `wbozon-inventory@wb.service`, `wbozon-inventory@ozon.service` и, при настроенных кампаниях, `wbozon-inventory@yandex_market.service`;
- активность `wbozon-wb.service`, Telegram worker, stock timer и, если настроен proxy, SSH relay;
- статус и свежесть последнего успешного запуска inventory отдельно по каждому маркетплейсу;
- наличие строк за текущую дату во всех snapshot-таблицах после 00:15 МСК;
- статус и свежесть обязательных заданий Ozon из `OZON_REQUIRED_TASKS`;
- отправка трёх Excel-файлов или предупреждения после `WB_TG_MORNING_TIME + 30 минут`.

При норме команда возвращает код `0`, при любой ошибке — `1`. Новый набор имён неуспешных проверок отправляется в `WB_TG_CHAT_ID` один раз. Пока набор ошибок не изменился, следующие пятиминутные проверки не создают сообщения. После перехода из ошибочного состояния в нормальное отправляется уведомление о восстановлении. История и дедупликация используют `wb_telegram_deliveries`.

Если подключение к PostgreSQL полностью недоступно, команда не может прочитать журнал дедупликации и записать доставку: такая ошибка остаётся в journal и отображается как failed unit.

Проверки заданий Ozon включаются после установки timers. На текущем VPS обязательный набор совпадает с реально включёнными заданиями:

```dotenv
OZON_REQUIRED_TASKS=products,orders,supplies,daily_sales,finances,ads
```

`ads` требует `OZON_PERFORMANCE_CLIENT_ID` и `OZON_PERFORMANCE_CLIENT_SECRET`.
`communications` пока не является обязательным: Reviews API текущего кабинета
возвращает HTTP 403. После появления доступа его можно включить в timer и список
обязательных задач. Допустимый возраст каждого задания задаётся переменными
`OZON_*_MAX_AGE_SECONDS` из `.env.example`.

## systemd

Готовые `wbozon-healthcheck.service` и `wbozon-healthcheck.timer` находятся в [`deploy/systemd`](../deploy/systemd). Не нужно поддерживать отдельные копии unit-текста в этой документации.

Применение и проверка:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now wbozon-healthcheck.timer
sudo systemctl start wbozon-healthcheck.service
systemctl status wbozon-healthcheck.timer --no-pager
sudo journalctl -u wbozon-healthcheck.service -n 100 --no-pager
```

Если проверки нашли проблему, oneshot-service получает статус `failed`; это ожидаемо. Активный timer продолжает запускать новые проверки и после восстановления следующий запуск завершится успешно.

Нормальный итог ручной проверки заканчивается строкой `SUMMARY: N OK, 0 ERROR` и кодом возврата `0`. Список ближайших Ozon timers печатается перед прикладными проверками только когда на сервере доступен `systemctl`.
