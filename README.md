# 🔐 FastAPI Auth Service

A production-ready authentication microservice built with **FastAPI** and **JWT**. Designed to be reusable — plug it into any project without rewriting auth from scratch.

## Features

- Registration and login with JWT
- Access token + refresh token rotation
- Refresh tokens stored in `httponly` cookies
- Token blacklist via Redis (logout, password change)
- `token_version` — changing password invalidates all other sessions
- Role-based access control (RBAC) via `require_role()`
- Rate limiting on all public endpoints
- PostgreSQL + async SQLAlchemy
- Fully containerized with Docker Compose

## Tech Stack

| Layer | Technology |
|---|---|
| Framework | FastAPI |
| Auth | JWT (python-jose) |
| Password hashing | bcrypt (passlib) |
| Database | PostgreSQL 16 |
| ORM | SQLAlchemy (async) |
| Cache / Blacklist | Redis 7 |
| Rate limiting | fastapi-limiter |
| Containerization | Docker, Docker Compose |

## Endpoints

| Method | Path | Description | Auth |
|---|---|---|---|
| `POST` | `/register` | Create a new user | — |
| `POST` | `/login` | Get access + refresh tokens | — |
| `POST` | `/refresh` | Rotate refresh token | cookie |
| `POST` | `/logout` | Invalidate refresh token | cookie |
| `GET` | `/me` | Get current user info | Bearer |
| `POST` | `/change-password` | Change password, invalidate all sessions | Bearer |
| `GET` | `/` | List all users | Bearer (admin) |
| `GET` | `/{user_id}` | Get user by ID | Bearer (admin) |
| `GET` | `/by-email` | Get user by email | Bearer (admin) |

## Token Flow

```
POST /login
  → access_token (JSON body, 15 min)
  → refresh_token (httponly cookie, 30 days)

POST /refresh
  → new access_token
  → new refresh_token cookie
  → old refresh_token blacklisted in Redis

POST /logout
  → refresh_token blacklisted in Redis
  → cookie cleared

POST /change-password
  → token_version incremented (all other sessions invalidated)
  → new access_token + refresh_token issued for current session
```

## Getting Started

### 1. Clone the repo

```bash
git clone https://github.com/your-username/auth-service.git
cd auth-service
```

### 2. Configure environment variables

```bash
cp .env.example .env
```

Edit `.env`:

```env
POSTGRES_USER=user
POSTGRES_PASSWORD=password
POSTGRES_DB=auth_service
DATABASE_URL=postgresql+asyncpg://user:password@db:5432/auth_service

JWT_SECRET_KEY=your-super-secret-key
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=15
REFRESH_TOKEN_EXPIRE_DAYS=30

REDIS_URL=redis://redis:6379
```

### 3. Run with Docker Compose

```bash
docker-compose up --build
```

The service will be available at `http://localhost:8001`.

Interactive API docs: `http://localhost:8001/docs`

## Running Tests

Tests are located in the `user_service/tests/` directory and use **pytest**.

### Run all tests

```bash
pytest user_service/
```

### Run tests with verbose output

```bash
pytest user_service/ -v
```

### Run specific test file

```bash
pytest user_service/tests/test_users.py -v
```

### Run tests with coverage

```bash
pytest user_service/ --cov=user_service --cov-report=html
```

## Project Structure

```
auth-service/
├── core/
│   ├── auth.py          # JWT creation, decoding, require_role()
│   ├── config.py        # Settings from .env
│   ├── db.py            # SQLAlchemy + Redis setup
│   ├── models.py        # UserModel
│   └── utility.py       # hash_password, verify_password
├── users/
│   ├── router.py        # All endpoints
│   └── schemas.py       # Pydantic schemas
├── .env.example
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```

## User Model

| Field | Type | Description |
|---|---|---|
| `id` | int | Primary key |
| `email` | str | Unique, indexed |
| `password` | str | bcrypt hashed |
| `role` | str | `user` by default |
| `token_version` | int | Increments on password change |
| `created_at` | datetime | Auto timestamp |
| `updated_at` | datetime | Auto timestamp |

## RBAC

Endpoints are protected with `require_role()`:

```python
# single role
_user: UserModel = Depends(require_role("admin"))

# multiple roles
current_user: UserModel = Depends(require_role("user", "admin"))
```

New users are always registered with `role="user"`. Roles can only be changed directly in the database by an admin.

## Using in Other Projects

Run the service as a standalone container and call it over HTTP from any other service:

```python
import httpx

# verify token and get current user
response = httpx.get(
    "http://auth-service:8001/me",
    headers={"Authorization": f"Bearer {access_token}"}
)
user = response.json()
# {"id": 1, "email": "user@example.com", "role": "user"}
```

## License

MIT