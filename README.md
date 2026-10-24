# Content Approval API — согласование контента

Управляет согласованием контента и надёжной передачей событий получателю.

**Проект:** Самостоятельная разработка.

![CI](https://github.com/memorim/content-approval-api/actions/workflows/ci.yml/badge.svg)

[Пример реального локального запроса и ответа](docs/API_EXAMPLE.md)

## Что работает
- Создание, approve/reject/cancel, фильтрация и журнал аудита.
- Идемпотентные запросы и outbox в транзакции бизнес-операции.
- Worker с арендой события, повторными попытками, dead letter и ручным перезапуском.
- Локальный получатель с дедупликацией либо настроенный HTTPS webhook.

## Стек
Python, FastAPI, SQLAlchemy, Alembic, PostgreSQL/SQLite.

## Запуск и проверка
Python 3.12.14.

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
python -m pip install -c requirements-lock.txt -r requirements.txt
alembic upgrade head
python -m pytest -q
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

## Технические решения
- Схема изменяется через Alembic, включая проверку обновления предыдущего релиза.
- Lease token защищает подтверждение от устаревшего worker.
- Stable event_id и Idempotency-Key позволяют получателю безопасно принимать повторную доставку.

## Подробности
[API, конфигурация и исходные инструкции](docs/TECHNICAL.md).

[Результаты проверки этой версии](docs/VERIFICATION.md).

## Проверки и обновления
CI проверяет проект и ссылки на локальные материалы. Dependabot предлагает обновления зависимостей и Actions. [История изменений](CHANGELOG.md).

[Контракты API и обновление базы](docs/COMPATIBILITY.md): `python tests/check_contract.py && python tests/check_upgrade.py`.
