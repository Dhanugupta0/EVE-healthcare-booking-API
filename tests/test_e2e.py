from unittest.mock import patch

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_e2e_full_diagnostic_booking_and_payment_lifecycle(client: AsyncClient):
    """
    End-to-End Test 1: Complete Happy Path Lifecycle
    1. Admin logs in and registers a Diagnostic Centre with tests.
    2. Patient Alice signs up, logs in, and browses available centres & tests.
    3. Alice books a diagnostic test with a future appointment time.
    4. Alice verifies booking is in PENDING status with correct amount.
    5. Payment webhook callback arrives with status SUCCESS.
    6. Idempotent webhook replay is verified.
    7. Alice verifies booking is CONFIRMED.
    8. Attempting to pay again for CONFIRMED booking is rejected.
    """
    # --- Step 1: Admin logs in ---
    admin_signup_resp = await client.post(
        "/auth/signup",
        json={"email": "test@example.com", "password": "adminpassword123"},
    )
    assert admin_signup_resp.status_code == 201
    assert admin_signup_resp.json()["is_admin"] is True

    admin_login_resp = await client.post(
        "/auth/login",
        data={"username": "test@example.com", "password": "adminpassword123"},
    )
    assert admin_login_resp.status_code == 200
    admin_token = admin_login_resp.json()["access_token"]
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    # Admin creates diagnostic centre
    centre_resp = await client.post(
        "/centres/",
        json={"name": "Apollo Diagnostics Bangalore", "location": "Indiranagar, Bangalore"},
        headers=admin_headers,
    )
    assert centre_resp.status_code == 201
    centre_data = centre_resp.json()
    centre_id = centre_data["id"]
    assert centre_data["name"] == "Apollo Diagnostics Bangalore"

    # Admin adds tests to the centre
    test1_resp = await client.post(
        f"/centres/{centre_id}/tests",
        json={"name": "Complete Blood Count (CBC)", "price": 499.00},
        headers=admin_headers,
    )
    assert test1_resp.status_code == 201
    test1_id = test1_resp.json()["id"]

    test2_resp = await client.post(
        f"/centres/{centre_id}/tests",
        json={"name": "Lipid Profile", "price": 999.00},
        headers=admin_headers,
    )
    assert test2_resp.status_code == 201
    test2_id = test2_resp.json()["id"]

    # --- Step 2: Patient Alice signs up and logs in ---
    alice_signup = await client.post(
        "/auth/signup",
        json={"email": "alice@example.com", "password": "alicepassword123"},
    )
    assert alice_signup.status_code == 201
    assert alice_signup.json()["is_admin"] is False

    alice_login = await client.post(
        "/auth/login",
        data={"username": "alice@example.com", "password": "alicepassword123"},
    )
    assert alice_login.status_code == 200
    alice_token = alice_login.json()["access_token"]
    alice_headers = {"Authorization": f"Bearer {alice_token}"}

    # Alice browses available diagnostic centres
    centres_list = await client.get("/centres/", headers=alice_headers)
    assert centres_list.status_code == 200
    centres_data = centres_list.json()
    assert len(centres_data) >= 1
    assert any(c["id"] == centre_id for c in centres_data)

    # Alice views centre details with available tests
    centre_detail = await client.get(f"/centres/{centre_id}", headers=alice_headers)
    assert centre_detail.status_code == 200
    available_tests = centre_detail.json()["tests"]
    assert len(available_tests) == 2
    assert {t["name"] for t in available_tests} == {"Complete Blood Count (CBC)", "Lipid Profile"}

    # --- Step 3: Alice books an appointment ---
    booking_payload = {
        "centre_id": centre_id,
        "test_id": test1_id,
        "appointment_time": "2099-10-15T09:30:00Z",
    }
    booking_resp = await client.post("/bookings/", json=booking_payload, headers=alice_headers)
    assert booking_resp.status_code == 201
    booking_data = booking_resp.json()
    booking_id = booking_data["id"]

    # Assert initial booking state
    assert booking_data["status"] == "PENDING"
    assert booking_data["amount"] == 499.00
    assert booking_data["centre_id"] == centre_id
    assert booking_data["test_id"] == test1_id

    # --- Step 4: Alice verifies booking in her bookings list ---
    my_bookings = await client.get("/bookings/", headers=alice_headers)
    assert my_bookings.status_code == 200
    assert len(my_bookings.json()) == 1
    assert my_bookings.json()[0]["id"] == booking_id

    # --- Step 5: Webhook callback processes SUCCESS payment ---
    webhook_payload = {
        "event_id": "evt-e2e-success-001",
        "booking_id": booking_id,
        "status": "SUCCESS",
    }
    webhook_resp = await client.post("/payments/webhook/", json=webhook_payload)
    assert webhook_resp.status_code == 200
    assert webhook_resp.json()["status"] == "SUCCESS"
    assert webhook_resp.json()["booking_id"] == booking_id

    # --- Step 6: Verify Webhook Idempotency ---
    webhook_dup_resp = await client.post("/payments/webhook/", json=webhook_payload)
    assert webhook_dup_resp.status_code == 200
    assert webhook_dup_resp.json()["id"] == webhook_resp.json()["id"]

    # --- Step 7: Alice verifies booking status is now CONFIRMED ---
    confirmed_booking = await client.get(f"/bookings/{booking_id}", headers=alice_headers)
    assert confirmed_booking.status_code == 200
    assert confirmed_booking.json()["status"] == "CONFIRMED"

    # --- Step 8: Double payment attempt blocked ---
    dup_pay_resp = await client.post(
        "/payments/",
        json={"booking_id": booking_id},
        headers=alice_headers,
    )
    assert dup_pay_resp.status_code == 400
    assert "PENDING or FAILED" in dup_pay_resp.json()["detail"]


