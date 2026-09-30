from unittest.mock import patch

import pytest
from httpx import AsyncClient


async def _setup_pending_booking(client: AsyncClient, auth_header: dict) -> int:
    """Helper: create a centre, test, and pending booking. Returns booking_id."""
    resp = await client.post(
        "/centres/",
        json={"name": "Lab", "location": "Delhi"},
        headers=auth_header,
    )
    centre_id = resp.json()["id"]
    resp = await client.post(
        f"/centres/{centre_id}/tests",
        json={"name": "CBC", "price": 500.0},
        headers=auth_header,
    )
    test_id = resp.json()["id"]
    resp = await client.post(
        "/bookings/",
        json={
            "test_id": test_id,
            "centre_id": centre_id,
            "appointment_time": "2099-06-15T10:00:00Z",
        },
        headers=auth_header,
    )
    return resp.json()["id"]


@pytest.mark.asyncio
async def test_simulate_payment(client: AsyncClient, auth_header: dict):
    booking_id = await _setup_pending_booking(client, auth_header)
    resp = await client.post(
        "/payments/",
        json={"booking_id": booking_id},
        headers=auth_header,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] in ("SUCCESS", "FAILED")
    assert data["booking_id"] == booking_id

    # Booking status should now be CONFIRMED or FAILED
    resp = await client.get(f"/bookings/{booking_id}", headers=auth_header)
    booking_status = resp.json()["status"]
    if data["status"] == "SUCCESS":
        assert booking_status == "CONFIRMED"
    else:
        assert booking_status == "FAILED"


@pytest.mark.asyncio
async def test_payment_cancelled_booking(client: AsyncClient, auth_header: dict):
    """Paying for a CANCELLED booking → 400."""
    booking_id = await _setup_pending_booking(client, auth_header)

    # Cancel it first
    await client.post(f"/bookings/{booking_id}/cancel", headers=auth_header)

    resp = await client.post(
        "/payments/",
        json={"booking_id": booking_id},
        headers=auth_header,
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_payment_confirmed_booking(client: AsyncClient, auth_header: dict):
    """Paying for an already CONFIRMED booking → 400."""
    booking_id = await _setup_pending_booking(client, auth_header)

    # Force a SUCCESS payment via webhook
    await client.post(
        "/payments/webhook/",
        json={"event_id": "evt-confirm", "booking_id": booking_id, "status": "SUCCESS"},
    )

    resp = await client.post(
        "/payments/",
        json={"booking_id": booking_id},
        headers=auth_header,
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_payment_retry_after_failure(client: AsyncClient, auth_header: dict):
    """Payment retry on a FAILED booking is allowed and can succeed."""
    booking_id = await _setup_pending_booking(client, auth_header)

    # Force a FAILED payment via webhook
    await client.post(
        "/payments/webhook/",
        json={"event_id": "evt-fail-001", "booking_id": booking_id, "status": "FAILED"},
    )

    # Verify booking is FAILED
    resp = await client.get(f"/bookings/{booking_id}", headers=auth_header)
    assert resp.json()["status"] == "FAILED"

    # Retry payment — mock to always succeed
    with patch("app.services.payment_service.random.choices", return_value=["SUCCESS"]):
        resp = await client.post(
            "/payments/",
            json={"booking_id": booking_id},
            headers=auth_header,
        )
    assert resp.status_code == 201
    assert resp.json()["status"] == "SUCCESS"

    # Booking should now be CONFIRMED
    resp = await client.get(f"/bookings/{booking_id}", headers=auth_header)
    assert resp.json()["status"] == "CONFIRMED"


@pytest.mark.asyncio
async def test_webhook_creates_payment(client: AsyncClient, auth_header: dict):
    booking_id = await _setup_pending_booking(client, auth_header)
    resp = await client.post(
        "/payments/webhook/",
        json={
            "event_id": "evt-unique-001",
            "booking_id": booking_id,
            "status": "SUCCESS",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["event_id"] == "evt-unique-001"
    assert data["status"] == "SUCCESS"

    # Booking should be CONFIRMED
    resp = await client.get(f"/bookings/{booking_id}", headers=auth_header)
    assert resp.json()["status"] == "CONFIRMED"


@pytest.mark.asyncio
async def test_webhook_idempotency(client: AsyncClient, auth_header: dict):
    """Sending the same event_id twice → second call is a no-op, 200, same result."""
    booking_id = await _setup_pending_booking(client, auth_header)

    payload = {
        "event_id": "evt-idempotent-001",
        "booking_id": booking_id,
        "status": "SUCCESS",
    }

    # First call
    resp1 = await client.post("/payments/webhook/", json=payload)
    assert resp1.status_code == 200
    data1 = resp1.json()

    # Second call — same event_id
    resp2 = await client.post("/payments/webhook/", json=payload)
    assert resp2.status_code == 200
    data2 = resp2.json()

    # Same payment returned
    assert data1["id"] == data2["id"]
    assert data1["event_id"] == data2["event_id"]

    # Booking status unchanged from the first call
    resp = await client.get(f"/bookings/{booking_id}", headers=auth_header)
    assert resp.json()["status"] == "CONFIRMED"


@pytest.mark.asyncio
async def test_webhook_nonexistent_booking(client: AsyncClient):
    resp = await client.post(
        "/payments/webhook/",
        json={
            "event_id": "evt-no-booking",
            "booking_id": 999,
            "status": "SUCCESS",
        },
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_webhook_cancelled_booking_not_revived(client: AsyncClient, auth_header: dict):
    """Webhook SUCCESS on a cancelled booking must not change booking status."""
    booking_id = await _setup_pending_booking(client, auth_header)

    # Cancel the booking
    await client.post(f"/bookings/{booking_id}/cancel", headers=auth_header)

    # Webhook arrives after cancellation
    resp = await client.post(
        "/payments/webhook/",
        json={
            "event_id": "evt-late-webhook",
            "booking_id": booking_id,
            "status": "SUCCESS",
        },
    )
    assert resp.status_code == 200

    # Booking must still be CANCELLED
    resp = await client.get(f"/bookings/{booking_id}", headers=auth_header)
    assert resp.json()["status"] == "CANCELLED"
