# Content Approval API — согласование контента

Хранит заявки на публикацию и решения по ним.

**Тип:** Самостоятельный портфолио-проект. Рабочая демонстрационная реализация; коммерческий запуск и использование реальными пользователями не заявляются.

![CI](https://github.com/memorim/content-approval-api/actions/workflows/ci.yml/badge.svg)

[Пример реального локального запроса и ответа](docs/API_EXAMPLE.md)

## Что работает
- Создание, чтение, approve/reject/cancel и фильтрация заявок.
- Идемпотентное создание, журнал аудита и сохранение событий в outbox.
- Проверка workspace и разрешений, схемы входных данных.

## Стек
Python, FastAPI, SQLAlchemy, Alembic, PostgreSQL/SQLite.

## Запуск и проверка
Python 3.12. Для PostgreSQL-варианта — Docker или доступная PostgreSQL.

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
python -m pip install -r requirements.txt
alembic upgrade head
python -m pytest -q
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

## Технические решения
- Схема базы создаётся через Alembic; запуск приложения не создаёт таблицы в обход миграций.
- Тестовые соединения закрываются перед удалением временного SQLite-файла.

## Границы готовности
- Аутентификация — заглушка на доверенных заголовках; напрямую открывать API недоверенным клиентам нельзя.
- Запись в outbox реализована, отправителя событий и интеграции с публикацией нет.
- Права задаются заголовками, полноценный identity-провайдер и проверка JWT не подключены.

## Подробности
[API, конфигурация и исходные инструкции](docs/TECHNICAL.md).

[Результаты проверки этой версии](docs/VERIFICATION.md).
