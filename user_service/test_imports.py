from core import (
    Base,
    UserModel,
    config,
    create_access_token,
    create_refresh_token,
    db_helper,
    decode_token,
    hash_password,
    verify_password,
)
from main import app
from users.routes import router as users_router


def test_core_imports_are_available():
    assert config.database_url
    assert db_helper is not None
    assert Base is not None
    assert UserModel is not None
    assert create_access_token is not None
    assert create_refresh_token is not None
    assert decode_token is not None
    assert hash_password is not None
    assert verify_password is not None
    assert users_router is not None
    assert app.title == "Task Manager API"
