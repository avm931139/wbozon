# VPS: доступ, назначение серверов и эксплуатация

Этот документ — каноническая инструкция по production-инфраструктуре `wbozon`. В нём нет паролей, API-токенов и приватных ключей: они хранятся только у администратора и на соответствующем сервере.

## Карта серверов

| Роль | Адрес | Пользователь приложения | Назначение |
|---|---|---|---|
| Production VPS | `185.105.111.112` | `wbozon` | Код, `.venv`, `.env`, PostgreSQL, все workers, timers, healthcheck и личный операционный бот |
| Legacy Telegram relay | `46.30.47.95` | `wbozon` | Только исходящий SSH/SOCKS-маршрут к Telegram для production VPS |

На production VPS наблюдалось имя `vm643362.eurodir.ru`, на legacy VPS — `vm587513`. Для подключения и unit-файлов каноничны IP-адреса: имя хоста провайдер может изменить.

Старый VPS не является резервной копией приложения и не должен запускать workers. Если он недоступен, синхронизация WB/Ozon/Яндекс Маркета и PostgreSQL продолжают работать, но Telegram-доставки остаются в очереди до восстановления relay.

```text
Администратор ──SSH──→ 185.105.111.112 (production)
                              │
                              ├── HTTPS → WB/Ozon/Яндекс Маркет/GitHub
                              ├── localhost:5432 → PostgreSQL
                              └── localhost:1080 → SSH SOCKS → 46.30.47.95 → Telegram API
```

## Какие доступы нужны и для чего

Не смешивайте три независимых ключа:

1. **Административный SSH-ключ** находится на компьютере администратора. Он нужен для входа как `wbozon` на production VPS. Его публичная часть находится в `/home/wbozon/.ssh/authorized_keys` production-сервера.
2. **GitHub deploy key** при использовании SSH находится на production VPS. Он нужен только для `git pull`; серверу не требуется право записи в репозиторий. Для публичного репозитория достаточно текущего HTTPS remote без ключа.
3. **Telegram relay key** находится на production VPS в `/home/wbozon/.ssh/telegram_relay`. Его публичная часть разрешена пользователю `wbozon` на `46.30.47.95`. Он используется только unit-файлом `wbozon-telegram-relay.service`.

Нельзя копировать приватные ключи в Git, `.env`, документацию или Telegram. Команды диагностики не должны печатать содержимое `.env` и приватных ключей.

## Подключение администратора

С Linux/macOS или Windows OpenSSH:

```bash
ssh wbozon@185.105.111.112
```

Если административный ключ не имеет стандартного имени:

```bash
ssh -i ~/.ssh/wbozon_prod -o IdentitiesOnly=yes wbozon@185.105.111.112
```

Удобный необязательный фрагмент локального `~/.ssh/config`:

```sshconfig
Host wbozon-prod
    HostName 185.105.111.112
    User wbozon
    IdentityFile ~/.ssh/wbozon_prod
    IdentitiesOnly yes
    ServerAliveInterval 30
    ServerAliveCountMax 3
```

Имена файлов здесь — примеры. Не создавайте второй ключ, если рабочий административный ключ уже настроен.

Для администрирования legacy VPS используйте консоль провайдера или отдельный административный ключ. Не используйте для интерактивного входа `telegram_relay`: его доступ может намеренно запрещать shell и PTY.

После входа убедитесь, что это нужный сервер:

```bash
hostname
hostname -I
whoami
pwd
```

Ожидаются пользователь `wbozon` и production-адрес `185.105.111.112`. Рабочий каталог приложения:

```bash
cd /home/wbozon/wbozon
```

`root` используется только для первичной настройки и аварийного восстановления. Прикладные процессы запускаются от `wbozon`; управление systemd и системными файлами выполняется через `sudo`. Пользователь `postgres` используется только для административных команд PostgreSQL.

## Первичная подготовка нового production VPS

Этот раздел нужен только при полной переустановке или переносе на новый VPS. Из консоли провайдера под `root`:

```bash
apt update
apt install -y git python3 python3-venv python3-pip postgresql curl openssh-client nano
adduser wbozon
usermod -aG sudo wbozon
install -d -m 700 -o wbozon -g wbozon /home/wbozon/.ssh
install -m 600 -o wbozon -g wbozon /dev/null /home/wbozon/.ssh/authorized_keys
sudo -u wbozon nano /home/wbozon/.ssh/authorized_keys
```

В `authorized_keys` помещается только публичный административный ключ. До закрытия консоли провайдера проверьте новый вход `ssh wbozon@IP` и работу `sudo` в отдельном терминале.

