from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.schemas.payment import PaymentCreate, PaymentResponse, WebhookPayload
from app.services.payment_service import process_webhook, simulate_payment

router = APIRouter(prefix="/payments", tags=["payments"])


@router.post("/", response_model=PaymentResponse, status_code=201)
async def create_payment(
    payload: PaymentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await simulate_payment(db, payload.booking_id, current_user.id)


@router.post("/webhook/", response_model=PaymentResponse)
async def payment_webhook(
    payload: WebhookPayload,
    db: AsyncSession = Depends(get_db),
):
    return await process_webhook(db, payload.event_id, payload.booking_id, payload.status)
