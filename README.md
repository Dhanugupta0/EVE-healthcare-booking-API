# EVE Diagnostics Booking API

A FastAPI backend for diagnostic test bookings with a simulated payment flow. Built as a hiring assignment demonstrating clean async architecture, proper testing, and Docker deployment.

## Tech Stack

- **Python 3.11+** / **FastAPI** — fully async (`async def` routes throughout)
- **PostgreSQL** via **SQLAlchemy 2.0 async** (`AsyncSession`, `create_async_engine`) with `asyncpg`
- **SQLite in-memory** via `aiosqlite` for tests (no external services required)
- **passlib[bcrypt]** for password hashing, **python-jose** for JWT
- **pytest** + **pytest-asyncio** + **httpx.AsyncClient** for async testing
- **Docker** + **docker-compose** for one-command startup

---

## How to Run

### Option 1: Docker Compose (recommended)

```bash
git clone <repo-url> && cd eve-diagnostics-booking
docker-compose up --build
```

The API will be available at `http://localhost:8000`. Swagger docs at `http://localhost:8000/docs`.

### Option 2: Local venv + uvicorn

```bash
# Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Set environment variables (or create .env from .env.example)
cp .env.example .env
# Edit .env to point DATABASE_URL to your local Postgres

# Run the server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Running Tests

```bash
source venv/bin/activate
pytest -v
```

Tests use an in-memory SQLite database — no Postgres needed.

---

## API Endpoints

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| POST | `/auth/signup` | none | Create user (admin if email matches `ADMIN_EMAIL`) |
| POST | `/auth/login` | none | Returns JWT access token |
| GET | `/centres/` | none | List centres (paginated: `skip`, `limit`) |
| GET | `/centres/{centre_id}` | none | Centre detail + its tests |
| POST | `/centres/` | admin | Create a centre |
| POST | `/centres/{centre_id}/tests` | admin | Add a test to a centre |
| POST | `/bookings/` | required | Create a booking (PENDING, amount = test price) |
| GET | `/bookings/` | required | List current user's bookings (paginated: `skip`, `limit`) |
| GET | `/bookings/{id}` | required | Get one booking (must belong to caller) |
| POST | `/bookings/{id}/cancel` | required | Cancel a PENDING or CONFIRMED booking |
| POST | `/payments/` | required | Simulate payment → SUCCESS/FAILED |
| POST | `/payments/webhook/` | none | Idempotent status update from "payment provider" |

### Example curl Requests

**Signup:**
```bash
curl -X POST http://localhost:8000/auth/signup \
  -H "Content-Type: application/json" \
  -d '{"email": "user@example.com", "password": "securepass123"}'
```

**Login:**
```bash
curl -X POST http://localhost:8000/auth/login \
  -d "username=user@example.com&password=securepass123"
```

**List Centres (with pagination):**
```bash
curl "http://localhost:8000/centres/?skip=0&limit=20"
```

**Get Centre Detail:**
```bash
curl http://localhost:8000/centres/1
```

**Create Centre (admin auth required):**
```bash
curl -X POST http://localhost:8000/centres/ \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"name": "City Diagnostics", "location": "Mumbai"}'
```

**Add Test to Centre (admin auth required):**
```bash
curl -X POST http://localhost:8000/centres/1/tests \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"name": "Complete Blood Count", "price": 500.00}'
```

**Create Booking (auth required):**
```bash
curl -X POST http://localhost:8000/bookings/ \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"test_id": 1, "centre_id": 1, "appointment_time": "2025-06-15T10:00:00Z"}'
```

**List My Bookings (with pagination):**
```bash
curl "http://localhost:8000/bookings/?skip=0&limit=20" \
  -H "Authorization: Bearer <token>"
```

**Get Booking (auth required):**
```bash
curl http://localhost:8000/bookings/1 \
  -H "Authorization: Bearer <token>"
```

**Cancel Booking (auth required):**
```bash
curl -X POST http://localhost:8000/bookings/1/cancel \
  -H "Authorization: Bearer <token>"
```

**Simulate Payment (auth required):**
```bash
curl -X POST http://localhost:8000/payments/ \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"booking_id": 1}'
```

**Payment Webhook (no auth — simulates external provider):**
```bash
curl -X POST http://localhost:8000/payments/webhook/ \
  -H "Content-Type: application/json" \
  -d '{"event_id": "evt-abc-123", "booking_id": 1, "status": "SUCCESS"}'
