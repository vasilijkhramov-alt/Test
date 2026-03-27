# Асинхронный сервис процессинга платежей

Микросервис на `FastAPI + SQLAlchemy 2.0 + PostgreSQL + RabbitMQ + FastStream`

Основные настройки:

 `API_KEY` - статический API ключ.

 `DATABASE_URL` - строка подключения к PostgreSQL.

 `RABBITMQ_URL` - строка подключения к RabbitMQ.

 `MAX_PROCESSING_ATTEMPTS=3` - общее количество попыток обработки сообщения.

 `RETRY_BACKOFF_BASE_SECONDS=1` - базовая экспоненциальная задержка.

## Запуск через Docker Compose

```bash
docker compose up --build
```

После старта будут доступны:

- API: [http://localhost:8000/docs](http://localhost:8000/docs)
- RabbitMQ UI: [http://localhost:15672](http://localhost:15672)

RabbitMQ credentials по умолчанию: `guest / guest`

## Миграции

```bash
alembic upgrade head
```

## Примеры API

### Создание платежа

```bash
curl -X POST http://localhost:8000/api/v1/payments \
  -H "Content-Type: application/json" \
  -H "X-API-Key: super-secret-api-key" \
  -H "Idempotency-Key: order-100500" \
  -d '{
    "amount": "199.99",
    "currency": "RUB",
    "description": "Оплата заказа #100500",
    "metadata": {
      "order_id": "100500",
      "customer_id": "42"
    },
    "webhook_url": "https://httpbin.org/post"
  }'
```

Пример ответа:

```json
{
  "payment_id": "1f40d2da-c7c2-4b2f-b4aa-a3452d1ac7ab",
  "status": "pending",
  "created_at": "2026-03-27T00:00:00.000000Z"
}
```

Повторный запрос с тем же `Idempotency-Key` вернет тот же платеж без создания дубля.

### Получение платежа

```bash
curl http://localhost:8000/api/v1/payments/1f40d2da-c7c2-4b2f-b4aa-a3452d1ac7ab \
  -H "X-API-Key: super-secret-api-key"
```

Пример ответа:

```json
{
  "payment_id": "1f40d2da-c7c2-4b2f-b4aa-a3452d1ac7ab",
  "amount": "199.99",
  "currency": "RUB",
  "description": "Оплата заказа #100500",
  "metadata": {
    "order_id": "100500",
    "customer_id": "42"
  },
  "status": "succeeded",
  "idempotency_key": "order-100500",
  "webhook_url": "https://httpbin.org/post",
  "created_at": "2026-03-27T00:00:00.000000Z",
  "processed_at": "2026-03-27T00:00:03.532000Z",
  "webhook_sent_at": "2026-03-27T00:00:03.900000Z",
  "webhook_attempts": 1,
  "last_error": null
}
```
