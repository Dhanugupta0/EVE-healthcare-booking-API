from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import require_admin
from app.models.centre import Centre, Test
from app.models.user import User
from app.schemas.centre import (
    CentreCreate,
    CentreDetailResponse,
    CentreResponse,
    TestCreate,
    TestResponse,
)

router = APIRouter(prefix="/centres", tags=["centres"])


@router.get("/", response_model=list[CentreResponse])
async def list_centres(
    skip: int = 0,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Centre).offset(skip).limit(min(limit, 100)))
    return list(result.scalars().all())


@router.get("/{centre_id}", response_model=CentreDetailResponse)
async def get_centre(centre_id: int, db: AsyncSession = Depends(get_db)):
    centre = await db.get(Centre, centre_id)
    if not centre:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Centre not found")
    return centre


@router.post("/", response_model=CentreResponse, status_code=status.HTTP_201_CREATED)
async def create_centre(
    payload: CentreCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    centre = Centre(name=payload.name, location=payload.location)
    db.add(centre)
    await db.commit()
    await db.refresh(centre)
    return centre


@router.post("/{centre_id}/tests", response_model=TestResponse, status_code=status.HTTP_201_CREATED)
async def add_test(
    centre_id: int,
    payload: TestCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    centre = await db.get(Centre, centre_id)
    if not centre:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Centre not found")

    test = Test(centre_id=centre_id, name=payload.name, price=payload.price)
    db.add(test)
    await db.commit()
    await db.refresh(test)
    return test

