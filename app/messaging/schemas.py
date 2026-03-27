from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class PaymentProcessingMessage(BaseModel):
    event_id: UUID
    payment_id: UUID
    idempotency_key: str
    attempt: int = Field(default=1, ge=1)
    created_at: datetime


class DeadLetterMessage(PaymentProcessingMessage):
    error: str
    failed_at: datetime
