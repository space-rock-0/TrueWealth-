"""Account registration and opaque, server-side cookie sessions."""
from __future__ import annotations

import hashlib
import hmac
import os
import re
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field as PydanticField
from sqlalchemy import delete
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.core.db import AppUser, AuthSession, engine
from app.core.rate_limit import limiter
from app.core.email_delivery import email_configured, send_email

router = APIRouter(prefix="/api/auth", tags=["authentication"])
PRODUCTION = os.getenv("APP_ENV", "development").lower() == "production"
VERIFY_EMAIL = os.getenv("EMAIL_VERIFICATION_REQUIRED", str(PRODUCTION)).lower() == "true"
SESSION_COOKIE = "tw_session"
CSRF_COOKIE = "tw_csrf"
SESSION_DAYS = 7
USERNAME_RE = re.compile(r"^[a-zA-Z0-9_]{3,32}$")
PASSWORD_MIN = 12


def _now():
    return datetime.now(timezone.utc)


def _is_expired(value):
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value <= _now()


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _password_hash(password: str) -> str:
    salt = secrets.token_bytes(16)
    value = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=5, dklen=32)
    return f"scrypt$16384$8$5${salt.hex()}${value.hex()}"


def _password_matches(password: str, encoded: str) -> bool:
    try:
        algorithm, n, r, p, salt_hex, hash_hex = encoded.split("$")
        if algorithm != "scrypt":
            return False
        actual = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt_hex), n=int(n), r=int(r), p=int(p), dklen=len(bytes.fromhex(hash_hex)))
        return hmac.compare_digest(actual, bytes.fromhex(hash_hex))
    except (ValueError, TypeError):
        return False


def _cookie_options():
    return {"httponly": True, "secure": PRODUCTION, "samesite": "lax", "path": "/"}


def _set_csrf(response: Response, token: str):
    response.set_cookie(CSRF_COOKIE, token, max_age=SESSION_DAYS * 86400, httponly=False,
                        secure=PRODUCTION, samesite="lax", path="/")


def _new_session(user: AppUser, response: Response, csrf_token: str):
    token = secrets.token_urlsafe(48)
    with Session(engine) as db:
        db.add(AuthSession(user_id=user.id, token_digest=_digest(token), csrf_digest=_digest(csrf_token),
                           expires_at=_now() + timedelta(days=SESSION_DAYS)))
        db.commit()
    response.set_cookie(SESSION_COOKIE, token, max_age=SESSION_DAYS * 86400, **_cookie_options())
    _set_csrf(response, csrf_token)


def get_current_user(request: Request) -> AppUser:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise HTTPException(status_code=401, detail="Sign in required.")
    with Session(engine) as db:
        record = db.exec(select(AuthSession).where(AuthSession.token_digest == _digest(token))).first()
        if not record or _is_expired(record.expires_at):
            if record:
                db.delete(record)
                db.commit()
            raise HTTPException(status_code=401, detail="Session expired. Please sign in again.")
        user = db.get(AppUser, record.user_id)
        if not user or not user.is_active or (VERIFY_EMAIL and not user.email_verified):
            raise HTTPException(status_code=401, detail="Account is unavailable.")
        return user


def require_csrf(request: Request):
    cookie_token = request.cookies.get(CSRF_COOKIE, "")
    header_token = request.headers.get("X-CSRF-Token", "")
    origin = request.headers.get("origin")
    if not cookie_token or not header_token or not hmac.compare_digest(cookie_token, header_token):
        raise HTTPException(status_code=403, detail="CSRF validation failed.")
    if origin:
        allowed = {v.strip().rstrip("/") for v in os.getenv(
            "APP_ALLOWED_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000"
        ).split(",") if v.strip()}
        if origin.rstrip("/") not in allowed and origin.rstrip("/") != f"{request.url.scheme}://{request.url.netloc}":
            raise HTTPException(status_code=403, detail="Request origin is not allowed.")
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        with Session(engine) as db:
            record = db.exec(select(AuthSession).where(AuthSession.token_digest == _digest(token))).first()
            if record and not hmac.compare_digest(record.csrf_digest, _digest(cookie_token)):
                raise HTTPException(status_code=403, detail="CSRF validation failed.")


