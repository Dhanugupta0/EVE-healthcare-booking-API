"""
End-to-End (E2E) Verification Script for EVE Diagnostics Booking API.
Executes the full end-to-end lifecycle across all subsystems:
- Auth & Roles (Admin vs Patient)
- Diagnostic Centres & Tests Catalog
- Booking Creation & Input Validations
- Data Isolation between Users
- Payment Simulation & Webhook Confirmation
- Webhook Idempotency & Replay Protection
- Payment Failure & Retry Flow
- Cancellation Lifecycle & Webhook Protection against Revival
"""

import asyncio
import os
import sys

# Configure environment before imports
os.environ["ADMIN_EMAIL"] = "admin@evedx.com"

from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import Base, get_db
from app.main import app

# In-memory SQLite for self-contained, repeatable E2E runs
engine_e2e = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
session_e2e = async_sessionmaker(engine_e2e, class_=AsyncSession, expire_on_commit=False)


async def override_get_db():
    async with session_e2e() as session:
        yield session


app.dependency_overrides[get_db] = override_get_db


def print_step(num: int, title: str):
    print(f"\n\033[1;36m[{num:02d}] {title}\033[0m")


def print_ok(msg: str):
    print(f"  \033[32m✔\033[0m {msg}")


def print_info(msg: str):
    print(f"    ℹ {msg}")


