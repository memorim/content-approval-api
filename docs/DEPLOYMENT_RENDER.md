# Размещение Content Approval API на Render

Репозиторий содержит [Render Blueprint](../render.yaml) для бесплатного web-сервиса. Он применяет Alembic-миграции перед стартом и использует PostgreSQL для заявок и постоянного реестра Bearer-токенов.

Blueprint не создаёт базу и не содержит секретов. Укажите `DATABASE_URL` для PostgreSQL и оставьте `APP_AUTH_BACKEND=database`.

## Бесплатная доставка событий

Постоянный worker заменён бесплатным расписанием GitHub Actions в [.github/workflows/outbox.yml](../.github/workflows/outbox.yml). Workflow запускается каждые пять минут и выполняет `python -m app.outbox --once`.

Добавьте в настройках репозитория:

- `CONTENT_APPROVAL_DATABASE_URL`;
- `CONTENT_APPROVAL_NTFY_TOPIC` для бесплатных push-уведомлений;
- либо `CONTENT_APPROVAL_OUTBOX_WEBHOOK_URL` и `CONTENT_APPROVAL_OUTBOX_WEBHOOK_TOKEN` для собственного HTTPS-получателя.

Не задавайте ntfy и webhook одновременно. Тема ntfy должна быть случайной строкой длиной 32–128 символов. Уведомление не содержит контакты и текст заявки; получатель должен дедуплицировать `event_id`.

## Проверка после публикации

1. Откройте HTTPS-адрес Render и убедитесь, что `/ready` отвечает успешно.
2. Выпустите отдельные Bearer-токены для creator и reviewer через `python -m app.credentials --application-database`.
3. Проверьте создание, approve/reject/cancel и повтор с тем же `Idempotency-Key`.
4. Отправьте тестовую заявку и убедитесь, что запись появилась в PostgreSQL.
5. Дождитесь запуска workflow и проверьте, что событие доставлено выбранным каналом.
6. Проверьте повтор после потери ответа и ручной retry dead-letter события.

GitHub Actions и Render Free не требуют платного background worker. Секреты и PostgreSQL нужно настроить владельцу; этот репозиторий не создаёт их автоматически.
