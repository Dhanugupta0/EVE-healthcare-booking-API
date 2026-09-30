from datetime import datetime, timezone

from pydantic import BaseModel, field_validator


class BookingCreate(BaseModel):
    test_id: int
    centre_id: int
    appointment_time: datetime

    @field_validator("appointment_time")
    @classmethod
    def must_be_in_future(cls, v: datetime) -> datetime:
        now = datetime.now(timezone.utc)
        # Make naive datetimes UTC for comparison
        compare = v if v.tzinfo else v.replace(tzinfo=timezone.utc)
        if compare <= now:
            raise ValueError("appointment_time must be in the future")
        return v


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