```

---

## Schema Explanation

### Why These Tables

The data model follows the natural domain: **Users** book **Tests** at **Centres**, creating **Bookings** that are paid for via **Payments**.

### Tables

| Table | Purpose |
|-------|------------|
| `users` | Authentication. Email is unique and indexed for fast lookup. `is_admin` flag controls access to management endpoints. |
| `centres` | Diagnostic centres with name and location. |
| `tests` | Diagnostic tests offered at a centre. FK to `centres`. Price stored here — booking amount is pulled from this, not from client input. |
| `bookings` | A user's appointment for a test at a centre. Tracks status through its lifecycle. |
| `payments` | Payment records. `event_id` is a unique idempotency key to prevent duplicate processing from webhook retries. |

### Why Status is a String Column (Not a Postgres ENUM)

Both `BookingStatus` (PENDING, CONFIRMED, FAILED, CANCELLED) and `PaymentStatus` (SUCCESS, FAILED) are stored as plain `String` columns rather than Postgres-native `ENUM` types. This ensures the same SQLAlchemy models work against both PostgreSQL in production and SQLite in-memory during tests — SQLite has no native ENUM type. The Python-side `enum.Enum` classes still enforce valid values in application code.

### Why `event_id` is the Idempotency Key

Payment providers often retry webhook calls. The `event_id` column has a unique constraint. Before inserting a new Payment, the webhook handler checks if that `event_id` already exists — if so, it returns the existing result without touching the booking. This guarantees exactly-once semantics for payment processing.

---

## Business Rules & Edge Cases

### Input Validation (Pydantic)
- **Password**: minimum 8 characters (422 if shorter)
- **Centre name / test name**: cannot be empty (422 if blank)
- **Test price**: must be greater than 0 (422 if zero or negative)
- **Appointment time**: must be in the future (422 if in the past)

### Admin Access Control
- `is_admin` boolean on the User model (default `False`)
- Set `ADMIN_EMAIL` env var — any user signing up with that email is automatically marked as admin
- Only admins can create diagnostic centres (`POST /centres/`) and add tests (`POST /centres/{id}/tests`) — non-admins get 403

### Webhook Cannot Revive Cancelled Bookings
- If a booking has been cancelled by the user, a late-arriving webhook (SUCCESS or FAILED) will **not** change the booking status back
- The payment record is still stored for audit trail, and idempotency still works correctly

### Payment Retry After Failure
- Payment is allowed for bookings in `PENDING` or `FAILED` status
- Payment is blocked for `CONFIRMED` (already paid) and `CANCELLED` (user cancelled) bookings
- Each retry generates a new `event_id`

### Pagination
- `GET /centres/` and `GET /bookings/` accept `skip` (default 0) and `limit` (default 20, max 100) query params
- Example: `GET /bookings/?skip=0&limit=10`

### Other Edge Cases
- Ownership check returns 404, not 403 — avoids leaking information about whether a booking exists
- Booking amount is pulled from the test's price in the database, not from client input
- Cancelling an already cancelled or failed booking returns 400

---

## Assumptions

1. **Admin via env var** — `ADMIN_EMAIL` marks a single user as admin on signup. In production, this would be a proper RBAC system with an admin panel.
2. **Ownership check returns 404, not 403** — when a user tries to access another user's booking, the API returns 404 to avoid leaking information about whether the booking exists.
3. **Payment success rate is simulated** — the `POST /payments/` endpoint randomly resolves to SUCCESS (80%) or FAILED (20%). In production, this would integrate with a real payment gateway.
4. **No Alembic migrations** — tables are created via `Base.metadata.create_all` on startup. Fine for a demo; production would use Alembic.
5. **Webhook has no authentication** — in production, webhook endpoints would verify a signature from the payment provider.
6. **Single commit for webhook** — the Payment row and Booking status update happen in a single `await db.commit()` call, ensuring atomicity.

---

## What I Would Improve With More Time

- **Alembic migrations** — proper schema versioning instead of `create_all` on startup
- **Redis caching** — cache frequently accessed data like the centres list to reduce DB load
- **Rate limiting on login** — protect `/auth/login` from brute force attacks (e.g., via Redis + slowapi)
- **Structured logging** — add middleware for request/response logging with correlation IDs, latency tracking
- **Webhook signature verification** — validate that webhook calls come from the actual payment provider using HMAC signatures
- **Full RBAC** — role-based access control beyond a single admin flag
- **Retry queue** — for failed payments, allow retrying with exponential backoff via Celery
- **CI/CD pipeline** — automated test runs, linting, and deployment
- **Soft deletes** — instead of hard state transitions, maintain an audit trail
