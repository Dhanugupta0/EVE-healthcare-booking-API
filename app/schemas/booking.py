from datetime import datetime

from pydantic import BaseModel


class BookingCreate(BaseModel):
    test_id: int
    centre_id: int
    appointment_time: datetime


class BookingResponse(BaseModel):
    id: int
    user_id: int
    test_id: int
    centre_id: int
    appointment_time: datetime
    amount: float
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}