Создание роли и базы при чистой установке PostgreSQL:

```bash
cd /tmp
sudo -u postgres createuser --pwprompt wbozon
sudo -u postgres createdb --owner=wbozon app_db
```

Пароль роли запишите в `DATABASE_URL` локального `.env`; не передавайте его аргументом командной строки. Если роль или база уже существуют, повторно создавать их не нужно.

Установка проекта от пользователя `wbozon`:

```bash
cd /home/wbozon
git clone https://github.com/avm931139/wbozon.git wbozon
cd /home/wbozon/wbozon
python3 -m venv .venv
./.venv/bin/pip install -r requirements.txt
cp .env.example .env
chmod 600 .env
nano .env
./.venv/bin/python -m alembic upgrade head
```

После заполнения `.env` установите units по [`deploy/systemd/README.md`](../deploy/systemd/README.md). Старый relay-ключ переносите только по защищённому каналу; предпочтительнее создать на новом production VPS новую отдельную пару и заменить её публичную часть на legacy VPS.

## Файлы на production VPS

| Путь | Для чего нужен | Рекомендуемые права |
|---|---|---|
| `/home/wbozon/wbozon` | Git working tree приложения | владелец `wbozon:wbozon` |
| `/home/wbozon/wbozon/.venv` | Python и зависимости | владелец `wbozon:wbozon` |
| `/home/wbozon/wbozon/.env` | пароли БД, API-ключи и Telegram-настройки | `chmod 600` |
| `/home/wbozon/.ssh/telegram_relay` | приватный ключ relay | `chmod 600` |
| `/home/wbozon/.ssh/known_hosts` | проверенный ключ legacy VPS | не должен быть доступен на запись посторонним |
| `/etc/systemd/system/wbozon-*` | установленные service/timer units | изменяются через `sudo` |
| `/home/wbozon/wbozon/logs/wb` | файловые журналы WB | владелец `wbozon:wbozon` |

Проверка прав без вывода секретов:

```bash
stat -c '%a %U:%G %n' /home/wbozon/wbozon/.env /home/wbozon/.ssh/telegram_relay
```

## Доступ production VPS к GitHub

Сначала проверьте текущую схему:

```bash
cd /home/wbozon/wbozon
git remote -v
git status --short
git branch --show-current
```

Для публичного репозитория HTTPS remote подходит для `git pull` и не требует токена. Production-сервер не должен выполнять `git push`.

Если репозиторий станет приватным, создайте на production VPS отдельный read-only deploy key:

```bash
ssh-keygen -t ed25519 -f /home/wbozon/.ssh/github_wbozon -C 'wbozon production deploy key'
chmod 600 /home/wbozon/.ssh/github_wbozon
cat /home/wbozon/.ssh/github_wbozon.pub
```

Публичную часть добавьте в GitHub как Deploy key **без** `Allow write access`. Затем настройте отдельный alias в `/home/wbozon/.ssh/config`:

```sshconfig
Host github-wbozon
    HostName github.com
    User git
    IdentityFile /home/wbozon/.ssh/github_wbozon
    IdentitiesOnly yes
```

После проверки fingerprint GitHub добавьте host key в `known_hosts`, проверьте доступ и только затем измените remote:

```bash
ssh -T git@github-wbozon
git remote set-url origin git@github-wbozon:avm931139/wbozon.git
git fetch origin
```

## PostgreSQL

PostgreSQL работает на production VPS и должен быть доступен приложению локально. Порт `5432` не требуется открывать в интернет. Рабочая база — `app_db`, владелец — `wbozon`; точная строка подключения хранится только в `.env` как `DATABASE_URL`.

Проверки:

```bash
sudo systemctl status postgresql --no-pager
sudo -u postgres psql -d app_db -c '\\conninfo'
cd /home/wbozon/wbozon
./.venv/bin/python -m alembic current
./.venv/bin/python -m alembic heads
```

Сообщение `could not change directory to "/home/wbozon": Permission denied` от команды `sudo -u postgres` не означает ошибку PostgreSQL: системный пользователь `postgres` просто не может войти в домашний каталог `wbozon`. Чтобы не видеть предупреждение, сначала выполните `cd /tmp`.

## Как работает Telegram relay

На production VPS unit [`wbozon-telegram-relay.service`](../deploy/systemd/wbozon-telegram-relay.service) запускает:

```text
ssh -N -D 127.0.0.1:1080 ... wbozon@46.30.47.95
```

