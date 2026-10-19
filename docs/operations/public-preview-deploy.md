# Публичный preview Chess Master

Preview работает на `chess.rakhmetzianov.website`. Каждый посетитель получает одноразовый код. После активации браузерная сессия длится 15 минут, хранит не больше одной партии и не видит данные другого посетителя. Compose закреплён за проектом `chessmaster`, поэтому не пересекается с NutriOS в `/srv/nutrios/repo`.

## Ограничения сервера

VPS делит 2 ГБ RAM с NutriOS и портфолио. Production Compose запускает один Celery worker, один поток Stockfish, MultiPV 3 и 0,25 секунды на позицию. Одновременно доступен один engine job. LLM в preview отключён: ключ и LiteLLM endpoint не передаются контейнерам.

PostgreSQL, Redis и API не публикуются наружу. Caddy проксирует только frontend на `127.0.0.1:18081`.

## Подготовка DNS

До правки Caddy создать A-запись:

```text
chess.rakhmetzianov.website.  A  194.87.126.95
```

Проверить с VPS:

```bash
getent ahostsv4 chess.rakhmetzianov.website
```

Адрес должен быть `194.87.126.95`. До этого не включать Caddy route: TLS не сможет подтвердить домен.

## Первый деплой

Все команды выполняются под `deploy`. Не печатать `/srv/chessmaster/.env`.

```bash
sudo install -d -o deploy -g deploy -m 0750 /srv/chessmaster
git clone --origin origin https://github.com/ahruslan17/chessmaster.git /srv/chessmaster/repo
cd /srv/chessmaster/repo
git checkout --detach <RELEASE_SHA>
umask 077
cat > /srv/chessmaster/.env
```

В `.env` записать `POSTGRES_PASSWORD` и `ACCESS_CODE_SECRET`: разные случайные hex-значения длиной не меньше 32 байт. Их можно получить через `openssl rand -hex 32`. Затем сохранить файл и проверить права:

```bash
chmod 600 /srv/chessmaster/.env
docker compose --env-file /srv/chessmaster/.env -f compose.production.yaml config --quiet
```

Собирать по одному образу, чтобы не перегрузить VPS:

```bash
cd /srv/chessmaster/repo
ENV='--env-file /srv/chessmaster/.env'
FILE='-f compose.production.yaml'
docker compose $ENV $FILE build api
docker compose $ENV $FILE build frontend
docker compose $ENV $FILE up -d postgres redis
docker compose $ENV $FILE up -d api
docker compose $ENV $FILE exec -T api uv run alembic upgrade head
docker compose $ENV $FILE up -d celery frontend
docker compose $ENV $FILE ps
```

После DNS добавить содержимое `deploy/caddy/chessmaster.caddy` в `/etc/caddy/Caddyfile`, проверить и применить конфигурацию:

```bash
sudo caddy validate --config /etc/caddy/Caddyfile
sudo systemctl reload caddy
curl --fail --max-time 20 https://chess.rakhmetzianov.website/api/health
```

## Выдать код

Код печатается один раз. По умолчанию неактивированный код действует 24 часа.

```bash
cd /srv/chessmaster/repo
docker compose --env-file /srv/chessmaster/.env -f compose.production.yaml \
  exec -T api uv run python -m app.scripts.create_access_code
```

Передать посетителю только выведенный код. Не передавать cookie, `.env` или пароль БД.

## Проверка и обновление

```bash
curl --fail --max-time 20 https://chess.rakhmetzianov.website/api/health
cd /srv/chessmaster/repo
docker compose --env-file /srv/chessmaster/.env -f compose.production.yaml ps
docker stats --no-stream
```

Для обновления получить точный commit SHA, выполнить `git fetch origin`, `git checkout --detach <SHA>`, последовательно пересобрать `api` и `frontend`, прогнать миграции и поднять сервисы. Не использовать `latest`, не публиковать внутренние порты и не выполнять `down -v`.