async def main():
    print("\n" + "=" * 65)
    print("  EVE Diagnostics Booking API — End-to-End Integration Suite")
    print("=" * 65)

    # Initialize tables
    async with engine_e2e.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:

        # ---------------------------------------------------------
        # Step 1: Health Check
        # ---------------------------------------------------------
        print_step(1, "API Health Check")
        resp = await client.get("/health")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
        print_ok(f"GET /health -> status={resp.status_code}, response={resp.json()}")

        # ---------------------------------------------------------
        # Step 2: System Admin Registration & Login
        # ---------------------------------------------------------
        print_step(2, "Admin Registration & Authentication")
        admin_payload = {"email": "admin@evedx.com", "password": "AdminSecurePassword123"}
        resp = await client.post("/auth/signup", json=admin_payload)
        assert resp.status_code == 201, resp.text
        admin_data = resp.json()
        assert admin_data["is_admin"] is True
        print_ok(f"POST /auth/signup (Admin) -> user_id={admin_data['id']}, is_admin={admin_data['is_admin']}")

        resp = await client.post("/auth/login", data={"username": "admin@evedx.com", "password": "AdminSecurePassword123"})
        assert resp.status_code == 200
        admin_token = resp.json()["access_token"]
        admin_headers = {"Authorization": f"Bearer {admin_token}"}
        print_ok("POST /auth/login (Admin) -> JWT access token acquired")

        # ---------------------------------------------------------
        # Step 3: Diagnostic Centre & Tests Catalog Creation
        # ---------------------------------------------------------
        print_step(3, "Diagnostic Centre & Tests Management (Admin Only)")
        centre_payload = {"name": "Apollo Diagnostics Bangalore", "location": "Indiranagar, Bangalore"}
        resp = await client.post("/centres/", json=centre_payload, headers=admin_headers)
        assert resp.status_code == 201
        centre = resp.json()
        centre_id = centre["id"]
        print_ok(f"POST /centres/ -> Created centre '{centre['name']}' (ID: {centre_id})")

        # Add Diagnostic Tests
        tests_data = [
            {"name": "Complete Blood Count (CBC)", "price": 450.00},
            {"name": "Comprehensive Lipid Profile", "price": 850.00},
            {"name": "HbA1c Diabetes Screening", "price": 500.00},
        ]
        created_tests = []
        for t in tests_data:
            resp = await client.post(f"/centres/{centre_id}/tests", json=t, headers=admin_headers)
            assert resp.status_code == 201
            t_obj = resp.json()
            created_tests.append(t_obj)
            print_ok(f"  + Added test: {t_obj['name']} | Price: ₹{t_obj['price']} (ID: {t_obj['id']})")

        cbc_test = created_tests[0]
        lipid_test = created_tests[1]
        hba1c_test = created_tests[2]

        # ---------------------------------------------------------
        # Step 4: Patient Alice Registration & Discovery
        # ---------------------------------------------------------
        print_step(4, "Patient Registration & Catalog Browsing")
        alice_payload = {"email": "alice@customer.com", "password": "AlicePassword123"}
        resp = await client.post("/auth/signup", json=alice_payload)
        assert resp.status_code == 201
        alice_data = resp.json()
        assert alice_data["is_admin"] is False
        print_ok(f"POST /auth/signup (Patient) -> user_id={alice_data['id']}, is_admin={alice_data['is_admin']}")

        resp = await client.post("/auth/login", data={"username": "alice@customer.com", "password": "AlicePassword123"})
        alice_token = resp.json()["access_token"]
        alice_headers = {"Authorization": f"Bearer {alice_token}"}
        print_ok("POST /auth/login (Patient) -> JWT access token acquired")

        # Alice retrieves centres & tests
        resp = await client.get("/centres/", headers=alice_headers)
        assert resp.status_code == 200
        centres_list = resp.json()
        assert len(centres_list) >= 1
        print_ok(f"GET /centres/ -> Retrieved {len(centres_list)} centre(s)")

        resp = await client.get(f"/centres/{centre_id}", headers=alice_headers)
        assert resp.status_code == 200
        centre_detail = resp.json()
        assert len(centre_detail["tests"]) == 3
        print_ok(f"GET /centres/{centre_id} -> Details loaded with {len(centre_detail['tests'])} tests available")

        # ---------------------------------------------------------
        # Step 5: Input Validation & Security Boundary Checks
        # ---------------------------------------------------------
        print_step(5, "Input Validation & Access Control Verification")

        # 5a: Short password rejected (< 8 chars)
        short_pw_resp = await client.post("/auth/signup", json={"email": "bad@x.com", "password": "short"})
        assert short_pw_resp.status_code == 422
        print_ok("Validation: Password < 8 characters rejected (422 Unprocessable Entity)")

        # 5b: Non-admin centre creation rejected
        non_admin_centre = await client.post("/centres/", json={"name": "Hacked Lab", "location": "Nowhere"}, headers=alice_headers)
        assert non_admin_centre.status_code == 403
        print_ok("Security: Non-admin user blocked from creating centres (403 Forbidden)")

        # 5c: Empty centre name rejected
        empty_c = await client.post("/centres/", json={"name": "", "location": "Delhi"}, headers=admin_headers)
        assert empty_c.status_code == 422
        print_ok("Validation: Empty centre name rejected (422 Unprocessable Entity)")

        # 5d: Invalid test price rejected (<= 0)
        invalid_price = await client.post(f"/centres/{centre_id}/tests", json={"name": "Free Test", "price": 0.0}, headers=admin_headers)
        assert invalid_price.status_code == 422
        print_ok("Validation: Non-positive test price rejected (422 Unprocessable Entity)")

        # 5e: Past appointment date rejected
        past_booking = await client.post(
            "/bookings/",
            json={"centre_id": centre_id, "test_id": cbc_test["id"], "appointment_time": "2020-01-01T10:00:00Z"},
            headers=alice_headers,
        )
        assert past_booking.status_code == 422
        print_ok("Validation: Past appointment time rejected (422 Unprocessable Entity)")

        # ---------------------------------------------------------
        # Step 6: Happy Path — Booking Creation & Initial State
        # ---------------------------------------------------------
        print_step(6, "Booking Creation (Happy Path)")
        booking_payload = {
            "centre_id": centre_id,
            "test_id": cbc_test["id"],
            "appointment_time": "2099-09-15T09:30:00Z",
        }
        resp = await client.post("/bookings/", json=booking_payload, headers=alice_headers)
        assert resp.status_code == 201
        booking_1 = resp.json()
        b1_id = booking_1["id"]
        assert booking_1["status"] == "PENDING"
        assert booking_1["amount"] == 450.00
        print_ok(f"POST /bookings/ -> Created booking ID: {b1_id} | Status: {booking_1['status']} | Amount: ₹{booking_1['amount']}")

        # ---------------------------------------------------------
        # Step 7: User Data Isolation & Unauthorized Access
        # ---------------------------------------------------------
        print_step(7, "Cross-User Privacy & Data Isolation")
        bob_payload = {"email": "bob@customer.com", "password": "BobSecurePassword123"}
        resp = await client.post("/auth/signup", json=bob_payload)
        resp = await client.post("/auth/login", data={"username": "bob@customer.com", "password": "BobSecurePassword123"})
        bob_headers = {"Authorization": f"Bearer {resp.json()['access_token']}"}

        # Bob attempts to view Alice's booking
        bob_view = await client.get(f"/bookings/{b1_id}", headers=bob_headers)
        assert bob_view.status_code == 404
        print_ok(f"Data Isolation: Bob querying Alice's booking -> 404 Not Found (hidden)")

        # Bob attempts to cancel Alice's booking
        bob_cancel = await client.post(f"/bookings/{b1_id}/cancel", headers=bob_headers)
        assert bob_cancel.status_code == 404
        print_ok(f"Data Isolation: Bob canceling Alice's booking -> 404 Not Found (blocked)")

        # Bob attempts to pay for Alice's booking
        bob_pay = await client.post("/payments/", json={"booking_id": b1_id}, headers=bob_headers)
        assert bob_pay.status_code == 404
        print_ok(f"Data Isolation: Bob paying for Alice's booking -> 404 Not Found (blocked)")

        # ---------------------------------------------------------
        # Step 8: Payment Webhook Callback & Idempotency
        # ---------------------------------------------------------
        print_step(8, "Payment Webhook Delivery & Idempotency")
        event_id = "evt-e2e-live-cbc-001"
        webhook_payload = {
            "event_id": event_id,
            "booking_id": b1_id,
            "status": "SUCCESS",
        }
        # First delivery
        resp = await client.post("/payments/webhook/", json=webhook_payload)
        assert resp.status_code == 200
        p_data = resp.json()
        assert p_data["status"] == "SUCCESS"
        assert p_data["event_id"] == event_id
        print_ok(f"POST /payments/webhook/ -> Recorded payment ID: {p_data['id']}, status=SUCCESS")

        # Second delivery (replay / retry from payment gateway)
        resp_dup = await client.post("/payments/webhook/", json=webhook_payload)
        assert resp_dup.status_code == 200
        assert resp_dup.json()["id"] == p_data["id"]
        print_ok("Webhook Idempotency: Duplicate delivery safely handled with identical payment ID")

        # Verify Alice's booking is CONFIRMED
        resp = await client.get(f"/bookings/{b1_id}", headers=alice_headers)
        assert resp.status_code == 200
        assert resp.json()["status"] == "CONFIRMED"
        print_ok(f"State Transition: Booking {b1_id} status updated to CONFIRMED")

        # Step 8b: Attempt to initiate payment on already CONFIRMED booking is rejected
        dup_pay = await client.post("/payments/", json={"booking_id": b1_id}, headers=alice_headers)
        assert dup_pay.status_code == 400
        print_ok("Safety Guard: Paying for already CONFIRMED booking rejected (400 Bad Request)")

        # ---------------------------------------------------------
        # Step 9: Payment Failure & Retry Flow
        # ---------------------------------------------------------
        print_step(9, "Payment Failure & Retry Recovery Flow")
        # Alice creates second booking for Lipid Profile
        resp = await client.post(
            "/bookings/",
            json={"centre_id": centre_id, "test_id": lipid_test["id"], "appointment_time": "2099-10-01T14:00:00Z"},
            headers=alice_headers,
        )
        b2_id = resp.json()["id"]
        print_ok(f"Created Booking ID: {b2_id} for Lipid Profile (₹850.00)")

        # Webhook reports payment FAILED
        fail_event = "evt-e2e-fail-lipid"
        resp = await client.post(
            "/payments/webhook/",
            json={"event_id": fail_event, "booking_id": b2_id, "status": "FAILED"},
        )
        assert resp.status_code == 200

        # Booking is now FAILED
        resp = await client.get(f"/bookings/{b2_id}", headers=alice_headers)
        assert resp.json()["status"] == "FAILED"
        print_ok(f"Payment failure registered -> Booking {b2_id} status is now FAILED")

        # Alice retries payment via webhook or endpoint
        retry_event = "evt-e2e-retry-success-lipid"
        resp = await client.post(
            "/payments/webhook/",
            json={"event_id": retry_event, "booking_id": b2_id, "status": "SUCCESS"},
        )
        assert resp.status_code == 200

        # Booking transitions to CONFIRMED after retry
        resp = await client.get(f"/bookings/{b2_id}", headers=alice_headers)
        assert resp.json()["status"] == "CONFIRMED"
        print_ok(f"Payment retry successful -> Booking {b2_id} successfully recovered to CONFIRMED")

        # ---------------------------------------------------------
        # Step 10: Cancellation & Webhook Guard (No Revival)
        # ---------------------------------------------------------
        print_step(10, "Cancellation Lifecycle & Late Webhook Protection")
        # Alice creates third booking for HbA1c
        resp = await client.post(
            "/bookings/",
            json={"centre_id": centre_id, "test_id": hba1c_test["id"], "appointment_time": "2099-10-10T16:00:00Z"},
            headers=alice_headers,
        )
        b3_id = resp.json()["id"]
        print_ok(f"Created Booking ID: {b3_id} for HbA1c (₹500.00)")

        # Alice cancels the booking
        resp = await client.post(f"/bookings/{b3_id}/cancel", headers=alice_headers)
        assert resp.status_code == 200
        assert resp.json()["status"] == "CANCELLED"
        print_ok(f"POST /bookings/{b3_id}/cancel -> Booking status changed to CANCELLED")

        # Cannot cancel again
        resp_re_cancel = await client.post(f"/bookings/{b3_id}/cancel", headers=alice_headers)
        assert resp_re_cancel.status_code == 400
        print_ok("Cancellation Guard: Cannot re-cancel an already CANCELLED booking (400 Bad Request)")

        # Cannot initiate payment for cancelled booking
        resp_cancel_pay = await client.post("/payments/", json={"booking_id": b3_id}, headers=alice_headers)
        assert resp_cancel_pay.status_code == 400
        print_ok("Payment Guard: Initiating payment for CANCELLED booking rejected (400 Bad Request)")

        # Late payment webhook arrives from payment gateway
        late_event = "evt-e2e-late-hba1c"
        resp = await client.post(
            "/payments/webhook/",
            json={"event_id": late_event, "booking_id": b3_id, "status": "SUCCESS"},
        )
        assert resp.status_code == 200
        print_ok(f"Late Webhook: Accepted with status 200 and logged in payment audit ledger")

        # Crucial check: Booking must NOT be revived
        resp = await client.get(f"/bookings/{b3_id}", headers=alice_headers)
        assert resp.json()["status"] == "CANCELLED"
        print_ok(f"Revival Guard Verified: Booking {b3_id} remains CANCELLED (never revived)")

        # ---------------------------------------------------------
        # Final Summary
        # ---------------------------------------------------------
        print("\n" + "=" * 65)
        print("  \033[1;32mALL END-TO-END TESTS PASSED SUCCESSFULLY! (10/10 Stages)\033[0m")
        print("=" * 65 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
