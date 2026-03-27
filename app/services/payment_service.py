from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.messaging.schemas import PaymentProcessingMessage
from app.messaging.topology import PAYMENTS_NEW_ROUTING_KEY
from app.models.enums import PaymentStatus
from app.models.outbox import OutboxEvent
from app.models.payment import Payment
from app.models.base import utcnow
from app.schemas.payment import (
    CreatePaymentRequest,
    PaymentAcceptedResponse,
    PaymentDetailsResponse,
)


class PaymentService:
    async def create_payment(
        self,
        session: AsyncSession,
        payload: CreatePaymentRequest,
        idempotency_key: str,
    ) -> Payment:
        payment = Payment(
            amount=payload.amount,
            currency=payload.currency,
            description=payload.description,
            metadata_payload=payload.metadata,
            status=PaymentStatus.PENDING,
            idempotency_key=idempotency_key,
            webhook_url=str(payload.webhook_url),
        )

        try:
            async with session.begin():
                existing = await self._get_by_idempotency_key(session, idempotency_key)
                if existing is not None:
                    return existing

                session.add(payment)
                await session.flush()

                event = PaymentProcessingMessage(
                    event_id=uuid.uuid4(),
                    payment_id=payment.id,
                    idempotency_key=idempotency_key,
                    attempt=1,
                    created_at=utcnow(),
                )
                session.add(
                    OutboxEvent(
                        aggregate_type="payment",
                        aggregate_id=payment.id,
                        event_type="payment.created",
                        routing_key=PAYMENTS_NEW_ROUTING_KEY,
                        payload=event.model_dump(mode="json"),
                    )
                )
        except IntegrityError:
            await session.rollback()
            existing = await self._get_by_idempotency_key(session, idempotency_key)
            if existing is not None:
                return existing
            raise

        await session.refresh(payment)
        return payment

    async def get_payment(self, session: AsyncSession, payment_id: uuid.UUID) -> Payment | None:
        return await session.get(Payment, payment_id)

    async def _get_by_idempotency_key(
        self,
        session: AsyncSession,
        idempotency_key: str,
    ) -> Payment | None:
        result = await session.execute(
            select(Payment).where(Payment.idempotency_key == idempotency_key)
        )
        return result.scalar_one_or_none()

    @staticmethod
    def to_accepted_response(payment: Payment) -> PaymentAcceptedResponse:
        return PaymentAcceptedResponse(
            payment_id=payment.id,
            status=payment.status,
            created_at=payment.created_at,
        )

    @staticmethod
    def to_details_response(payment: Payment) -> PaymentDetailsResponse:
        return PaymentDetailsResponse(
            payment_id=payment.id,
            amount=payment.amount,
            currency=payment.currency,
            description=payment.description,
            metadata=payment.metadata_payload,
            status=payment.status,
            idempotency_key=payment.idempotency_key,
            webhook_url=payment.webhook_url,
            created_at=payment.created_at,
            processed_at=payment.processed_at,
            webhook_sent_at=payment.webhook_sent_at,
            webhook_attempts=payment.webhook_attempts,
            last_error=payment.last_error,
        )
