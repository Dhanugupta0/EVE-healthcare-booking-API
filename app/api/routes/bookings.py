from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.schemas.booking import BookingCreate, BookingResponse
from app.services.booking_service import (
    cancel_booking,
    create_booking,
    get_booking_for_user,
    get_user_bookings,
)

router = APIRouter(prefix="/bookings", tags=["bookings"])


@router.post("/", response_model=BookingResponse, status_code=201)
async def create_booking_route(
    payload: BookingCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    booking = await create_booking(
        db,
        user_id=current_user.id,
        test_id=payload.test_id,
        centre_id=payload.centre_id,
        appointment_time=payload.appointment_time,
    )
    return booking


@router.get("/", response_model=list[BookingResponse])
async def list_bookings(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await get_user_bookings(db, current_user.id)


@router.get("/{booking_id}", response_model=BookingResponse)
async def get_booking(
    booking_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await get_booking_for_user(db, booking_id, current_user.id)


@router.post("/{booking_id}/cancel", response_model=BookingResponse)
async def cancel_booking_route(
    booking_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await cancel_booking(db, booking_id, current_user.id)
