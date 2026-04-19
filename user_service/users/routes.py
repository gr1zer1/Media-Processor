from typing import Annotated, List

from datetime import datetime, timezone

from core import UserModel

from core.db import db_helper

from core.config import config

from core.auth import decode_token, require_role, create_access_token, create_refresh_token
from core.utility import hash_password, verify_password
from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Query, Response, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select,update
from sqlalchemy.ext.asyncio import AsyncSession

from fastapi_limiter.depends import RateLimiter

from users.schemas import UserResponseSchema, UserSchema, ChangePasswordRequestSchema

SessionDep = Annotated[AsyncSession, Depends(db_helper.get_session)]

router = APIRouter(tags=["Users"])




async def get_current_user(
    session: SessionDep, authorization: str | None = Header(default=None)
) -> UserModel:
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header",
        )

    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization scheme",
        )

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





@router.post(
            "/register",
            dependencies=[Depends(RateLimiter(times=20, seconds=60))],
            )
async def register(
    response: Response,
    user: UserSchema,
    session: SessionDep,
):
    stmt = select(UserModel).where(UserModel.email == user.email)
    existing_user_result = await session.execute(stmt)

    if existing_user_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User with this email already exists",
        )

    new_user = UserModel(
        email=user.email,
        password=hash_password(user.password),
        role="user",
    )

    session.add(new_user)
    await session.commit()
    await session.refresh(new_user)

    access_token = create_access_token(new_user.id,new_user.role )
    refresh_token = create_refresh_token(new_user.id,new_user.role)

    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        max_age=config.refresh_token_expire_days
        * 24
        * 60
        * 60,
        httponly=True,
        samesite="lax",
        secure=True,
    )

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": UserResponseSchema.model_validate(new_user),
    }

@router.get(
        "/by-email",
        response_model=UserResponseSchema,
        dependencies=[Depends(RateLimiter(times=20, seconds=60))],
        )
async def get_user_by_email(
    session: SessionDep,
    email: str = Query(...),
    _user:UserModel = Depends(require_role("admin")),
) -> UserResponseSchema:
    stmt = select(UserModel).where(UserModel.email == email)
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )

    return user





@router.post(
        "/login",
        dependencies=[Depends(RateLimiter(times=20, seconds=60))],
        )
async def login(
    response: Response,
    form: Annotated[OAuth2PasswordRequestForm, Depends()],
    session: SessionDep,
) -> dict:
    stmt = select(UserModel).where(UserModel.email == form.username)
    user_result = await session.execute(stmt)
    user_data = user_result.scalar_one_or_none()

    if not user_data or not verify_password(form.password, user_data.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )

    access_token = create_access_token(user_data.id,user_data.role, user_data.token_version)
    refresh_token = create_refresh_token(user_data.id,user_data.role, user_data.token_version)

    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        max_age=config.refresh_token_expire_days
        * 24
        * 60
        * 60,
        httponly=True,
        samesite="lax",
        secure=True,
    )

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": UserResponseSchema.model_validate(user_data),
    }




@router.get(
        "",
        response_model=List[UserResponseSchema],
        )
    
async def get_all_users(session: SessionDep,_user:UserModel = Depends(require_role("admin"))) -> List[UserResponseSchema]:
    stmt = select(UserModel)
    result = await session.execute(stmt)
    return result.scalars().all()


@router.get(
        "/{user_id}",
        response_model=UserResponseSchema,
        dependencies=[Depends(RateLimiter(times=20, seconds=60))],
        )
async def get_user(user_id: int, session: SessionDep,_user:UserModel = Depends(require_role("admin"))) -> UserResponseSchema:
    stmt = select(UserModel).where(UserModel.id == user_id)
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )

    return user


@router.post("/logout")
async def logout(response:Response,refresh_token: str | None = Cookie(default=None)) -> dict:
    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Missing refresh token"
        )

    payload = decode_token(refresh_token)
    jti = payload.get("jti")
    exp = payload.get("exp")

    ttl = exp - int(datetime.now(timezone.utc).timestamp())

    await db_helper.redis_pool.set(f"blacklist:{jti}", "1", ex=ttl)

    response.delete_cookie("refresh_token")

    return {"detail": "Logged out successfully"}

@router.post("/refresh")
async def refresh_token(
    response: Response,
    refresh_token: str | None = Cookie(default=None),
    
) -> dict:
    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Missing refresh token"
        )

    payload = decode_token(refresh_token)
    user_id = payload.get("sub")
    role = payload.get("role")
    jti = payload.get("jti")
    exp = payload.get("exp")
    token_version = payload.get("token_version")

    is_blacklisted = await db_helper.redis_pool.get(f"blacklist:{jti}")
    if is_blacklisted:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Token has been revoked"
        )

    new_access_token = create_access_token(user_id,role,token_version)
    new_refresh_token = create_refresh_token(user_id,role,token_version)

    await db_helper.redis_pool.set(
        f"blacklist:{jti}",
        "1",
        ex=exp - int(datetime.now(timezone.utc).timestamp()),
    )

    response.set_cookie(
        key="refresh_token",
        value=new_refresh_token,
        max_age=config.refresh_token_expire_days
        * 24
        * 60
        * 60,
        httponly=True,
        samesite="lax",
        secure=True,
    )


    return {"access_token": new_access_token, "token_type": "bearer"}

@router.post("/change-password")
async def change_password(
    response:Response,
    data: ChangePasswordRequestSchema,
    session: SessionDep,
    current_user: UserModel = Depends(require_role("user", "admin")),
):
    if not verify_password(data.old_password, current_user.password):
        raise HTTPException(400, "Invalid old password")

    current_user.password = hash_password(data.new_password)

    current_user.token_version += 1

    await session.commit()
    await session.refresh(current_user)

    new_access_token = create_access_token(current_user.id, current_user.role, current_user.token_version)
    new_refresh_token = create_refresh_token(current_user.id, current_user.role, current_user.token_version)

    response.set_cookie(
        key="refresh_token",
        value=new_refresh_token,
        max_age=config.refresh_token_expire_days
        * 24
        * 60
        * 60,
        httponly=True,
        samesite="lax",
        secure=True,
    )

    
    return {
        "access_token": new_access_token,
        "token_type": "bearer",
        "detail": "Password changed successfully"
    }