@pytest.mark.asyncio
async def test_e2e_payment_failure_and_retry_flow(client: AsyncClient, auth_header: dict):
    """
    End-to-End Test 2: Payment Failure & Retry Flow
    1. Patient books a test.
    2. Webhook triggers payment FAILED status.
    3. Booking status transitions to FAILED.
    4. Patient retries payment via simulated payment endpoint.
    5. Booking successfully transitions to CONFIRMED.
    """
    # Setup centre and test
    c_resp = await client.post(
        "/centres/",
        json={"name": "Fortis Diagnostics", "location": "Delhi"},
        headers=auth_header,
    )
    c_id = c_resp.json()["id"]
    t_resp = await client.post(
        f"/centres/{c_id}/tests",
        json={"name": "Thyroid Profile", "price": 600.00},
        headers=auth_header,
    )
    t_id = t_resp.json()["id"]

    # Create patient booking
    b_resp = await client.post(
        "/bookings/",
        json={
            "centre_id": c_id,
            "test_id": t_id,
            "appointment_time": "2099-11-20T11:00:00Z",
        },
        headers=auth_header,
    )
    assert b_resp.status_code == 201
    b_id = b_resp.json()["id"]
    assert b_resp.json()["status"] == "PENDING"

    # Webhook notifies payment failure
    fail_webhook = await client.post(
        "/payments/webhook/",
        json={
            "event_id": "evt-e2e-fail-001",
            "booking_id": b_id,
            "status": "FAILED",
        },
    )
    assert fail_webhook.status_code == 200
    assert fail_webhook.json()["status"] == "FAILED"

    # Booking must now be FAILED
    booking_status_check = await client.get(f"/bookings/{b_id}", headers=auth_header)
    assert booking_status_check.status_code == 200
    assert booking_status_check.json()["status"] == "FAILED"

    # Patient retries payment (simulate success)
    with patch("app.services.payment_service.random.choices", return_value=["SUCCESS"]):
        retry_resp = await client.post(
            "/payments/",
            json={"booking_id": b_id},
            headers=auth_header,
        )
    assert retry_resp.status_code == 201
    assert retry_resp.json()["status"] == "SUCCESS"

    # Booking must now be CONFIRMED after retry
    confirmed_check = await client.get(f"/bookings/{b_id}", headers=auth_header)
    assert confirmed_check.status_code == 200
    assert confirmed_check.json()["status"] == "CONFIRMED"


