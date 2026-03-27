from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session, require_api_key
from app.schemas.payment import CreatePaymentRequest, PaymentAcceptedResponse, PaymentDetailsResponse
from app.services.payment_service import PaymentService

router = APIRouter(
    prefix="/api/v1/payments",
    tags=["payments"],
    dependencies=[Depends(require_api_key)],
)

payment_service = PaymentService()


@router.post(
    "",
    response_model=PaymentAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_payment(
    payload: CreatePaymentRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
) -> PaymentAcceptedResponse:
    payment = await payment_service.create_payment(session, payload, idempotency_key)
    return payment_service.to_accepted_response(payment)


@router.get(
    "/{payment_id}",
    response_model=PaymentDetailsResponse,
    status_code=status.HTTP_200_OK,
)
async def get_payment(
    payment_id: UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> PaymentDetailsResponse:
    payment = await payment_service.get_payment(session, payment_id)
    if payment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Payment not found",
        )

    return payment_service.to_details_response(payment)
