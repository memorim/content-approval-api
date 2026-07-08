# DESIGN: approval-service

## Назначение сервиса

`approval-service` отвечает только за процесс согласования контента перед публикацией.
Внешние сущности — публикации, сценарии, пользователи и workspace — не реализуются внутри сервиса и передаются только идентификаторами.

## Границы сервиса

Сервис хранит:

- заявку на согласование;
- список reviewer user ids;
- текущее состояние заявки;
- историю успешных изменений;
- outbox-события для будущих интеграций.

Сервис не хранит и не обрабатывает:

- реальные публикации и материалы;
- медиафайлы;
- credentials, токены, signed URLs, provider payloads;
- реальные права пользователей во внешней IAM-системе.

Для локального запуска используется auth-заглушка через HTTP headers.

## Модель данных

### `approval_requests`

Основная таблица заявок.

Ключевые поля:

- `id` — UUID заявки;
- `workspace_id` — изоляция данных по workspace;
- `source_type` — `publication`, `scenario`, `edit`, `external`;
- `source_id` — внешний идентификатор объекта;
- `title`, `description` — описание заявки;
- `status` — `pending`, `approved`, `rejected`, `cancelled`;
- `idempotency_key` — защита от дублей;
- `created_by`, `decided_by` — внешние user ids;
- `decision_comment`, `decision_reason` — итоговое решение;
- timestamps.

Ограничение:

```text
UNIQUE(workspace_id, idempotency_key)
```

### `approval_reviewers`

Список внешних пользователей, назначенных ревьюерами.

### `audit_logs`

След успешных изменений:

- кто изменил;
- какое действие выполнил;
- какой статус был до/после;
- очищенный payload действия;
- время изменения.

### `outbox_events`

Таблица для будущей интеграции через события.
Сейчас события только сохраняются, но не публикуются во внешний брокер.

Примеры типов событий:

- `approval_request.created`
- `approval_request.approved`
- `approval_request.rejected`
- `approval_request.cancelled`

## Обработка повторов

Создание заявки поддерживает idempotency.
Клиент может передать:

```http
Idempotency-Key: client-request-123
```

Если в том же workspace уже есть заявка с таким ключом, сервис возвращает существующую заявку.
Если ключ не передан, он вычисляется из workspace, пользователя и тела запроса. Это защищает от случайного повтора одного и того же запроса, но для создания двух одинаковых заявок клиенту лучше передавать разные idempotency keys.

## State machine

Допустимые переходы:

```text
pending -> approved
pending -> rejected
pending -> cancelled
```

Финальные статусы:

```text
approved, rejected, cancelled
```

Если заявка уже в финальном статусе, повторный `approve/reject/cancel` возвращает `409 Conflict`.

## Изоляция workspace

Все запросы к заявкам фильтруются по `workspace_id` из URL.
Дополнительно auth-заглушка требует, чтобы `X-Workspace-Id` совпадал с `workspace_id` из URL.

## Безопасность данных

Публичные request schemas запрещают лишние поля через `extra="forbid"`.
Для audit/outbox payload используется функция redaction, которая редактирует чувствительные ключи:

- secret;
- token;
- email;
- storage key;
- signed URL;
- provider URL;
- raw provider payload;
- password/credentials.

## Интеграции и события

Выбран паттерн transactional outbox:

1. бизнес-изменение, audit log и outbox event сохраняются в одной транзакции;
2. отдельный worker в будущем сможет читать `outbox_events` с `published=false`;
3. после успешной публикации во внешний брокер событие можно пометить как опубликованное.

Это снижает риск ситуации, когда статус в БД изменился, а событие не было отправлено.

## Известные компромиссы

- Auth реализован как заглушка через headers, без JWT/OAuth/IAM.
- Reviewer ids не валидируются во внешнем user-service.
- Outbox events сохраняются, но не публикуются в реальный брокер.
- Для локального запуска поддержан SQLite, для docker-compose — PostgreSQL.
- При отсутствии `Idempotency-Key` сервис дедуплицирует одинаковые запросы по телу, что удобно для retry, но для намеренного создания идентичных заявок лучше передавать разные ключи.
