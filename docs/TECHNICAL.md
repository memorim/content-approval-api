# Content Approval API — согласование контента

Backend-сервис согласования контента перед публикацией.

## Стек

- Python 3.12
- FastAPI
- SQLAlchemy 2
- Alembic migrations
- SQLite для локального запуска или PostgreSQL через Docker Compose
- Pytest

## Быстрый запуск локально через SQLite

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -c requirements-lock.txt -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload
```

По умолчанию используется локальная SQLite-база `approval.db`. При необходимости настройки `DATABASE_URL` и `LOG_LEVEL` можно задать в файле `.env`.

Swagger UI: `http://localhost:8000/docs`

## Запуск через Docker Compose

```bash
docker compose up --build
```

API будет доступен на `http://localhost:8000`.

## Тесты

```bash
pytest -q
```

## Серверная авторизация

API проверяет `Authorization: Bearer <token>`. Заголовки `X-Workspace-Id`, `X-User-Id` и `X-Actions` не задают личность или права. `workspace_id` в URL должен совпадать с пространством, связанным с токеном, иначе ответ — `403`. Без настроенного реестра запрос закрыт (`401`); при недоступной БД авторизации — `503`.

Для локального запуска оператор создаёт отдельные токены:

```bash
export APP_AUTH_DATABASE=/secure/auth.db
python -m app.credentials --database "$APP_AUTH_DATABASE" issue --workspace ws_1 --user usr_creator --actions approval:create,approval:read,approval:cancel
python -m app.credentials --database "$APP_AUTH_DATABASE" issue --workspace ws_1 --user usr_reviewer --actions approval:read,approval:decide
```

Команда показывает секрет один раз. В реестре хранится SHA-256, срок по умолчанию — 30 дней. Передайте каждому участнику только его токен через защищённый канал. Для примеров ниже задайте `CREATOR_TOKEN` и `REVIEWER_TOKEN` в своей оболочке, не сохраняя их в Git или общих журналах. На опубликованном сервере используйте HTTPS.

`revoke HASH` отзывает токен, `disable-user --workspace WS --user USER` отключает пользователя и отзывает его токены в этом пространстве. Повторное включение не восстанавливает отозванные токены. Все процессы должны читать одну постоянную БД авторизации. Альтернативный `APP_AUTH_TOKENS` и порядок выбора реестра описаны в [README](../README.md#серверная-идентификация).

Для PostgreSQL можно хранить этот реестр в той же постоянной базе, что и заявки: после `alembic upgrade head` задайте `APP_AUTH_BACKEND=database`, уберите `APP_AUTH_DATABASE` и замените `--database PATH` на `--application-database` в командах оператора. Новый режим не копирует старый SQLite-реестр автоматически. Подробности — в [README](../README.md#постоянные-токены-в-postgresql).

Права:

| Action | Для чего |
| --- | --- |
| `approval:read` | чтение заявок |
| `approval:create` | создание заявки |
| `approval:decide` | approve/reject |
| `approval:cancel` | cancel |

Права берутся из серверного реестра, а не из запроса клиента.

## Idempotency

Для создания заявки можно передать заголовок:

```http
Idempotency-Key: client-request-123
```

Повторный `POST` с тем же ключом в том же workspace вернёт уже созданную заявку и не создаст дубль.
Если заголовок не передан, сервис строит детерминированный ключ из workspace, пользователя и тела запроса.

## Примеры запросов

### Health

```bash
curl http://localhost:8000/health
curl http://localhost:8000/ready
```

### Создать заявку

```bash
curl -X POST http://localhost:8000/api/v1/workspaces/ws_1/approval-requests \
  -H 'Content-Type: application/json' \
  -H "Authorization: Bearer $CREATOR_TOKEN" \
  -H 'Idempotency-Key: req-001' \
  -d '{
    "sourceType": "publication",
    "sourceId": "pub_123",
    "title": "Instagram reel draft",
    "description": "Needs final approval",
    "reviewerUserIds": ["usr_1", "usr_2"]
  }'
```

### Получить список заявок

```bash
curl http://localhost:8000/api/v1/workspaces/ws_1/approval-requests \
  -H "Authorization: Bearer $REVIEWER_TOKEN"
```

Поддерживаются query-параметры:

- `status=pending|approved|rejected|cancelled`
- `sourceType=publication|scenario|edit|external`
- `limit=50`
- `offset=0`

### Получить одну заявку

```bash
curl http://localhost:8000/api/v1/workspaces/ws_1/approval-requests/{request_id} \
  -H "Authorization: Bearer $REVIEWER_TOKEN"
```

### Approve

```bash
curl -X POST http://localhost:8000/api/v1/workspaces/ws_1/approval-requests/{request_id}/approve \
  -H 'Content-Type: application/json' \
  -H "Authorization: Bearer $REVIEWER_TOKEN" \
  -d '{"comment": "Approved"}'
```

### Reject

```bash
curl -X POST http://localhost:8000/api/v1/workspaces/ws_1/approval-requests/{request_id}/reject \
  -H 'Content-Type: application/json' \
  -H "Authorization: Bearer $REVIEWER_TOKEN" \
  -d '{"reason": "Brand tone is wrong"}'
```

### Cancel

```bash
curl -X POST http://localhost:8000/api/v1/workspaces/ws_1/approval-requests/{request_id}/cancel \
  -H 'Content-Type: application/json' \
  -H "Authorization: Bearer $CREATOR_TOKEN" \
  -d '{"reason": "Draft was removed"}'
```

## Гарантии сервиса

- заявки из одного workspace недоступны из другого workspace;
- повтор создания заявки не создаёт дубль;
- после финального статуса `approved/rejected/cancelled` заявка не может перейти в другой финальный статус;
- успешные изменения пишутся в `audit_logs`;
- будущие интеграционные события сохраняются в `outbox_events`;
- входные схемы запрещают лишние поля, а payload аудита/событий проходит через redaction чувствительных ключей.

## Текущий режим работы
Идентичность и роли задаёт серверный реестр Bearer-токенов; самостоятельная регистрация и OIDC не подключены. Outbox worker доставляет событие в локальный каталог, фиксированный HTTPS webhook либо ntfy. Внешний получатель должен дедуплицировать event_id; публикация в конкретной соцсети — отдельная интеграция. См. [Outbox](OUTBOX.md) и [бесплатные уведомления](FREE_NOTIFICATIONS.md).