@pytest.mark.asyncio
async def test_e2e_booking_cancellation_and_webhook_guard(client: AsyncClient, auth_header: dict):
    """
    End-to-End Test 3: Cancellation Lifecycle & Webhook Guard
    1. Booking is created in PENDING status.
    2. Patient cancels the booking -> status CANCELLED.
    3. Subsequent cancellation attempt rejected with 400.
    4. Payment attempt for CANCELLED booking rejected with 400.
    5. Late payment webhook arrives reporting SUCCESS.
    6. Payment record is created for ledger audit, but booking remains CANCELLED.
    """
    c_resp = await client.post(
        "/centres/",
        json={"name": "Max Diagnostics", "location": "Gurgaon"},
        headers=auth_header,
    )
    c_id = c_resp.json()["id"]
    t_resp = await client.post(
        f"/centres/{c_id}/tests",
        json={"name": "Vitamin D", "price": 1200.00},
        headers=auth_header,
    )
    t_id = t_resp.json()["id"]

    # Book appointment
    b_resp = await client.post(
        "/bookings/",
        json={
            "centre_id": c_id,
            "test_id": t_id,
            "appointment_time": "2099-12-05T14:00:00Z",
        },
        headers=auth_header,
    )
    b_id = b_resp.json()["id"]
    assert b_resp.json()["status"] == "PENDING"

    # Cancel booking
    cancel_resp = await client.post(f"/bookings/{b_id}/cancel", headers=auth_header)
    assert cancel_resp.status_code == 200
    assert cancel_resp.json()["status"] == "CANCELLED"

    # Cannot cancel again
    dup_cancel = await client.post(f"/bookings/{b_id}/cancel", headers=auth_header)
    assert dup_cancel.status_code == 400

    # Cannot pay for CANCELLED booking
    pay_cancelled = await client.post(
        "/payments/",
        json={"booking_id": b_id},
        headers=auth_header,
    )
    assert pay_cancelled.status_code == 400

    # Late webhook arrives claiming payment SUCCESS
    late_webhook = await client.post(
        "/payments/webhook/",
        json={
            "event_id": "evt-e2e-late-success",
            "booking_id": b_id,
            "status": "SUCCESS",
        },
    )
    assert late_webhook.status_code == 200
    assert late_webhook.json()["status"] == "SUCCESS"

    # Verify booking was NOT revived: status remains CANCELLED
    final_booking = await client.get(f"/bookings/{b_id}", headers=auth_header)
    assert final_booking.status_code == 200
    assert final_booking.json()["status"] == "CANCELLED"