class RegisterBody(BaseModel):
    email: str = PydanticField(min_length=5, max_length=254)
    username: str = PydanticField(min_length=3, max_length=32, pattern=r"^[a-zA-Z0-9_]+$")
    password: str = PydanticField(min_length=PASSWORD_MIN, max_length=128)


class LoginBody(BaseModel):
    identifier: str = PydanticField(min_length=3, max_length=254)
    password: str = PydanticField(min_length=1, max_length=128)


class TokenBody(BaseModel):
    token: str = PydanticField(min_length=20, max_length=200)


class ResetBody(TokenBody):
    password: str = PydanticField(min_length=PASSWORD_MIN, max_length=128)


class CsrfResponse(BaseModel):
    csrf_token: str


@router.get("/csrf", response_model=CsrfResponse)
def csrf(request: Request, response: Response):
    token = request.cookies.get(CSRF_COOKIE) or secrets.token_urlsafe(32)
    session_token = request.cookies.get(SESSION_COOKIE)
    if session_token:
        with Session(engine) as db:
            record = db.exec(select(AuthSession).where(AuthSession.token_digest == _digest(session_token))).first()
            if record and not hmac.compare_digest(record.csrf_digest, _digest(token)):
                record.csrf_digest = _digest(token)
                db.add(record)
                db.commit()
    _set_csrf(response, token)
    return {"csrf_token": token}


@router.get("/me")
def me(user: AppUser = Depends(get_current_user)):
    return {"id": user.id, "email": user.email, "username": user.username, "email_verified": user.email_verified}


@router.post("/register", status_code=201)
@limiter.limit("8/minute")
def register(body: RegisterBody, request: Request, response: Response, _: None = Depends(require_csrf)):
    if VERIFY_EMAIL and not email_configured():
        raise HTTPException(503, 'Account email delivery is awaiting administrator configuration. Please try again later.')
    email = str(body.email).strip().lower()
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
        raise HTTPException(status_code=400, detail="Enter a valid email address.")
    username = body.username.strip().lower()
    if not USERNAME_RE.fullmatch(username) or len(body.password.encode()) > 128:
        raise HTTPException(status_code=400, detail="Invalid registration details.")
    with Session(engine) as db:
        existing = db.exec(select(AppUser).where((AppUser.email == email) | (AppUser.username == username))).first()
        if existing:
            if PRODUCTION:
                return {"message": "If the account can be registered, verification instructions will be sent to its email."}
            raise HTTPException(status_code=409, detail="Email or username is already in use.")
        user = AppUser(email=email, username=username, password_hash=_password_hash(body.password), email_verified=not VERIFY_EMAIL)
        db.add(user)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            raise HTTPException(409, 'Email or username is unavailable.')
        db.refresh(user)
    if VERIFY_EMAIL:
        _send_account_link(user, "verify")
        return {"message": "Check your email to verify your account."}
    csrf_token = secrets.token_urlsafe(32)
    _new_session(user, response, csrf_token)
    return {"id": user.id, "email": user.email, "username": user.username}


@router.post("/login")
@limiter.limit("8/minute")
def login(body: LoginBody, request: Request, response: Response, _: None = Depends(require_csrf)):
    ident = body.identifier.strip().lower()
    with Session(engine) as db:
        user = db.exec(select(AppUser).where((AppUser.email == ident) | (AppUser.username == ident))).first()
        valid = bool(user and user.is_active and _password_matches(body.password, user.password_hash))
        if not valid:
            # A fixed dummy scrypt hash keeps unknown account attempts comparable.
            _password_matches(body.password, _DUMMY_HASH)
            raise HTTPException(status_code=401, detail="Invalid email/username or password.")
        if VERIFY_EMAIL and not user.email_verified:
            raise HTTPException(status_code=403, detail="Verify your email before signing in.")
        user_id = user.id
        payload = {"id": user.id, "email": user.email, "username": user.username}
    csrf_token = secrets.token_urlsafe(32)
    with Session(engine) as db:
        user = db.get(AppUser, user_id)
    _new_session(user, response, csrf_token)
    return payload


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response, _: None = Depends(require_csrf), user: AppUser = Depends(get_current_user)):
    token = request.cookies.get(SESSION_COOKIE)
    with Session(engine) as db:
        if token:
            db.exec(delete(AuthSession).where(AuthSession.token_digest == _digest(token), AuthSession.user_id == user.id))
            db.commit()
    response.delete_cookie(SESSION_COOKIE, path="/", secure=PRODUCTION, httponly=True, samesite="lax")
    response.delete_cookie(CSRF_COOKIE, path="/", secure=PRODUCTION, samesite="lax")


