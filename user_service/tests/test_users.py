from types import SimpleNamespace

import pytest
from fastapi import HTTPException, Response

from core import UserModel
from core.auth import require_role
from core.utility import hash_password, verify_password
from users.routes import (
    change_password,
    get_current_user,
    get_user_by_email,
    login,
    logout,
    refresh_token,
    register,
)
from users.schemas import ChangePasswordRequestSchema, UserSchema


class FakeResult:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class FakeSession:
    def __init__(self, results=None):
        self.results = list(results or [])
        self.added = []
        self.committed = False
        self.refreshed = []

    async def execute(self, _stmt):
        if self.results:
            return FakeResult(self.results.pop(0))
        return FakeResult(None)

    def add(self, item):
        if getattr(item, "id", None) is None:
            item.id = len(self.added) + 1
        self.added.append(item)

    async def commit(self):
        self.committed = True

    async def refresh(self, item):
        self.refreshed.append(item)


class FakeRedisPool:
    def __init__(self):
        self.storage = {}
        self.last_set = None

    async def get(self, key):
        return self.storage.get(key)

    async def set(self, key, value, ex=None):
        self.storage[key] = value
        self.last_set = {"key": key, "value": value, "ex": ex}


@pytest.fixture
def redis_pool(monkeypatch):
    from users import routes

    fake_pool = FakeRedisPool()
    monkeypatch.setattr(routes.db_helper, "redis_pool", fake_pool)
    return fake_pool


@pytest.mark.asyncio
async def test_register_creates_user_hashes_password_and_sets_refresh_cookie():
    response = Response()
    session = FakeSession(results=[None])

    result = await register(
        response,
        UserSchema(email="user@example.com", password="secret123"),
        session,
    )

    created_user = session.added[0]

    assert result["token_type"] == "bearer"
    assert result["user"].email == "user@example.com"
    assert created_user.email == "user@example.com"
    assert created_user.role == "user"
    assert created_user.password != "secret123"
    assert verify_password("secret123", created_user.password)
    assert session.committed is True
    assert session.refreshed == [created_user]
    assert "refresh_token=" in response.headers["set-cookie"]


@pytest.mark.asyncio
async def test_register_rejects_duplicate_email():
    session = FakeSession(results=[SimpleNamespace(email="user@example.com")])

    with pytest.raises(HTTPException) as exc:
        await register(
            Response(),
            UserSchema(email="user@example.com", password="secret123"),
            session,
        )

    assert exc.value.status_code == 409
    assert exc.value.detail == "User with this email already exists"


@pytest.mark.asyncio
async def test_login_returns_tokens_and_user_payload():
    session = FakeSession(
        results=[
            UserModel(
                id=7,
                email="user@example.com",
                password=hash_password("secret123"),
                role="admin",
                token_version=3,
            )
        ]
    )
    response = Response()

    result = await login(
        response,
        SimpleNamespace(username="user@example.com", password="secret123"),
        session,
    )

    assert result["token_type"] == "bearer"
    assert result["user"].email == "user@example.com"
    assert result["user"].role == "admin"
    assert result["access_token"]
    assert "refresh_token=" in response.headers["set-cookie"]


@pytest.mark.asyncio
async def test_login_rejects_wrong_password():
    session = FakeSession(
        results=[
            UserModel(
                id=7,
                email="user@example.com",
                password=hash_password("secret123"),
                role="user",
                token_version=0,
            )
        ]
    )

    with pytest.raises(HTTPException) as exc:
        await login(
            Response(),
            SimpleNamespace(username="user@example.com", password="wrong-pass"),
            session,
        )

    assert exc.value.status_code == 401
    assert exc.value.detail == "Incorrect email or password"


@pytest.mark.asyncio
async def test_get_current_user_requires_authorization_header():
    with pytest.raises(HTTPException) as exc:
        await get_current_user(FakeSession(), None)

    assert exc.value.status_code == 401
    assert exc.value.detail == "Missing Authorization header"


@pytest.mark.asyncio
async def test_get_current_user_rejects_blacklisted_token(monkeypatch, redis_pool):
    from users import routes

    redis_pool.storage["blacklist:revoked-jti"] = "1"
    monkeypatch.setattr(
        routes,
        "decode_token",
        lambda _token: {"sub": "5", "token_version": 0, "jti": "revoked-jti"},
    )

    with pytest.raises(HTTPException) as exc:
        await get_current_user(
            FakeSession(results=[UserModel(id=5, email="user@example.com", password="x", role="user", token_version=0)]),
            "Bearer access-token",
        )

    assert exc.value.status_code == 401
    assert exc.value.detail == "Token has been revoked"


