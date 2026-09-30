from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.booking import Booking, BookingStatus
from app.models.centre import Centre, Test


async def create_booking(
    db: AsyncSession, user_id: int, test_id: int, centre_id: int, appointment_time
) -> Booking:
    # Validate centre exists
    centre = await db.get(Centre, centre_id)
    if not centre:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Centre not found")

    # Validate test exists and belongs to the centre
    test = await db.get(Test, test_id)
    if not test or test.centre_id != centre_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Test not found")

    booking = Booking(
        user_id=user_id,
        test_id=test_id,
        centre_id=centre_id,
        appointment_time=appointment_time,
        amount=float(test.price),
        status=BookingStatus.PENDING.value,
    )
    db.add(booking)
    await db.commit()
    await db.refresh(booking)
    return booking


async def get_user_bookings(db: AsyncSession, user_id: int, skip: int = 0, limit: int = 20) -> list[Booking]:
    result = await db.execute(
        select(Booking).where(Booking.user_id == user_id).offset(skip).limit(limit)
    )
    return list(result.scalars().all())


async def get_booking_for_user(db: AsyncSession, booking_id: int, user_id: int) -> Booking:
    booking = await db.get(Booking, booking_id)
    if not booking or booking.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found")
    return booking


async def cancel_booking(db: AsyncSession, booking_id: int, user_id: int) -> Booking:
    booking = await get_booking_for_user(db, booking_id, user_id)

    if booking.status in (BookingStatus.CANCELLED.value, BookingStatus.FAILED.value):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot cancel a booking with status {booking.status}",
        )

    booking.status = BookingStatus.CANCELLED.value
    await db.commit()
    await db.refresh(booking)
    return booking
