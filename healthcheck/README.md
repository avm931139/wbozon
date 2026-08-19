# Healthcheck и серверный мониторинг

Пакет `healthcheck` выполняет разовую прикладную проверку:

```bash
python -m healthcheck
```

Проверяются:

- активность `wbozon-inventory.service` и `cron.service`/`crond.service`;
- статус последнего запуска `inventory_sync`;
- свежесть последней успешной загрузки относительно `INVENTORY_SYNC_INTERVAL_SECONDS`;
- наличие строк за текущую дату во всех четырёх snapshot-таблицах после 00:15 МСК;
- отправка двух Excel-файлов или предупреждения после `WB_TG_MORNING_TIME + 30 минут`.

При норме команда возвращает код `0`, при любой ошибке — `1`. Новый набор имён неуспешных проверок отправляется в `WB_TG_CHAT_ID` один раз. Пока набор ошибок не изменился, следующие пятиминутные проверки не создают сообщения. После перехода из ошибочного состояния в нормальное отправляется уведомление о восстановлении. История и дедупликация используют `wb_telegram_deliveries`.

Если подключение к PostgreSQL полностью недоступно, команда не может прочитать журнал дедупликации и записать доставку: такая ошибка остаётся в journal и отображается как failed unit.

## systemd

`/etc/systemd/system/wbozon-healthcheck.service`:

```ini
[Unit]
Description=WB/Ozon application healthcheck
After=network-online.target wbozon-inventory.service

[Service]
Type=oneshot
User=wbozon
WorkingDirectory=/home/wbozon/wbozon
EnvironmentFile=/home/wbozon/wbozon/.env
ExecStart=/home/wbozon/wbozon/.venv/bin/python -m healthcheck
```

`/etc/systemd/system/wbozon-healthcheck.timer`:

```ini
[Unit]
Description=Run WB/Ozon healthcheck every 5 minutes

[Timer]
OnBootSec=2min
OnUnitActiveSec=5min
Persistent=true
Unit=wbozon-healthcheck.service

[Install]
WantedBy=timers.target
```

Применение и проверка:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now wbozon-healthcheck.timer
sudo systemctl start wbozon-healthcheck.service
systemctl status wbozon-healthcheck.timer --no-pager
sudo journalctl -u wbozon-healthcheck.service -n 100 --no-pager
```

Если проверки нашли проблему, oneshot-service получает статус `failed`; это ожидаемо. Активный timer продолжает запускать новые проверки и после восстановления следующий запуск завершится успешно.
