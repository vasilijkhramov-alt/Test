from __future__ import annotations

from faststream.rabbit import ExchangeType, RabbitBroker, RabbitExchange, RabbitQueue

from app.config import Settings

PAYMENTS_EXCHANGE_NAME = "payments"
PAYMENTS_NEW_QUEUE_NAME = "payments.new"
PAYMENTS_NEW_ROUTING_KEY = "payments.new"
PAYMENTS_DLQ_QUEUE_NAME = "payments.dlq"
PAYMENTS_DLQ_ROUTING_KEY = "payments.dlq"


def payments_exchange() -> RabbitExchange:
    return RabbitExchange(
        PAYMENTS_EXCHANGE_NAME,
        type=ExchangeType.DIRECT,
        durable=True,
    )


def payments_new_queue() -> RabbitQueue:
    return RabbitQueue(
        PAYMENTS_NEW_QUEUE_NAME,
        durable=True,
        routing_key=PAYMENTS_NEW_ROUTING_KEY,
    )


def payments_dlq_queue() -> RabbitQueue:
    return RabbitQueue(
        PAYMENTS_DLQ_QUEUE_NAME,
        durable=True,
        routing_key=PAYMENTS_DLQ_ROUTING_KEY,
    )


def retry_routing_key(attempt: int) -> str:
    return f"payments.retry.{attempt}"


def retry_queue_name(attempt: int) -> str:
    return f"payments.retry.{attempt}"


def retry_delay_ms(settings: Settings, attempt: int) -> int:
    retry_index = attempt - 2
    seconds = settings.retry_backoff_base_seconds * (2**retry_index)
    return seconds * 1000


def payments_retry_queue(settings: Settings, attempt: int) -> RabbitQueue:
    return RabbitQueue(
        retry_queue_name(attempt),
        durable=True,
        routing_key=retry_routing_key(attempt),
        arguments={
            "x-message-ttl": retry_delay_ms(settings, attempt),
            "x-dead-letter-exchange": PAYMENTS_EXCHANGE_NAME,
            "x-dead-letter-routing-key": PAYMENTS_NEW_ROUTING_KEY,
        },
    )


async def _declare_and_bind(
    broker: RabbitBroker,
    exchange: RabbitExchange,
    queue: RabbitQueue,
) -> None:
    declared_queue = await broker.declare_queue(queue)
    declared_exchange = await broker.declare_exchange(exchange)
    await declared_queue.bind(
        declared_exchange,
        routing_key=queue.routing_key or "",
    )


async def declare_topology(broker: RabbitBroker, settings: Settings) -> None:
    exchange = payments_exchange()
    await _declare_and_bind(broker, exchange, payments_new_queue())
    await _declare_and_bind(broker, exchange, payments_dlq_queue())

    for attempt in range(2, settings.max_processing_attempts + 1):
        await _declare_and_bind(
            broker,
            exchange,
            payments_retry_queue(settings, attempt),
        )