@pytest.mark.asyncio
async def test_e2e_data_isolation_and_security_boundaries(client: AsyncClient):
    """
    End-to-End Test 4: Multi-User Security & Isolation
    1. Admin creates centre & test.
    2. User Alice creates a booking.
    3. User Bob cannot see, access, cancel, or pay for Alice's booking.
    4. Bob cannot create centres (non-admin).
    5. Bob's booking list only shows his own bookings.
    """
    # 1. Admin setup
    await client.post("/auth/signup", json={"email": "test@example.com", "password": "adminpassword123"})
    admin_login = await client.post(
        "/auth/login", data={"username": "test@example.com", "password": "adminpassword123"}
    )
    admin_headers = {"Authorization": f"Bearer {admin_login.json()['access_token']}"}

    c_resp = await client.post(
        "/centres/",
        json={"name": "SRL Diagnostics", "location": "Kolkata"},
        headers=admin_headers,
    )
    c_id = c_resp.json()["id"]
    t_resp = await client.post(
        f"/centres/{c_id}/tests",
        json={"name": "KFT Kidney Function Test", "price": 750.00},
        headers=admin_headers,
    )
    t_id = t_resp.json()["id"]

    # 2. Alice signup & booking
    await client.post("/auth/signup", json={"email": "alice_sec@example.com", "password": "alicepass123"})
    alice_login = await client.post(
        "/auth/login", data={"username": "alice_sec@example.com", "password": "alicepass123"}
    )
    alice_headers = {"Authorization": f"Bearer {alice_login.json()['access_token']}"}

    alice_b_resp = await client.post(
        "/bookings/",
        json={"centre_id": c_id, "test_id": t_id, "appointment_time": "2099-08-10T10:00:00Z"},
        headers=alice_headers,
    )
    alice_b_id = alice_b_resp.json()["id"]

    # 3. Bob signup & attempts unauthorized access to Alice's resources
    await client.post("/auth/signup", json={"email": "bob_sec@example.com", "password": "bobpassword123"})
    bob_login = await client.post(
        "/auth/login", data={"username": "bob_sec@example.com", "password": "bobpassword123"}
    )
    bob_headers = {"Authorization": f"Bearer {bob_login.json()['access_token']}"}

    # Bob cannot view Alice's booking (404 for isolation)
    bob_view = await client.get(f"/bookings/{alice_b_id}", headers=bob_headers)
    assert bob_view.status_code == 404

    # Bob cannot cancel Alice's booking
    bob_cancel = await client.post(f"/bookings/{alice_b_id}/cancel", headers=bob_headers)
    assert bob_cancel.status_code == 404

    # Bob cannot pay for Alice's booking
    bob_pay = await client.post("/payments/", json={"booking_id": alice_b_id}, headers=bob_headers)
    assert bob_pay.status_code == 404

    # Bob's bookings list is empty
    bob_list = await client.get("/bookings/", headers=bob_headers)
    assert bob_list.status_code == 200
    assert bob_list.json() == []

    # Bob cannot create a centre (non-admin → 403)
    bob_centre = await client.post(
        "/centres/",
        json={"name": "Hacked Lab", "location": "Nowhere"},
        headers=bob_headers,
    )
    assert bob_centre.status_code == 403


@pytest.mark.asyncio
async def test_e2e_input_validation_and_error_handling(client: AsyncClient, auth_header: dict):
    """
    End-to-End Test 5: Comprehensive Input Validation
    - Short password (< 8 chars) -> 422
    - Past appointment time -> 422
    - Empty centre name -> 422
    - Non-positive test price -> 422
    - Unauthenticated access to protected routes -> 401
    """
    # Short password
    short_pw = await client.post("/auth/signup", json={"email": "bad@example.com", "password": "short"})
    assert short_pw.status_code == 422

    # Unauthenticated access
    unauth = await client.get("/bookings/")
    assert unauth.status_code == 401

    # Empty centre name
    empty_centre = await client.post(
        "/centres/",
        json={"name": "", "location": "Mumbai"},
        headers=auth_header,
    )
    assert empty_centre.status_code == 422

    # Create valid centre to test test-price validation
    centre_resp = await client.post(
        "/centres/",
        json={"name": "Validation Centre", "location": "Pune"},
        headers=auth_header,
    )
    c_id = centre_resp.json()["id"]

    # Zero or negative price
    zero_price = await client.post(
        f"/centres/{c_id}/tests",
        json={"name": "Free Test", "price": 0.0},
        headers=auth_header,
    )
    assert zero_price.status_code == 422

    neg_price = await client.post(
        f"/centres/{c_id}/tests",
        json={"name": "Negative Price Test", "price": -50.0},
        headers=auth_header,
    )
    assert neg_price.status_code == 422

    # Add valid test to check booking validation
    test_resp = await client.post(
        f"/centres/{c_id}/tests",
        json={"name": "Valid Test", "price": 100.0},
        headers=auth_header,
    )
    t_id = test_resp.json()["id"]

    # Past appointment time
    past_booking = await client.post(
        "/bookings/",
        json={
            "centre_id": c_id,
            "test_id": t_id,
            "appointment_time": "2020-01-01T12:00:00Z",
        },
        headers=auth_header,
    )
    assert past_booking.status_code == 422
