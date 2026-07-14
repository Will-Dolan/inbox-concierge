import secrets

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import get_settings
from core.crypto import encrypt
from core.db import get_db
from core.deps import get_current_user
from core.google_oauth import build_auth_url, exchange_code_for_tokens, verify_id_token
from core.models import User
from core.session import SESSION_COOKIE_NAME, SESSION_TTL, create_session_token

router = APIRouter(prefix="/auth/google", tags=["auth"])
me_router = APIRouter(tags=["auth"])


@me_router.get("/auth/me")
async def me(user: User = Depends(get_current_user)) -> dict:
    return {"id": str(user.id), "email": user.email}


@router.get("/login")
async def login() -> RedirectResponse:
    state = secrets.token_urlsafe(16)
    return RedirectResponse(build_auth_url(state))


@router.get("/callback")
async def callback(code: str, db: AsyncSession = Depends(get_db)) -> RedirectResponse:
    tokens = await exchange_code_for_tokens(code)
    if "refresh_token" not in tokens:
        raise HTTPException(
            400,
            "Google did not return a refresh token. Revoke this app's access at "
            "myaccount.google.com/permissions and retry.",
        )
    claims = verify_id_token(tokens["id_token"])

    result = await db.execute(select(User).where(User.google_sub == claims["sub"]))
    user = result.scalar_one_or_none()
    if user is None:
        user = User(
            google_sub=claims["sub"],
            email=claims["email"],
            encrypted_refresh_token=encrypt(tokens["refresh_token"]),
        )
        db.add(user)
    else:
        user.encrypted_refresh_token = encrypt(tokens["refresh_token"])
        user.email = claims["email"]
    await db.commit()
    await db.refresh(user)

    settings = get_settings()
    session_token = create_session_token(str(user.id))
    response = RedirectResponse(settings.frontend_origin)
    response.set_cookie(
        SESSION_COOKIE_NAME,
        session_token,
        httponly=True,
        secure=settings.env != "local",
        samesite="none" if settings.env != "local" else "lax",
        max_age=int(SESSION_TTL.total_seconds()),
    )
    return response


@router.post("/logout")
async def logout(response: Response) -> Response:
    # Called via fetch from the SPA, not a page navigation, so this returns a
    # plain response rather than a redirect (which fetch would follow into
    # the frontend's HTML and fail to parse as JSON).
    response.delete_cookie(SESSION_COOKIE_NAME)
    response.status_code = 204
    return response
