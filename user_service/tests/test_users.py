import pytest
from httpx import AsyncClient
from sqlalchemy import select

from core import UserModel
from core.auth import decode_token
from core.utility import verify_password


REGISTER_URL = "/users/register"
LOGIN_URL = "/users/login"
CURRENT_USER_URL = "/users/users/by-jwt"
REFRESH_URL = "/users/refresh"
LOGOUT_URL = "/users/logout"
CHANGE_PASSWORD_URL = "/users/change-password"


async def register_user(
    client: AsyncClient,
    email: str = "user@example.com",
    password: str = "secret123",
):
    return await client.post(
        REGISTER_URL,
        json={"email": email, "password": password},
    )


async def login_user(
    client: AsyncClient,
    email: str = "user@example.com",
    password: str = "secret123",
):
    return await client.post(
        LOGIN_URL,
        data={"username": email, "password": password},
    )


@pytest.mark.asyncio
async def test_register_creates_user_with_hashed_password(client: AsyncClient, setup_db):
    response = await register_user(client)

    assert response.status_code == 200

    payload = response.json()
    assert payload["token_type"] == "bearer"
    assert payload["user"]["email"] == "user@example.com"
    assert payload["user"]["role"] == "user"
    assert "refresh_token" in response.cookies

    async with setup_db["session_factory"]() as session:
        result = await session.execute(
            select(UserModel).where(UserModel.email == "user@example.com")
        )
        user = result.scalar_one()

    assert user.password != "secret123"
    assert verify_password("secret123", user.password)
    assert user.quota_used == 0
    assert user.quota_limit == 1_073_741_824


@pytest.mark.asyncio
async def test_register_rejects_duplicate_email(client: AsyncClient):
    first_response = await register_user(client)
    second_response = await register_user(client)

    assert first_response.status_code == 200
    assert second_response.status_code == 409
    assert second_response.json()["detail"] == "User with this email already exists"


@pytest.mark.asyncio
async def test_register_rejects_invalid_email(client: AsyncClient):
    response = await client.post(
        REGISTER_URL,
        json={"email": "test.com", "password": "secret123"},
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_login_returns_access_token_and_user_payload(client: AsyncClient):
    await register_user(client)

    response = await login_user(client)

    assert response.status_code == 200

    payload = response.json()
    assert payload["token_type"] == "bearer"
    assert payload["user"]["email"] == "user@example.com"
    assert payload["access_token"]
    assert "refresh_token" in response.cookies


@pytest.mark.asyncio
async def test_login_rejects_wrong_password(client: AsyncClient):
    await register_user(client)

    response = await login_user(client, password="wrong-pass")

    assert response.status_code == 401
    assert response.json()["detail"] == "Incorrect email or password"


@pytest.mark.asyncio
async def test_get_current_user_by_jwt_returns_registered_user(client: AsyncClient):
    register_response = await register_user(client)
    access_token = register_response.json()["access_token"]

    response = await client.get(
        CURRENT_USER_URL,
        headers={"Authorization": f"Bearer {access_token}"},
    )

    assert response.status_code == 200
    assert response.json()["email"] == "user@example.com"


@pytest.mark.asyncio
async def test_get_current_user_by_jwt_requires_token(client: AsyncClient):
    response = await client.get(CURRENT_USER_URL)

    assert response.status_code == 401
    assert response.json()["detail"] == "Missing Authorization header"


@pytest.mark.asyncio
async def test_refresh_rotates_tokens_and_blacklists_previous_refresh_token(
    client: AsyncClient, setup_db
):
    await register_user(client)
    original_refresh_token = client.cookies.get("refresh_token")

    response = await client.post(REFRESH_URL)

    assert response.status_code == 200

    payload = response.json()
    assert payload["token_type"] == "bearer"
    assert payload["access_token"]

    new_refresh_token = client.cookies.get("refresh_token")
    assert new_refresh_token
    assert new_refresh_token != original_refresh_token

    original_refresh_payload = decode_token(original_refresh_token)
    blacklisted_token = await setup_db["redis"].get(
        f"blacklist:{original_refresh_payload['jti']}"
    )
    assert blacklisted_token == "1"


@pytest.mark.asyncio
async def test_logout_blacklists_refresh_token_and_clears_cookie(client: AsyncClient, setup_db):
    await register_user(client)
    refresh_token = client.cookies.get("refresh_token")
    refresh_payload = decode_token(refresh_token)

    response = await client.post(LOGOUT_URL)

    assert response.status_code == 200
    assert response.json()["detail"] == "Logged out successfully"
    assert client.cookies.get("refresh_token") is None

    blacklisted_token = await setup_db["redis"].get(
        f"blacklist:{refresh_payload['jti']}"
    )
    assert blacklisted_token == "1"


@pytest.mark.asyncio
async def test_change_password_updates_credentials_and_revokes_old_access(client: AsyncClient):
    register_response = await register_user(client, password="old-secret1")
    old_access_token = register_response.json()["access_token"]

    response = await client.post(
        CHANGE_PASSWORD_URL,
        json={"old_password": "old-secret1", "new_password": "new-secret123"},
        headers={"Authorization": f"Bearer {old_access_token}"},
    )

    assert response.status_code == 200
    assert response.json()["detail"] == "Password changed successfully"
    assert response.json()["access_token"]

    old_token_response = await client.get(
        CURRENT_USER_URL,
        headers={"Authorization": f"Bearer {old_access_token}"},
    )
    assert old_token_response.status_code == 401
    assert old_token_response.json()["detail"] == "Token has been revoked"

    login_response = await login_user(client, password="new-secret123")
    assert login_response.status_code == 200


@pytest.mark.asyncio
async def test_change_password_rejects_invalid_old_password(client: AsyncClient):
    register_response = await register_user(client, password="old-secret1")
    access_token = register_response.json()["access_token"]

    response = await client.post(
        CHANGE_PASSWORD_URL,
        json={"old_password": "wrong-secret", "new_password": "new-secret123"},
        headers={"Authorization": f"Bearer {access_token}"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid old password"
