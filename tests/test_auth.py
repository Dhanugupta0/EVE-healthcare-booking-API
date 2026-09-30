import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_signup_success(client: AsyncClient):
    resp = await client.post(
        "/auth/signup",
        json={"email": "new@example.com", "password": "pass1234"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["email"] == "new@example.com"
    assert "id" in data


@pytest.mark.asyncio
async def test_signup_duplicate_email(client: AsyncClient):
    await client.post(
        "/auth/signup",
        json={"email": "dup@example.com", "password": "pass1234"},
    )
    resp = await client.post(
        "/auth/signup",
        json={"email": "dup@example.com", "password": "pass4567"},
    )
    assert resp.status_code == 400
    assert "already registered" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_signup_short_password(client: AsyncClient):
    """Password shorter than 8 chars → 422."""
    resp = await client.post(
        "/auth/signup",
        json={"email": "short@example.com", "password": "abc"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_login_success(client: AsyncClient):
    await client.post(
        "/auth/signup",
        json={"email": "login@example.com", "password": "pass1234"},
    )
    resp = await client.post(
        "/auth/login",
        data={"username": "login@example.com", "password": "pass1234"},
    )
    assert resp.status_code == 200
    assert "access_token" in resp.json()


@pytest.mark.asyncio
async def test_login_wrong_password(client: AsyncClient):
    await client.post(
        "/auth/signup",
        json={"email": "wrong@example.com", "password": "pass1234"},
    )
    resp = await client.post(
        "/auth/login",
        data={"username": "wrong@example.com", "password": "wrongpass"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_login_unknown_email(client: AsyncClient):
    resp = await client.post(
        "/auth/login",
        data={"username": "nobody@example.com", "password": "pass1234"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_protected_route_no_token(client: AsyncClient):
    resp = await client.get("/bookings/")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_protected_route_invalid_token(client: AsyncClient):
    resp = await client.get(
        "/bookings/",
        headers={"Authorization": "Bearer invalid-token"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_admin_signup(client: AsyncClient):
    """User signing up with ADMIN_EMAIL gets is_admin=True."""
    resp = await client.post(
        "/auth/signup",
        json={"email": "test@example.com", "password": "testpass123"},
    )
    assert resp.status_code == 201
    assert resp.json()["is_admin"] is True


@pytest.mark.asyncio
async def test_regular_signup(client: AsyncClient):
    """User signing up with a non-admin email gets is_admin=False."""
    resp = await client.post(
        "/auth/signup",
        json={"email": "nonadmin@example.com", "password": "pass1234"},
    )
    assert resp.status_code == 201
    assert resp.json()["is_admin"] is False
