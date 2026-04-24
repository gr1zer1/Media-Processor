from datetime import datetime, timedelta, timezone
import uuid

from users.routes import get_current_user
from fastapi import Depends, HTTPException, status
from jose import JWTError, jwt

from .config import config
from .models.user import UserModel


def create_access_token(user_id: int, role:str, token_version:int | None = 0) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=config.access_token_expire_minutes
    )
    return jwt.encode(
        {
            "sub": str(user_id),
            "exp": expire,
            "role":role,
            "token_version": token_version,
            "type": "access",
        },
        key=config.jwt_secret_key,
        algorithm=config.jwt_algorithm,
    )


def create_refresh_token(user_id: int,role:str,token_version:int | None = 0) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        days=config.refresh_token_expire_days
    )
    jti = str(uuid.uuid4())


    return jwt.encode(
        {
            "sub": str(user_id),
            "exp": expire,
            "jti": jti,
            "role":role,
            "token_version": token_version,
            "role": role,
            "type": "refresh"
        },
        config.jwt_secret_key,
        config.jwt_algorithm,
    )


def decode_token(token: str) -> dict:
    try:
        payload = jwt.decode(
            token=token, key=config.jwt_secret_key, algorithms=[config.jwt_algorithm]
        )
        return payload
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Token!"
        )


def require_role(*roles: str) -> callable:

    async def dependency(
        current_user: UserModel = Depends(get_current_user),
    ) -> UserModel:
        if current_user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        return current_user

    return dependency
