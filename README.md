# Learning-support-assistant-Service-Booking
A HabotConnect hiring project to demonstrate Python backend skills by building an LSA booking platform connecting parents with Learning Support Assistants for children with learning difficulties.

# LSA Service Booking Backend

A Django REST Framework backend for booking Learning Support Assistants (LSAs) for parents.

The project focuses on reliable booking validation, overlap prevention, efficient LSA availability search, an isolated third-party verification integration, automated testing, and PostgreSQL-based CI.

---

## Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Technology Stack](#technology-stack)
- [Architecture](#architecture)
- [Project Structure](#project-structure)
- [Database Design](#database-design)
- [Installation](#installation)
- [Environment Variables](#environment-variables)
- [Running the Project](#running-the-project)
- [API Documentation](#api-documentation)
- [Booking Validation](#booking-validation)
- [Double-Booking Prevention](#double-booking-prevention)
- [LSA Search and N+1 Prevention](#lsa-search-and-n1-prevention)
- [Third-Party Verification Service](#third-party-verification-service)
- [Error Handling](#error-handling)
- [Testing](#testing)
- [GitHub Actions CI](#github-actions-ci)
- [Design Decisions](#design-decisions)

---
## Overview

The LSA Service Booking Backend provides two core API capabilities:

1. Create a booking between a Parent and an active LSA.
2. Search active LSAs by skill and optional availability window.

The booking workflow validates the request, optionally performs external verification, checks for overlapping bookings, and persists the booking safely.

The implementation deliberately keeps business logic outside the API views so that it can be reused and tested independently of HTTP.

---

## Features

- Parent, LSA, and BookingRequest data models.
- PostgreSQL database support.
- Django REST Framework APIs.
- Booking time-range validation.
- Active/inactive LSA validation.
- Parent and LSA existence validation.
- Overlap detection using database queries.
- Cancelled bookings do not block availability.
- Back-to-back bookings are allowed.
- Concurrency-safe booking creation using `select_for_update()` on the LSA row.
- Short database transaction around the critical booking operation.
- Optional third-party verification using `requests`.
- Timeout, connection, HTTP-status, JSON, and response-shape handling for the verification service.
- Correlated `Exists` query for N+1-safe LSA availability search.
- Domain-specific exceptions separated from HTTP concerns.
- Automated pytest/pytest-django tests.
- PostgreSQL service in GitHub Actions CI.

---

## Technology Stack

| Area | Technology |
|---|---|
| Language | Python 3.12 |
| Web framework | Django |
| API framework | Django REST Framework |
| Database | PostgreSQL |
| Testing | pytest, pytest-django |
| HTTP client | requests |
| Configuration | python-dotenv + python-decouple |
| CI | GitHub Actions |

---

## Architecture

The project uses a layered architecture:

```text
HTTP Request
     |
     v
+---------------------------+
| DRF API Layer             |
| booking_service/views.py          |
| - parse request            |
| - serialize response       |
| - map domain errors        |
+-------------+-------------+
              |
              v
+---------------------------+
| Service Layer              |
| booking_service/services.py       |
| - validation               |
| - verification             |
| - overlap detection        |
| - transaction handling     |
+-------------+-------------+
              |
       +------+------+
       |             |
       v             v
+-------------+  +-----------------------------+
| Django ORM  |  | Verification Integration     |
| PostgreSQL  |  | booking_service/integrations/ |
+-------------+  | verification_service.py      |
                  +-------------+--------------+
                                |
                                v
                            requests
                                |
                                v
                     External Verification API
```

The service layer does not depend on DRF. HTTP status-code decisions remain in the API layer.

---

## Project Structure

```text
.
├── manage.py
├── requirements.txt
├── pytest.ini
├── .env.example
├── .gitignore
├── README.md
│
├── .github/
│   └── workflows/
│       └── tests.yml
│
├── lsa_backend/
│   ├── settings.py
│   ├── urls.py
│   ├── asgi.py
│   └── wsgi.py
│
└── booking_service/
    ├── models.py
    ├── serializers.py
    ├── services.py
    ├── exceptions.py
    ├── views.py
    ├── urls.py
    ├── admin.py
    ├── tests.py
    ├── migrations/
    └── integrations/
        ├── __init__.py
        └── verification_service.py
```

---

## Database Design

### Parent

Table:

```text
parents
```

Fields:

| Field | Type | Description |
|---|---|---|
| `id` | BigAutoField | Primary key |
| `name` | CharField(255) | Parent name |
| `email` | EmailField | Unique email |
| `phone` | CharField(20) | Contact number |
| `created_at` | DateTimeField | Creation timestamp |

### LSAProfile

Table:

```text
lsa_profiles
```

Fields:

| Field | Type | Description |
|---|---|---|
| `id` | BigAutoField | Primary key |
| `name` | CharField(255) | LSA name |
| `email` | EmailField | Unique email |
| `skills` | TextField | Skills/specialties |
| `experience` | PositiveIntegerField | Years of experience |
| `is_active` | BooleanField | Whether the LSA can receive bookings |
| `created_at` | DateTimeField | Creation timestamp |

### BookingRequest

Table:

```text
booking_requests
```

Fields:

| Field | Type | Description |
|---|---|---|
| `id` | BigAutoField | Primary key |
| `parent` | ForeignKey | Parent who made the booking |
| `lsa` | ForeignKey | LSA being booked |
| `start_time` | DateTimeField | Booking start |
| `end_time` | DateTimeField | Booking end |
| `status` | CharField | pending / confirmed / cancelled / completed |
| `created_at` | DateTimeField | Creation timestamp |
| `updated_at` | DateTimeField | Last update timestamp |

A database-level `CheckConstraint` enforces:

```text
end_time > start_time
```

Booking queries use indexes including:

```text
(status)
(start_time)
(lsa, start_time)
(parent, start_time)
```

The email fields are unique, so separate redundant email indexes are not required.

---

## Relationships

```text
Parent (1)
    |
    | 1-to-many
    v
BookingRequest
    ^
    | many-to-1
    |
LSAProfile (1)
```

A Parent can have multiple bookings.

An LSA can have multiple bookings.

A BookingRequest belongs to exactly one Parent and one LSA.

### Delete behavior

Both Parent and LSA relationships use `PROTECT`.

This preserves booking history and prevents a Parent or LSA with existing bookings from being deleted accidentally.

For an LSA that should no longer receive bookings, use:

```text
is_active = False
```

instead of deleting the LSA.

---

## Installation

### 1. Clone the repository

```bash
git clone <repository-url>
cd "LSA Service Booking Backend"
```

### 2. Create a virtual environment

Linux/macOS:

```bash
python3 -m venv env
source env/bin/activate
```

Windows PowerShell:

```powershell
python -m venv env
.\env\Scripts\Activate.ps1
```

### 3. Install dependencies

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Create the environment file

Copy:

```text
.env.example
```

to:

```text
.env
```

Then configure the values for your local PostgreSQL instance.

---

## Environment Variables

The project uses `python-dotenv` to load `.env` and `python-decouple` for typed configuration values.

Example:

```env
SECRET_KEY=change-this-in-development
DEBUG=False
ALLOWED_HOSTS=localhost,127.0.0.1

DATABASE_URL=postgresql://lsa_booking_user:your-password@localhost:5432/lsa_booking

TIME_ZONE=UTC

VERIFICATION_SERVICE_URL=https://mock-verification.example.com/api/verify
VERIFICATION_SERVICE_TIMEOUT=5
ENABLE_EXTERNAL_VERIFICATION=False
```

### Variables

| Variable | Purpose |
|---|---|
| `SECRET_KEY` | Django secret key |
| `DEBUG` | Django debug mode |
| `ALLOWED_HOSTS` | Allowed host names |
| `DATABASE_URL` | PostgreSQL connection URL |
| `TIME_ZONE` | Django timezone |
| `VERIFICATION_SERVICE_URL` | External verification endpoint |
| `VERIFICATION_SERVICE_TIMEOUT` | Verification HTTP timeout in seconds |
| `ENABLE_EXTERNAL_VERIFICATION` | Enables/disables external verification |

Do not commit `.env`.

---

## PostgreSQL Setup

Create a PostgreSQL database and user appropriate for your environment.

Example:

```sql
CREATE USER lsa_booking_user WITH PASSWORD 'your-password';
CREATE DATABASE lsa_booking OWNER lsa_booking_user;
```

Then configure:

```env
DATABASE_URL=postgresql://lsa_booking_user:your-password@localhost:5432/lsa_booking
```

The application uses PostgreSQL through Django's PostgreSQL backend and `dj-database-url`.

---

## Running the Project

Run Django system checks:

```bash
python manage.py check
```

Create/apply migrations:

```bash
python manage.py makemigrations
python manage.py migrate
```

Start the development server:

```bash
python manage.py runserver
```

Health/working endpoint:

```text
GET /api/working/
```

Example response:

```json
{
  "status": "ok",
  "service": "lsa-booking"
}
```

---

# API Documentation

## POST `/api/v1/bookings/`

Creates a booking for a Parent with an active LSA.

### Request

```json
{
  "parent": 1,
  "lsa": 2,
  "start_time": "2026-09-01T10:00:00Z",
  "end_time": "2026-09-01T11:00:00Z"
}
```

### Success — `201 Created`

```json
{
  "id": 5,
  "parent": 1,
  "parent_name": "Jane Doe",
  "lsa": 2,
  "lsa_name": "Alice Math",
  "start_time": "2026-09-01T10:00:00Z",
  "end_time": "2026-09-01T11:00:00Z",
  "status": "pending",
  "created_at": "2026-08-12T09:00:00Z",
  "updated_at": "2026-08-12T09:00:00Z"
}
```

### Possible responses

| HTTP status | Meaning |
|---|---|
| `201` | Booking created |
| `400` | Invalid request, inactive LSA, invalid time range, or verification rejection |
| `404` | Parent or LSA does not exist |
| `409` | Requested time overlaps an existing booking |
| `502` | External verification service unavailable |
| `500` | Unexpected server error |

---

## GET `/api/v1/lsas/search/`

Returns active LSAs, optionally filtered by skill and/or availability.

### Skill search

```text
GET /api/v1/lsas/search/?skill=math
```

### Availability search

```text
GET /api/v1/lsas/search/?start_time=2026-08-12T10:00:00Z&end_time=2026-08-12T11:00:00Z
```

### Skill + availability

```text
GET /api/v1/lsas/search/?skill=math&start_time=2026-08-12T10:00:00Z&end_time=2026-08-12T11:00:00Z
```

`start_time` and `end_time` must be provided together.

### Response

```json
[
  {
    "id": 1,
    "name": "Alice Math",
    "email": "alice@example.com",
    "skills": "math, algebra",
    "experience": 3,
    "is_active": true,
    "created_at": "2026-08-11T18:36:29.795679Z"
  }
]
```

---

# Booking Validation

Booking creation follows these rules:

1. Request fields must have the correct type.
2. Parent must exist.
3. LSA must exist.
4. LSA must be active.
5. `end_time` must be strictly greater than `start_time`.
6. If external verification is enabled, verification must succeed.
7. The requested time must not overlap an existing non-cancelled booking for the same LSA.

---

# Double-Booking Prevention

The overlap condition is:

```text
existing.start_time < requested.end_time
AND
existing.end_time > requested.start_time
```

Therefore:

| Existing | Requested | Result |
|---|---|---|
| 10:00–11:00 | 10:30–11:30 | Rejected |
| 10:00–11:00 | 09:30–10:30 | Rejected |
| 10:00–11:00 | 09:00–10:00 | Allowed |
| 10:00–11:00 | 11:00–12:00 | Allowed |

Back-to-back bookings are intentionally allowed.

Cancelled bookings do not block a time slot.

## Concurrency safety

The final booking operation runs inside a short `transaction.atomic()` block.

The transaction locks the **LSAProfile row itself**:

```python
lsa = (
    LSAProfile.objects
    .select_for_update()
    .get(pk=lsa_id)
)
```

The LSA row is used as the serialization point because an LSA can have zero existing bookings. Locking only existing BookingRequest rows would not be safe when there is no row to lock.

The critical sequence is:

```text
BEGIN TRANSACTION
        |
        v
SELECT LSA FOR UPDATE
        |
        v
Check overlapping bookings
        |
        v
Create BookingRequest
        |
        v
COMMIT
```

Concurrent booking attempts for the same LSA therefore cannot both pass the overlap check before either transaction commits.

External HTTP verification is deliberately performed **before** this transaction so that a slow or unavailable third-party service does not hold database locks or keep the booking transaction open.

---

# LSA Search and N+1 Prevention

A naive implementation could produce an N+1 query pattern:

```python
lsas = LSAProfile.objects.filter(is_active=True)

for lsa in lsas:
    BookingRequest.objects.filter(
        lsa=lsa,
        ...
    ).exists()
```

That would require one query for the LSA list plus additional queries for individual LSAs.

The project instead uses Django's `Exists` and `OuterRef`:

```python
overlapping_bookings = BookingRequest.objects.filter(
    lsa=OuterRef("pk"),
    start_time__lt=end_time,
    end_time__gt=start_time,
).exclude(
    status=BookingRequest.Status.CANCELLED
)

queryset = queryset.annotate(
    has_conflicting_booking=Exists(overlapping_bookings)
).filter(
    has_conflicting_booking=False
)
```

The availability condition is therefore evaluated by PostgreSQL as part of the query rather than by issuing one booking query per LSA.

The test suite includes a query-count regression test to protect this behavior.

---

# Third-Party Verification Service

The integration lives in:

```text
booking/integrations/verification_service.py
```

The application uses `requests` to communicate with the configured external verification endpoint.

### Responsibilities

The integration handles:

- HTTP POST requests.
- Configurable timeout.
- Optional API key.
- Connection errors.
- Timeouts.
- Other `requests` exceptions.
- Non-2xx responses.
- Invalid JSON.
- Missing `verified` response field.

All transport-level failures are converted to:

```python
VerificationServiceError
```

Successful responses are represented by:

```python
VerificationResult(
    verified=...,
    reason=...,
    reference_id=...
)
```

The API key is never written to logs.

### Feature flag

External verification is disabled by default:

```env
ENABLE_EXTERNAL_VERIFICATION=False
```

Enable it when an external verification endpoint is available:

```env
ENABLE_EXTERNAL_VERIFICATION=True
```

### Transaction boundary

When enabled, the verification call happens before the database transaction:

```text
Validate request
      |
      v
External verification
      |
      v
Short DB transaction
      |
      v
Lock LSA
      |
      v
Check overlap
      |
      v
Create booking
```

This prevents third-party latency from holding database locks.

Automated tests mock the HTTP request and never depend on the real external service.

---

# Error Handling

The service layer uses domain-specific exceptions:

```text
ParentNotFound
LSANotFound
LSAInactive
InvalidBookingTimeRange
OverlappingBooking
ExternalVerificationFailed
ExternalVerificationUnavailable
```

The API layer maps these to HTTP responses:

```text
ParentNotFound                  -> 404
LSANotFound                     -> 404
LSAInactive                     -> 400
InvalidBookingTimeRange         -> 400
ExternalVerificationFailed     -> 400
ExternalVerificationUnavailable -> 502
OverlappingBooking              -> 409
Unexpected exception             -> 500
```

Unexpected internal exception details are not returned to API clients. They are logged server-side while the client receives a generic error response.

---

# Testing

Run the complete test suite:

```bash
pytest -v
```

The current project keeps its tests in:

```text
booking_service/tests.py
```

The suite covers the main booking, search, API, verification, and concurrency behavior, including:

- Successful booking creation.
- Invalid time ranges.
- Missing Parent.
- Missing LSA.
- Inactive LSA.
- Overlapping bookings.
- Back-to-back bookings.
- Cancelled bookings.
- Skill-based LSA search.
- Availability filtering.
- N+1 query regression.
- External verification success.
- External verification rejection.
- Verification timeout.
- Verification connection failure.
- Non-2xx responses.
- Invalid JSON.
- Missing verification response fields.
- API error mapping.
- Concurrent booking attempts.

Third-party HTTP calls are mocked during tests, so the test suite does not require internet access.

---

# GitHub Actions CI

The workflow is:

```text
.github/workflows/tests.yml
```

It runs on:

```text
push
pull_request
```

The CI pipeline:

1. Checks out the repository.
2. Sets up Python 3.12.
3. Starts PostgreSQL 16 as a service.
4. Waits for PostgreSQL to become available.
5. Installs `requirements.txt`.
6. Runs Django system checks.
7. Runs database migrations.
8. Runs pytest.

CI uses the same database configuration style as the application:

```env
DATABASE_URL=postgresql://lsa_booking_user:ci_test_password@localhost:5432/lsa_booking_test
```

The external verification feature is disabled in CI so that automated tests never accidentally make a real external request.

---

# Design Decisions

## Service layer

Business logic is kept in `booking_service/services.py` rather than placing it directly inside API views.

This keeps:

- validation,
- booking rules,
- overlap detection,
- transaction handling,
- verification

independent of HTTP.

## Domain exceptions

The service layer raises domain-specific Python exceptions instead of DRF exceptions.

The API layer is responsible for translating those exceptions into HTTP status codes.

## LSA row locking

The LSA row is locked with `select_for_update()` during the critical booking transaction.

This is preferable to locking existing booking rows because an LSA may have no existing bookings.

## Database constraint

The database enforces:

```text
end_time > start_time
```

This provides a second layer of protection underneath serializer and service validation.

## EXISTS for availability

The LSA availability search uses a correlated `Exists` query instead of Python-level iteration, avoiding an N+1 query pattern.

## Isolated external integration

All `requests` logic lives in the verification integration module. The rest of the application does not depend on `requests.Response` or transport-specific exceptions.

## Feature flag

External verification is feature-flagged so the core booking system can operate independently of the external service when it is disabled.

---