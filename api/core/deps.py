import uuid

from fastapi import Cookie, Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.db import get_db
from core.models import User
from core.session import SESSION_COOKIE_NAME, decode_session_token


async def get_current_user(
    session: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> User:
    # Frontend and API deploy to different sites in production, and browsers
    # now block third-party cookies outright (SameSite=None isn't enough), so
    # the SPA sends the session as a Bearer token instead. The cookie path is
    # kept for local dev, where both run on localhost.
    token = session
    if token is None and authorization and authorization.lower().startswith("bearer "):
        token = authorization[len("bearer ") :]
    if token is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    user_id = decode_session_token(token)
    if user_id is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid session")
    user = await db.get(User, uuid.UUID(user_id))
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found")
    return user
