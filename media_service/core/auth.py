from jose import JWTError,jwt
from fastapi import HTTPException,status
from core.config import config

from media.schemas import JWTSchema


def decode_token(token: str) -> JWTSchema:
    try:
        payload = jwt.decode(
            token=token, key=config.jwt_secret_key, algorithms=[config.jwt_algorithm]
        )
        return JWTSchema(**payload))
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Token!"
        )