Это создаёт SOCKS5-порт **на production VPS**, а не на legacy VPS. Настройка `.env` должна указывать:

```dotenv
WB_TG_PROXY_URL=socks5h://127.0.0.1:1080
```

`OPERATIONS_TG_PROXY_URL` можно не задавать: личный бот использует `WB_TG_PROXY_URL`. Суффикс `socks5h` важен — DNS-имя Telegram разрешается через relay.

Публичный ключ `/home/wbozon/.ssh/telegram_relay.pub` должен быть в `/home/wbozon/.ssh/authorized_keys` на legacy VPS. Для relay-ключа нормально запретить PTY, agent forwarding и X11 forwarding, но TCP forwarding должен остаться разрешён. Сообщение `PTY allocation request failed` при обычном `ssh` ожидаемо для ключа, ограниченного только туннелем; unit использует `-N` и PTY ему не нужен.

Если relay настраивается заново, создайте отдельную пару на production VPS:

```bash
ssh-keygen -t ed25519 -f /home/wbozon/.ssh/telegram_relay -C 'wbozon Telegram relay'
chmod 600 /home/wbozon/.ssh/telegram_relay
cat /home/wbozon/.ssh/telegram_relay.pub
```

Скопируйте только показанную публичную строку в `authorized_keys` пользователя `wbozon` на legacy VPS. Приватный файл остаётся на production VPS.

Из-за `StrictHostKeyChecking=yes` production VPS также должен знать host key `46.30.47.95`. Перед добавлением нового ключа обязательно сравните его fingerprint через консоль провайдера или другой доверенный канал.

Сначала сохраните результат отдельно и сравните fingerprint, затем добавьте ключ от имени `wbozon`:

```bash
ssh-keyscan -H 46.30.47.95 > /tmp/wbozon-relay-hostkey
ssh-keygen -lf /tmp/wbozon-relay-hostkey
cat /tmp/wbozon-relay-hostkey >> /home/wbozon/.ssh/known_hosts
chmod 600 /home/wbozon/.ssh/known_hosts
```

Строку `cat ... >> known_hosts` выполняйте только после совпадения fingerprint. Файл в `/tmp` можно оставить для последующей сверки.

Проверка выполняется **на production VPS**:

```bash
systemctl status wbozon-telegram-relay.service --no-pager -l
sudo journalctl -u wbozon-telegram-relay.service -n 50 --no-pager
ss -lntp | grep '127.0.0.1:1080'
curl --socks5-hostname 127.0.0.1:1080 -I --connect-timeout 10 https://api.telegram.org
```

Ответ Telegram `HTTP/2 302` с переходом на `core.telegram.org/bots` подтверждает работу маршрута. Выполнение этой команды на legacy VPS даст `Connection refused`, потому что порт `1080` слушает только production VPS.

Если журнал показывает `connect to host 46.30.47.95 port 22: Connection refused`, проверяйте SSH на legacy VPS через его консоль:

```bash
sudo systemctl status ssh --no-pager
sudo ss -lntp | grep ':22'
```

После восстановления:

```bash
sudo systemctl restart wbozon-telegram-relay.service
sudo systemctl status wbozon-telegram-relay.service --no-pager -l
```

## Сетевые правила

Минимально необходимая схема:

| Сервер | Направление | Порт | Назначение |
|---|---|---|---|
| Production | входящий | `22/tcp` | административный SSH |
| Production | локальный | `5432/tcp` | PostgreSQL; не открывать наружу |
| Production | локальный | `1080/tcp` | SOCKS relay; слушает только `127.0.0.1` |
| Production | исходящий | `443/tcp` | API маркетплейсов и GitHub HTTPS |
| Production → legacy | исходящий | `22/tcp` | SSH-туннель Telegram |
| Legacy | входящий | `22/tcp` | relay с production и аварийное администрирование |
| Legacy | исходящий | `443/tcp` | Telegram API |

На legacy VPS доступ к SSH для relay желательно ограничить источником `185.105.111.112`, но применяйте такое правило только после проверки отдельного аварийного административного доступа, чтобы не заблокировать себя.

## Обновление приложения

Каждое обновление начинается с проверки рабочей копии:

```bash
ssh wbozon@185.105.111.112
cd /home/wbozon/wbozon
git status --short
git fetch origin
git log --oneline HEAD..origin/master
git pull --ff-only origin master
./.venv/bin/pip install -r requirements.txt
./.venv/bin/python -m alembic upgrade head
```

Если `git status --short` не пуст, не используйте `git reset --hard`: сначала определите владельца и назначение изменений. `.env`, локальные ключи и runtime-логи не должны отслеживаться Git.

