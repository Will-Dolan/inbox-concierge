import secrets

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response
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

OAUTH_STATE_COOKIE_NAME = "oauth_state"
OAUTH_STATE_TTL_SECONDS = 5 * 60


@me_router.get("/auth/me")
async def me(user: User = Depends(get_current_user)) -> dict:
    return {"id": str(user.id), "email": user.email}


@router.get("/login")
async def login() -> RedirectResponse:
    settings = get_settings()
    state = secrets.token_urlsafe(16)
    response = RedirectResponse(build_auth_url(state))
    response.set_cookie(
        OAUTH_STATE_COOKIE_NAME,
        state,
        httponly=True,
        secure=settings.env != "local",
        samesite="lax",
        max_age=OAUTH_STATE_TTL_SECONDS,
    )
    return response


@router.get("/callback")
async def callback(
    code: str,
    state: str,
    db: AsyncSession = Depends(get_db),
    oauth_state: str | None = Cookie(default=None, alias=OAUTH_STATE_COOKIE_NAME),
) -> RedirectResponse:
    if oauth_state is None or not secrets.compare_digest(oauth_state, state):
        # Attach a Set-Cookie header (via a throwaway Response) so the
        # single-use oauth_state cookie can't be replayed, even on failure.
        stale_cookie = Response()
        stale_cookie.delete_cookie(OAUTH_STATE_COOKIE_NAME)
        raise HTTPException(400, "Invalid or missing OAuth state", headers=dict(stale_cookie.headers))

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
    is_cross_site = settings.frontend_origin.startswith("https://")
    response.set_cookie(
        SESSION_COOKIE_NAME,
        session_token,
        httponly=True,
        secure=is_cross_site,
        samesite="none" if is_cross_site else "lax",
        max_age=int(SESSION_TTL.total_seconds()),
    )
    response.delete_cookie(OAUTH_STATE_COOKIE_NAME)
    return response


@router.post("/logout")
async def logout(response: Response) -> Response:
    # Called via fetch from the SPA, not a page navigation, so this returns a
    # plain response rather than a redirect (which fetch would follow into
    # the frontend's HTML and fail to parse as JSON).
    response.delete_cookie(SESSION_COOKIE_NAME)
    response.status_code = 204
    return response
