import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_signup_success(client: AsyncClient):
    resp = await client.post(
        "/auth/signup",
        json={"email": "new@example.com", "password": "pass123"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["email"] == "new@example.com"
    assert "id" in data


@pytest.mark.asyncio
async def test_signup_duplicate_email(client: AsyncClient):
    await client.post(
        "/auth/signup",
        json={"email": "dup@example.com", "password": "pass123"},
    )
    resp = await client.post(
        "/auth/signup",
        json={"email": "dup@example.com", "password": "pass456"},
    )
    assert resp.status_code == 400
    assert "already registered" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_login_success(client: AsyncClient):
    await client.post(
        "/auth/signup",
        json={"email": "login@example.com", "password": "pass123"},
    )
    resp = await client.post(
        "/auth/login",
        data={"username": "login@example.com", "password": "pass123"},
    )
    assert resp.status_code == 200
    assert "access_token" in resp.json()


@pytest.mark.asyncio
async def test_login_wrong_password(client: AsyncClient):
    await client.post(
        "/auth/signup",
        json={"email": "wrong@example.com", "password": "pass123"},
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
        data={"username": "nobody@example.com", "password": "pass123"},
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