def _consume_token(token: str, purpose: str):
    from app.core.db import AuthToken
    with Session(engine) as db:
        user_id = db.exec(delete(AuthToken).where(AuthToken.token_digest == _digest(token), AuthToken.purpose == purpose, AuthToken.expires_at > _now()).returning(AuthToken.user_id)).scalar_one_or_none()
        if user_id is None:
            raise HTTPException(status_code=400, detail="This link is invalid or expired.")
        user = db.get(AppUser, user_id)
        if not user or not user.is_active:
            raise HTTPException(400, 'This account is unavailable.')
        db.commit()
        return user


@router.post("/verify-email")
@limiter.limit("8/minute")
def verify_email(body: TokenBody, request: Request, response: Response, _: None = Depends(require_csrf)):
    user = _consume_token(body.token, "verify")
    user.email_verified = True
    with Session(engine) as db:
        db.add(user)
        db.commit()
        db.refresh(user)
    csrf_token = secrets.token_urlsafe(32)
    _new_session(user, response, csrf_token)
    return {"id": user.id, "email": user.email, "username": user.username}


class EmailBody(BaseModel):
    email: str = PydanticField(min_length=5, max_length=254)


@router.post("/resend-verification", status_code=202)
@limiter.limit("5/minute")
def resend_verification(body: EmailBody, request: Request, _: None = Depends(require_csrf)):
    email = body.email.strip().lower()
    with Session(engine) as db:
        user = db.exec(select(AppUser).where(AppUser.email == email, AppUser.is_active.is_(True))).first()
    if user and not user.email_verified:
        try:
            _send_account_link(user, "verify")
        except Exception:
            pass
    return {"message": "If verification is needed, a new link has been sent."}


@router.post("/forgot-password", status_code=202)
@limiter.limit("5/minute")
def forgot_password(body: EmailBody, request: Request, _: None = Depends(require_csrf)):
    email = body.email.strip().lower()
    with Session(engine) as db:
        user = db.exec(select(AppUser).where(AppUser.email == email, AppUser.is_active.is_(True))).first()
    if user:
        try:
            _send_account_link(user, "reset")
        except Exception:
            # Avoid turning SMTP availability into an account enumeration oracle.
            pass
    return {"message": "If that account exists, a password reset link has been sent."}


@router.post("/reset-password")
@limiter.limit("5/minute")
def reset_password(body: ResetBody, request: Request, _: None = Depends(require_csrf)):
    if len(body.password.encode()) > 128:
        raise HTTPException(status_code=400, detail="Password must be at most 128 bytes.")
    user = _consume_token(body.token, "reset")
    user.password_hash = _password_hash(body.password)
    with Session(engine) as db:
        db.add(user)
        db.exec(delete(AuthSession).where(AuthSession.user_id == user.id))
        db.commit()
    return {"message": "Password updated. Please sign in."}


def _send_account_link(user: AppUser, purpose: str):
    if not email_configured():
        raise HTTPException(status_code=503, detail="Email delivery is not configured.")
    from app.core.db import AuthToken
    token = secrets.token_urlsafe(40)
    expires = _now() + timedelta(hours=1)
    with Session(engine) as db:
        db.exec(delete(AuthToken).where(AuthToken.user_id == user.id, AuthToken.purpose == purpose))
        db.add(AuthToken(user_id=user.id, purpose=purpose, token_digest=_digest(token), expires_at=expires))
        db.commit()
    base = os.getenv("FRONTEND_URL", "http://localhost:3000").rstrip("/")
    link = f"{base}/?{purpose}_token={token}"
    subject = "Verify your TrueWealth AI account" if purpose == "verify" else "Reset your TrueWealth AI password"
    try:
        send_email(user.email, subject, f"Use this one-time link within one hour:\n\n{link}\n")
    except RuntimeError:
        raise HTTPException(503, 'Email delivery failed. Please try resending the verification link later.') from None


_DUMMY_HASH = _password_hash("truewealth-dummy-password")
