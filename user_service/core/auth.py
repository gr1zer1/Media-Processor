from datetime import datetime, timedelta, timezone
import uuid

from fastapi import Depends, HTTPException, status
from jose import JWTError, jwt

from .config import config
from .models.user import UserModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from typing import Annotated
from .db import db_helper
from fastapi import Depends,Query,Header,HTTPException,status

SessionDep = Annotated[AsyncSession,Depends(db_helper.get_session)]


async def get_current_user(
    session: SessionDep,
    authorization: str | None = Header(default=None),
    authorization_query: str | None = Query(default=None),
) -> UserModel:
    if not authorization and not authorization_query:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header",
        )
    if not authorization_query:
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authorization scheme",
            )
    else:
        token = authorization_query

    payload = decode_token(token)
    user_id = payload.get("sub")
    token_version = payload.get("token_version")
    token_id = payload.get("jti")

    if await db_helper.redis_pool.get(f"blacklist:{token_id}"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Token has been revoked"
        )
    

    stmt = select(UserModel).where(UserModel.id == int(user_id))
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )
    
    if user.token_version != token_version:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has been revoked",
        )
    
    return user



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