@pytest.mark.asyncio
async def test_get_current_user_rejects_token_version_mismatch(monkeypatch, redis_pool):
    from users import routes

    monkeypatch.setattr(
        routes,
        "decode_token",
        lambda _token: {"sub": "5", "token_version": 1, "jti": "jti-1"},
    )
    session = FakeSession(
        results=[
            UserModel(
                id=5,
                email="user@example.com",
                password="hashed",
                role="user",
                token_version=2,
            )
        ]
    )

    with pytest.raises(HTTPException) as exc:
        await get_current_user(session, "Bearer access-token")

    assert exc.value.status_code == 401
    assert exc.value.detail == "Token has been revoked"


@pytest.mark.asyncio
async def test_get_user_by_email_returns_user():
    session = FakeSession(
        results=[
            UserModel(id=3, email="lookup@example.com", password="hashed", role="user")
        ]
    )

    result = await get_user_by_email(session, "lookup@example.com", SimpleNamespace(role="admin"))

    assert result.email == "lookup@example.com"


@pytest.mark.asyncio
async def test_logout_blacklists_refresh_token_and_clears_cookie(monkeypatch, redis_pool):
    from users import routes

    monkeypatch.setattr(
        routes,
        "decode_token",
        lambda _token: {"jti": "refresh-1", "exp": 4_200_000_000},
    )
    response = Response()

    result = await logout(response, "refresh-token")

    assert result == {"detail": "Logged out successfully"}
    assert redis_pool.last_set["key"] == "blacklist:refresh-1"
    assert redis_pool.last_set["value"] == "1"
    assert "refresh_token=\"\"" in response.headers["set-cookie"]


@pytest.mark.asyncio
async def test_refresh_token_rotates_tokens_and_blacklists_previous_token(monkeypatch, redis_pool):
    from users import routes

    monkeypatch.setattr(
        routes,
        "decode_token",
        lambda _token: {
            "sub": "7",
            "role": "admin",
            "jti": "refresh-1",
            "exp": 4_200_000_000,
            "token_version": 3,
        },
    )
    response = Response()

    result = await refresh_token(response, "refresh-token")

    assert result["token_type"] == "bearer"
    assert result["access_token"]
    assert redis_pool.last_set["key"] == "blacklist:refresh-1"
    assert "refresh_token=" in response.headers["set-cookie"]


@pytest.mark.asyncio
async def test_refresh_token_rejects_blacklisted_token(monkeypatch, redis_pool):
    from users import routes

    redis_pool.storage["blacklist:refresh-1"] = "1"
    monkeypatch.setattr(
        routes,
        "decode_token",
        lambda _token: {
            "sub": "7",
            "role": "admin",
            "jti": "refresh-1",
            "exp": 4_200_000_000,
            "token_version": 3,
        },
    )

    with pytest.raises(HTTPException) as exc:
        await refresh_token(Response(), "refresh-token")

    assert exc.value.status_code == 401
    assert exc.value.detail == "Token has been revoked"


@pytest.mark.asyncio
async def test_change_password_updates_hash_and_token_version():
    user = UserModel(
        id=11,
        email="user@example.com",
        password=hash_password("old-secret"),
        role="user",
        token_version=2,
    )
    response = Response()
    session = FakeSession()

    result = await change_password(
        response,
        ChangePasswordRequestSchema(
            old_password="old-secret",
            new_password="new-secret123",
        ),
        session,
        user,
    )

    assert result["detail"] == "Password changed successfully"
    assert result["token_type"] == "bearer"
    assert verify_password("new-secret123", user.password)
    assert user.token_version == 3
    assert session.committed is True
    assert session.refreshed == [user]
    assert "refresh_token=" in response.headers["set-cookie"]


@pytest.mark.asyncio
async def test_change_password_rejects_invalid_old_password():
    user = UserModel(
        id=11,
        email="user@example.com",
        password=hash_password("old-secret"),
        role="user",
        token_version=2,
    )

    with pytest.raises(HTTPException) as exc:
        await change_password(
            Response(),
            ChangePasswordRequestSchema(
                old_password="wrong-secret",
                new_password="new-secret123",
            ),
            FakeSession(),
            user,
        )

    assert exc.value.status_code == 400
    assert exc.value.detail == "Invalid old password"


@pytest.mark.asyncio
async def test_require_role_rejects_forbidden_role():
    dependency = require_role("admin")

    with pytest.raises(HTTPException) as exc:
        await dependency(current_user=SimpleNamespace(role="user"))

    assert exc.value.status_code == 403
    assert exc.value.detail == "Insufficient permissions"


def test_change_password_schema_rejects_same_password():
    with pytest.raises(ValueError, match="New password must be different from old password"):
        ChangePasswordRequestSchema(
            old_password="same-secret",
            new_password="same-secret",
        )
