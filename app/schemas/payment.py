from datetime import datetime

from pydantic import BaseModel


class PaymentCreate(BaseModel):
    booking_id: int


class PaymentResponse(BaseModel):
    id: int
    booking_id: int
    event_id: str
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class WebhookPayload(BaseModel):
    event_id: str
    booking_id: int
    status: str
