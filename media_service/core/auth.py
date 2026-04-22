from jose import JWTError,jwt
from fastapi import HTTPException,status
from core.config import config
from fastapi import Header
from media.schemas import JWTSchema


def decode_token(token: str) -> JWTSchema:
    try:
        payload = jwt.decode(
            token=token, key=config.jwt_secret_key, algorithms=[config.jwt_algorithm]
        )
        return JWTSchema(**payload)
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Token!"
        )
    


def current_user(authorization: str | None = Header(default=None)) -> JWTSchema:
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

    return decode_token(token)