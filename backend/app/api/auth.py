"""Authentication endpoints: register, login, logout, current user."""

from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, HTTPException, Request, Response, status
from sqlalchemy import select

from app.api.deps import CurrentSession, CurrentUser
from app.api.schemas import LoginRequest, RegisterRequest, UserOut
from app.config import get_settings
from app.db.models import Session, User
from app.security import SESSION_COOKIE, hash_password, hash_token, new_session_token, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _set_session_cookie(response: Response, token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=settings.session_ttl_hours * 3600,
        httponly=True,
        samesite="lax",
        secure=not settings.debug,  # HTTPS in production
        path="/",
    )


async def _create_session(response: Response, user: User, db: CurrentSession) -> None:
    settings = get_settings()
    token = new_session_token()
    db.add(
        Session(
            token_hash=hash_token(token),
            user_id=user.id,
            expires_at=dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=settings.session_ttl_hours),
        )
    )
    await db.flush()
    _set_session_cookie(response, token)


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def register(body: RegisterRequest, response: Response, db: CurrentSession) -> User:
    existing = await db.execute(select(User).where(User.email == body.email.lower()))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists")
    user = User(
        email=body.email.lower(),
        name=body.name.strip(),
        password_hash=hash_password(body.password),
    )
    db.add(user)
    await db.flush()
    await _create_session(response, user, db)
    return user


@router.post("/login", response_model=UserOut)
async def login(body: LoginRequest, response: Response, db: CurrentSession) -> User:
    result = await db.execute(select(User).where(User.email == body.email.lower()))
    user = result.scalar_one_or_none()
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")
    await _create_session(response, user, db)
    return user


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(response: Response, db: CurrentSession, request: Request) -> None:
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        result = await db.execute(select(Session).where(Session.token_hash == hash_token(token)))
        sess = result.scalar_one_or_none()
        if sess is not None:
            await db.delete(sess)
            await db.commit()
    response.delete_cookie(SESSION_COOKIE, path="/")


@router.get("/me", response_model=UserOut)
async def me(user: CurrentUser) -> User:
    return user
