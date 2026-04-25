import secrets

def make_url() -> str:
    return secrets.token_urlsafe(8)