Если в коммите изменились systemd units:

```bash
sudo cp deploy/systemd/*.service /etc/systemd/system/
sudo cp deploy/systemd/*.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemd-analyze verify /etc/systemd/system/wbozon-*.service /etc/systemd/system/wbozon-*.timer
```

Перезапускайте только затронутые постоянные workers. Oneshot-задачи безопаснее сначала запустить вручную и проверить их журнал. Полный перечень units и порядок включения находятся в [`deploy/systemd/README.md`](../deploy/systemd/README.md).

## Что нужно хранить вне VPS

Git содержит код и миграции, но не позволяет восстановить production целиком. В защищённом внешнем хранилище должны быть:

- актуальная резервная копия PostgreSQL;
- копия `data/wb/documents/`, если требуется восстановление самих бухгалтерских файлов, а не только их метаданных;
- копия `data/ozon/accounting/`, если требуется восстановление файлов бухгалтерских отчётов Ozon;
- защищённая копия значений `.env` или отдельный реестр всех секретов;
- административный SSH-ключ и доступ к консолям обоих VPS у провайдера;
- доступ владельца к GitHub и BotFather;
- перечень активных API-ключей кабинетов и порядок их отзыва.

Пример создания дампа без вывода данных на экран:

```bash
sudo install -d -m 700 -o postgres -g postgres /var/backups/wbozon
sudo -u postgres pg_dump -Fc -f /var/backups/wbozon/app_db_YYYY-MM-DD.dump app_db
sudo -u postgres pg_restore --list /var/backups/wbozon/app_db_YYYY-MM-DD.dump
```

Замените дату в имени вручную. После проверки скопируйте дамп с VPS в зашифрованное внешнее хранилище. Локальный файл на том же VPS не защищает от потери самого сервера. Восстановление БД является отдельной потенциально разрушительной операцией и должно выполняться только в новую или заранее проверенную целевую базу.

## Что где запускать

| Действие | Где выполнять |
|---|---|
| `git pull`, Alembic, Python-команды приложения | production VPS, пользователь `wbozon`, каталог `/home/wbozon/wbozon` |
| `systemctl`, копирование units | production VPS через `sudo` |
| SQL-проверки приложения | production VPS; обычные — через `DATABASE_URL`, административные — через `sudo -u postgres` |
| Проверка `127.0.0.1:1080` | только production VPS |
| Проверка SSH-порта `22` legacy VPS | legacy VPS через консоль провайдера либо отдельный admin SSH |
| Добавление GitHub deploy key | публичная часть в GitHub, приватная только на production VPS |
| Добавление relay key | публичная часть на legacy VPS, приватная только на production VPS |

## Быстрая проверка production

```bash
cd /home/wbozon/wbozon
git status --short
systemctl list-timers 'wbozon-*' --all
systemctl --no-pager --full status \
  wbozon-wb.service \
  wbozon-inventory@wb.service \
  wbozon-inventory@ozon.service \
  wbozon-inventory@yandex_market.service \
  wbozon-telegram.service \
  wbozon-telegram-relay.service \
  wbozon-operations.timer
sudo systemctl start wbozon-healthcheck.service
sudo journalctl -u wbozon-healthcheck.service -n 100 --no-pager
```

`inactive (dead)` нормально для успешно завершившегося `Type=oneshot`. Постоянные WB, inventory, Telegram scheduler и relay должны быть `active (running)`; timers — `active (waiting)`.

## Аварийные сценарии

- **Legacy VPS недоступен:** не останавливайте marketplace workers. Восстановите SSH/сеть relay; Telegram-очереди повторят доставку.
- **Production VPS недоступен:** legacy VPS не подхватит приложение. Нужны восстановление production или развёртывание на новом сервере из Git, резервной копии PostgreSQL и сохранённого набора секретов.
- **GitHub недоступен:** уже установленный код продолжает работать; отложите обновление.
- **PostgreSQL недоступен:** workers не могут безопасно фиксировать результаты. Сначала восстановите БД, затем проверяйте прикладные сервисы.
- **Скомпрометирован ключ:** удалите его публичную часть из `authorized_keys`/GitHub, создайте отдельную новую пару, обновите конфигурацию и перезапустите только зависимый контур.

После любой аварии сначала запускайте `./.venv/bin/python -m healthcheck` из каталога проекта, затем проверяйте личный операционный дайджест. Не переносите приложение обратно на legacy VPS только ради Telegram: его роль ограничена relay.
