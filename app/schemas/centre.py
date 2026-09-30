from pydantic import BaseModel, Field


class CentreCreate(BaseModel):
    name: str = Field(min_length=1)
    location: str = Field(min_length=1)


class TestCreate(BaseModel):
    name: str = Field(min_length=1)
    price: float = Field(gt=0)


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
