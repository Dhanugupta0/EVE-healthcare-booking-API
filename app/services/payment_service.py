import random
import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.booking import Booking, BookingStatus
from app.models.payment import Payment, PaymentStatus


async def simulate_payment(db: AsyncSession, booking_id: int, user_id: int) -> Payment:
    booking = await db.get(Booking, booking_id)
    if not booking or booking.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found")

    if booking.status not in (BookingStatus.PENDING.value, BookingStatus.FAILED.value):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Payment is only allowed for PENDING or FAILED bookings",
        )

    # Simulate payment outcome — weighted toward success
    payment_status = random.choices(
        [PaymentStatus.SUCCESS.value, PaymentStatus.FAILED.value],
        weights=[0.8, 0.2],
        k=1,
    )[0]

    event_id = str(uuid.uuid4())

    payment = Payment(
        booking_id=booking_id,
        event_id=event_id,
        status=payment_status,
    )

    # Update booking status based on payment outcome
    if payment_status == PaymentStatus.SUCCESS.value:
        booking.status = BookingStatus.CONFIRMED.value
    else:
        booking.status = BookingStatus.FAILED.value

    db.add(payment)
    await db.commit()
    await db.refresh(payment)
    return payment


async def process_webhook(db: AsyncSession, event_id: str, booking_id: int, payment_status: str) -> Payment:
    # Idempotency check: if event_id already exists, return the existing payment
    result = await db.execute(select(Payment).where(Payment.event_id == event_id))
    existing = result.scalar_one_or_none()
    if existing:
        return existing

    # Validate booking exists
    booking = await db.get(Booking, booking_id)
    if not booking:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found")

    # Validate payment status
    if payment_status not in (PaymentStatus.SUCCESS.value, PaymentStatus.FAILED.value):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid payment status"
        )

    # Create payment record regardless of booking state (audit trail)
    payment = Payment(
        booking_id=booking_id,
        event_id=event_id,
        status=payment_status,
    )
    db.add(payment)

    # Do not revive a cancelled booking
    if booking.status != BookingStatus.CANCELLED.value:
        if payment_status == PaymentStatus.SUCCESS.value:
            booking.status = BookingStatus.CONFIRMED.value
        else:
            booking.status = BookingStatus.FAILED.value

    # Single commit covering both writes
    await db.commit()
    await db.refresh(payment)
    return payment

