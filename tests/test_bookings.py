import pytest
from httpx import AsyncClient


async def _create_centre_and_test(client: AsyncClient, auth_header: dict) -> tuple[int, int]:
    """Helper: create a centre + test, return (centre_id, test_id)."""
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
    return centre_id, test_id


@pytest.mark.asyncio
async def test_create_booking(client: AsyncClient, auth_header: dict):
    centre_id, test_id = await _create_centre_and_test(client, auth_header)
    resp = await client.post(
        "/bookings/",
        json={
            "test_id": test_id,
            "centre_id": centre_id,
            "appointment_time": "2025-06-15T10:00:00Z",
        },
        headers=auth_header,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "PENDING"
    assert data["amount"] == 500.0  # pulled from test price, not client


@pytest.mark.asyncio
async def test_create_booking_nonexistent_test(client: AsyncClient, auth_header: dict):
    resp = await client.post(
        "/bookings/",
        json={
            "test_id": 999,
            "centre_id": 999,
            "appointment_time": "2025-06-15T10:00:00Z",
        },
        headers=auth_header,
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_list_bookings(client: AsyncClient, auth_header: dict):
    centre_id, test_id = await _create_centre_and_test(client, auth_header)
    await client.post(
        "/bookings/",
        json={
            "test_id": test_id,
            "centre_id": centre_id,
            "appointment_time": "2025-06-15T10:00:00Z",
        },
        headers=auth_header,
    )
    resp = await client.get("/bookings/", headers=auth_header)
    assert resp.status_code == 200
    assert len(resp.json()) == 1


@pytest.mark.asyncio
async def test_get_booking(client: AsyncClient, auth_header: dict):
    centre_id, test_id = await _create_centre_and_test(client, auth_header)
    resp = await client.post(
        "/bookings/",
        json={
            "test_id": test_id,
            "centre_id": centre_id,
            "appointment_time": "2025-06-15T10:00:00Z",
        },
        headers=auth_header,
    )
    booking_id = resp.json()["id"]
    resp = await client.get(f"/bookings/{booking_id}", headers=auth_header)
    assert resp.status_code == 200
    assert resp.json()["id"] == booking_id


@pytest.mark.asyncio
async def test_get_other_users_booking(client: AsyncClient, auth_header: dict):
    """Viewing another user's booking returns 404, not 403."""
    centre_id, test_id = await _create_centre_and_test(client, auth_header)
    resp = await client.post(
        "/bookings/",
        json={
            "test_id": test_id,
            "centre_id": centre_id,
            "appointment_time": "2025-06-15T10:00:00Z",
        },
        headers=auth_header,
    )
    booking_id = resp.json()["id"]

    # Create a second user
    await client.post(
        "/auth/signup",
        json={"email": "other@example.com", "password": "otherpass"},
    )
    resp2 = await client.post(
        "/auth/login",
        data={"username": "other@example.com", "password": "otherpass"},
    )
    other_header = {"Authorization": f"Bearer {resp2.json()['access_token']}"}

    resp = await client.get(f"/bookings/{booking_id}", headers=other_header)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_cancel_pending_booking(client: AsyncClient, auth_header: dict):
    centre_id, test_id = await _create_centre_and_test(client, auth_header)
    resp = await client.post(
        "/bookings/",
        json={
            "test_id": test_id,
            "centre_id": centre_id,
            "appointment_time": "2025-06-15T10:00:00Z",
        },
        headers=auth_header,
    )
    booking_id = resp.json()["id"]

    resp = await client.post(f"/bookings/{booking_id}/cancel", headers=auth_header)
    assert resp.status_code == 200
    assert resp.json()["status"] == "CANCELLED"


@pytest.mark.asyncio
async def test_cancel_already_cancelled_booking(client: AsyncClient, auth_header: dict):
    centre_id, test_id = await _create_centre_and_test(client, auth_header)
    resp = await client.post(
        "/bookings/",
        json={
            "test_id": test_id,
            "centre_id": centre_id,
            "appointment_time": "2025-06-15T10:00:00Z",
        },
        headers=auth_header,
    )
    booking_id = resp.json()["id"]

    # Cancel once
    await client.post(f"/bookings/{booking_id}/cancel", headers=auth_header)
    # Cancel again → 400
    resp = await client.post(f"/bookings/{booking_id}/cancel", headers=auth_header)
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_cancel_other_users_booking(client: AsyncClient, auth_header: dict):
    """Cancelling another user's booking returns 404."""
    centre_id, test_id = await _create_centre_and_test(client, auth_header)
    resp = await client.post(
        "/bookings/",
        json={
            "test_id": test_id,
            "centre_id": centre_id,
            "appointment_time": "2025-06-15T10:00:00Z",
        },
        headers=auth_header,
    )
    booking_id = resp.json()["id"]

    # Second user
    await client.post(
        "/auth/signup",
        json={"email": "other2@example.com", "password": "otherpass"},
    )
    resp2 = await client.post(
        "/auth/login",
        data={"username": "other2@example.com", "password": "otherpass"},
    )
    other_header = {"Authorization": f"Bearer {resp2.json()['access_token']}"}

    resp = await client.post(f"/bookings/{booking_id}/cancel", headers=other_header)
    assert resp.status_code == 404
