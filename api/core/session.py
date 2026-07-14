from datetime import UTC, datetime, timedelta

from jose import JWTError, jwt

from core.config import get_settings

ALGORITHM = "HS256"
SESSION_COOKIE_NAME = "session"
SESSION_TTL = timedelta(days=14)


def create_session_token(user_id: str) -> str:
    settings = get_settings()
    expire = datetime.now(UTC) + SESSION_TTL
    return jwt.encode({"sub": user_id, "exp": expire}, settings.session_secret, algorithm=ALGORITHM)


def decode_session_token(token: str) -> str | None:
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.session_secret, algorithms=[ALGORITHM])
    except JWTError:
        return None
    return payload.get("sub")
