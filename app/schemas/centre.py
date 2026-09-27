from pydantic import BaseModel


class CentreCreate(BaseModel):
    name: str
    location: str


class TestCreate(BaseModel):
    name: str
    price: float


class TestResponse(BaseModel):
    id: int
    centre_id: int
    name: str
    price: float

    model_config = {"from_attributes": True}


class CentreResponse(BaseModel):
    id: int
    name: str
    location: str

    model_config = {"from_attributes": True}


class CentreDetailResponse(BaseModel):
    id: int
    name: str
    location: str
    tests: list[TestResponse] = []

    model_config = {"from_attributes": True}
