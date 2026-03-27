from __future__ import annotations

import logging

from faststream import FastStream
from faststream.middlewares.acknowledgement.config import AckPolicy
from faststream.rabbit import RabbitBroker, RabbitMessage

from app.config import get_settings
from app.db import SessionFactory
from app.messaging.schemas import DeadLetterMessage, PaymentProcessingMessage
from app.messaging.topology import (
    PAYMENTS_DLQ_ROUTING_KEY,
    PAYMENTS_EXCHANGE_NAME,
    declare_topology,
    payments_exchange,
    payments_new_queue,
    retry_routing_key,
)
from app.models.base import utcnow
from app.services.payment_processor import PaymentProcessor

settings = get_settings()
logging.basicConfig(level=settings.log_level)
logger = logging.getLogger(__name__)

broker = RabbitBroker(settings.rabbitmq_url)
application = FastStream(broker)
processor = PaymentProcessor(session_factory=SessionFactory, settings=settings)


@application.on_startup
async def setup_topology() -> None:
    await declare_topology(broker, settings)


@broker.subscriber(
    payments_new_queue(),
    payments_exchange(),
    ack_policy=AckPolicy.MANUAL,
)
async def consume_payment(
    payload: PaymentProcessingMessage,
    message: RabbitMessage,
) -> None:
    try:
        await processor.process(payload)
    except Exception as exc:
        try:
            await route_failed_message(payload, exc)
        except Exception:
            logger.exception("Failed to republish payment message for retry/DLQ")
            await message.nack(requeue=True)
            return

        logger.exception(
            "Payment message handling failed on attempt %s for payment %s",
            payload.attempt,
            payload.payment_id,
        )
        await message.ack()
        return

    await message.ack()


async def route_failed_message(
    payload: PaymentProcessingMessage,
    exc: Exception,
) -> None:
    if payload.attempt >= settings.max_processing_attempts:
        dead_letter = DeadLetterMessage(
            **payload.model_dump(),
            error=str(exc),
            failed_at=utcnow(),
        )
        await broker.publish(
            dead_letter.model_dump(mode="json"),
            exchange=PAYMENTS_EXCHANGE_NAME,
            routing_key=PAYMENTS_DLQ_ROUTING_KEY,
            persist=True,
            message_id=str(dead_letter.event_id),
            timestamp=utcnow(),
            content_type="application/json",
            message_type="payment.failed.final",
        )
        return

    next_payload = payload.model_copy(update={"attempt": payload.attempt + 1})
    await broker.publish(
        next_payload.model_dump(mode="json"),
        exchange=PAYMENTS_EXCHANGE_NAME,
        routing_key=retry_routing_key(next_payload.attempt),
        persist=True,
        message_id=str(next_payload.event_id),
        timestamp=utcnow(),
        content_type="application/json",
        message_type="payment.retry",
    )
