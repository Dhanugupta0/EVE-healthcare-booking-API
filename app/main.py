from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes import auth, bookings, centres, payments
from app.core.database import Base, engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create all tables on startup
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield


app = FastAPI(
    title="EVE Diagnostics Booking API",
    description="Backend for diagnostic test bookings with simulated payment flow",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(auth.router)
app.include_router(centres.router)
app.include_router(bookings.router)
app.include_router(payments.router)


@app.get("/health")
async def health_check():
    return {"status": "healthy"}
