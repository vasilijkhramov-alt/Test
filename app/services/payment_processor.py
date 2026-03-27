from __future__ import annotations

import asyncio
import random
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.config import Settings
from app.messaging.schemas import PaymentProcessingMessage
from app.models.base import utcnow
from app.models.enums import PaymentStatus
from app.models.payment import Payment
from app.schemas.payment import PaymentWebhookResponse


class PaymentNotFoundError(Exception):
    pass


class WebhookDeliveryError(Exception):
    pass


class PaymentProcessor:
    def __init__(self, *, session_factory: async_sessionmaker, settings: Settings) -> None:
        self._session_factory = session_factory
        self._settings = settings

    async def process(self, message: PaymentProcessingMessage) -> None:
        async with self._session_factory() as session:
            result = await session.execute(
                select(Payment)
                .where(Payment.id == message.payment_id)
                .with_for_update()
            )
            payment = result.scalar_one_or_none()
            if payment is None:
                raise PaymentNotFoundError(f"Payment {message.payment_id} was not found")

            payment.webhook_attempts = max(payment.webhook_attempts, message.attempt)

            try:
                if payment.status == PaymentStatus.PENDING:
                    await self._simulate_gateway_processing(payment)

                if payment.webhook_sent_at is None:
                    await self._send_webhook(payment)
                    payment.webhook_sent_at = utcnow()

                payment.last_error = None
            except Exception as exc:
                payment.last_error = str(exc)
                await session.commit()
                raise

            await session.commit()

    async def _simulate_gateway_processing(self, payment: Payment) -> None:
        delay = random.uniform(
            self._settings.payment_min_delay_seconds,
            self._settings.payment_max_delay_seconds,
        )
        await asyncio.sleep(delay)

        payment.status = (
            PaymentStatus.SUCCEEDED if random.random() <= 0.9 else PaymentStatus.FAILED
        )
        payment.processed_at = utcnow()

    async def _send_webhook(self, payment: Payment) -> None:
        if payment.processed_at is None:
            raise WebhookDeliveryError("Payment was not processed before webhook delivery")

        payload = PaymentWebhookResponse(
            payment_id=payment.id,
            status=payment.status,
            amount=payment.amount,
            currency=payment.currency,
            description=payment.description,
            metadata=payment.metadata_payload,
            processed_at=payment.processed_at,
        )

        async with httpx.AsyncClient(timeout=self._settings.webhook_timeout_seconds) as client:
            response = await client.post(
                payment.webhook_url,
                json=payload.model_dump(mode="json"),
            )

        if response.status_code >= 400:
            raise WebhookDeliveryError(
                f"Webhook responded with HTTP {response.status_code} for payment {payment.id}"
            )

    async def get_payment(self, payment_id: UUID) -> Payment | None:
        async with self._session_factory() as session:
            return await session.get(Payment, payment_id)
