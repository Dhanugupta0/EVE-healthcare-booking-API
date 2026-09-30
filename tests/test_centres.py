import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_list_centres_empty(client: AsyncClient):
    resp = await client.get("/centres/")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_create_centre(client: AsyncClient, auth_header: dict):
    resp = await client.post(
        "/centres/",
        json={"name": "City Lab", "location": "Mumbai"},
        headers=auth_header,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "City Lab"
    assert data["location"] == "Mumbai"


@pytest.mark.asyncio
async def test_create_centre_no_auth(client: AsyncClient):
    resp = await client.post(
        "/centres/",
        json={"name": "Lab", "location": "Delhi"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_create_centre_non_admin(client: AsyncClient, regular_auth_header: dict):
    """Non-admin users cannot create centres → 403."""
    resp = await client.post(
        "/centres/",
        json={"name": "Lab", "location": "Delhi"},
        headers=regular_auth_header,
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_create_centre_empty_name(client: AsyncClient, auth_header: dict):
    """Empty centre name → 422."""
    resp = await client.post(
        "/centres/",
        json={"name": "", "location": "Delhi"},
        headers=auth_header,
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_add_test_invalid_price(client: AsyncClient, auth_header: dict):
    """Zero or negative test price → 422."""
    resp = await client.post(
        "/centres/",
        json={"name": "Lab", "location": "Delhi"},
        headers=auth_header,
    )
    centre_id = resp.json()["id"]

    resp = await client.post(
        f"/centres/{centre_id}/tests",
        json={"name": "CBC", "price": 0},
        headers=auth_header,
    )
    assert resp.status_code == 422

    resp = await client.post(
        f"/centres/{centre_id}/tests",
        json={"name": "CBC", "price": -100},
        headers=auth_header,
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_get_centre_detail(client: AsyncClient, auth_header: dict):
    # Create a centre
    resp = await client.post(
        "/centres/",
        json={"name": "City Lab", "location": "Mumbai"},
        headers=auth_header,
    )
    centre_id = resp.json()["id"]

    # Add a test to it
    await client.post(
        f"/centres/{centre_id}/tests",
        json={"name": "CBC", "price": 500.0},
        headers=auth_header,
    )

    # Get detail
    resp = await client.get(f"/centres/{centre_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "City Lab"
    assert len(data["tests"]) == 1
    assert data["tests"][0]["name"] == "CBC"


@pytest.mark.asyncio
async def test_get_nonexistent_centre(client: AsyncClient):
    resp = await client.get("/centres/999")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_add_test_to_centre(client: AsyncClient, auth_header: dict):
    resp = await client.post(
        "/centres/",
        json={"name": "Lab X", "location": "Pune"},
        headers=auth_header,
    )
    centre_id = resp.json()["id"]

    resp = await client.post(
        f"/centres/{centre_id}/tests",
        json={"name": "Lipid Panel", "price": 800.0},
        headers=auth_header,
    )
    assert resp.status_code == 201
    assert resp.json()["name"] == "Lipid Panel"
    assert resp.json()["price"] == 800.0


@pytest.mark.asyncio
async def test_add_test_nonexistent_centre(client: AsyncClient, auth_header: dict):
    resp = await client.post(
        "/centres/999/tests",
        json={"name": "Blood Test", "price": 300.0},
        headers=auth_header,
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_list_centres_pagination(client: AsyncClient, auth_header: dict):
    """Pagination params skip and limit work correctly."""
    # Create 3 centres
    for i in range(3):
        await client.post(
            "/centres/",
            json={"name": f"Lab {i}", "location": "City"},
            headers=auth_header,
        )

    # Default returns all 3
    resp = await client.get("/centres/")
    assert len(resp.json()) == 3

    # limit=2 returns 2
    resp = await client.get("/centres/?limit=2")
    assert len(resp.json()) == 2

    # skip=2 returns 1
    resp = await client.get("/centres/?skip=2")
    assert len(resp.json()) == 1
