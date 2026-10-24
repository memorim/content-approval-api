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
pip install -r requirements.txt
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

## Auth-заглушка

Сервис использует заголовки:

```http
X-Workspace-Id: ws_1
X-User-Id: usr_1
X-Actions: approval:read,approval:create,approval:decide,approval:cancel
```

Права:

| Action | Для чего |
| --- | --- |
| `approval:read` | чтение заявок |
| `approval:create` | создание заявки |
| `approval:decide` | approve/reject |
| `approval:cancel` | cancel |

`workspace_id` в URL должен совпадать с `X-Workspace-Id`, иначе сервис вернёт `403`.

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
  -H 'X-Workspace-Id: ws_1' \
  -H 'X-User-Id: usr_creator' \
  -H 'X-Actions: approval:create,approval:read,approval:decide,approval:cancel' \
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
  -H 'X-Workspace-Id: ws_1' \
  -H 'X-User-Id: usr_1' \
  -H 'X-Actions: approval:read'
```

Поддерживаются query-параметры:

- `status=pending|approved|rejected|cancelled`
- `sourceType=publication|scenario|edit|external`
- `limit=50`
- `offset=0`

### Получить одну заявку

```bash
curl http://localhost:8000/api/v1/workspaces/ws_1/approval-requests/{request_id} \
  -H 'X-Workspace-Id: ws_1' \
  -H 'X-User-Id: usr_1' \
  -H 'X-Actions: approval:read'
```

### Approve

```bash
curl -X POST http://localhost:8000/api/v1/workspaces/ws_1/approval-requests/{request_id}/approve \
  -H 'Content-Type: application/json' \
  -H 'X-Workspace-Id: ws_1' \
  -H 'X-User-Id: usr_reviewer' \
  -H 'X-Actions: approval:decide' \
  -d '{"comment": "Approved"}'
```

### Reject

```bash
curl -X POST http://localhost:8000/api/v1/workspaces/ws_1/approval-requests/{request_id}/reject \
  -H 'Content-Type: application/json' \
  -H 'X-Workspace-Id: ws_1' \
  -H 'X-User-Id: usr_reviewer' \
  -H 'X-Actions: approval:decide' \
  -d '{"reason": "Brand tone is wrong"}'
```

### Cancel

```bash
curl -X POST http://localhost:8000/api/v1/workspaces/ws_1/approval-requests/{request_id}/cancel \
  -H 'Content-Type: application/json' \
  -H 'X-Workspace-Id: ws_1' \
  -H 'X-User-Id: usr_creator' \
  -H 'X-Actions: approval:cancel' \
  -d '{"reason": "Draft was removed"}'
```

## Гарантии сервиса

- заявки из одного workspace недоступны из другого workspace;
- повтор создания заявки не создаёт дубль;
- после финального статуса `approved/rejected/cancelled` заявка не может перейти в другой финальный статус;
- успешные изменения пишутся в `audit_logs`;
- будущие интеграционные события сохраняются в `outbox_events`;
- входные схемы запрещают лишние поля, а payload аудита/событий проходит через redaction чувствительных ключей.
