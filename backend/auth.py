"""Cookie-backed account sessions and request identity for QueryLens."""
from __future__ import annotations

from contextvars import ContextVar
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import secrets
import sqlite3
import uuid

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field
import re

from chat.database import get_db_connection
from chat.models import utc_now_iso

SESSION_COOKIE = "querylens_session"
GUEST_COOKIE = "querylens_guest"
SESSION_DAYS = 30
_PASSWORD_ROUNDS = 310_000
_request_user: ContextVar[dict | None] = ContextVar("querylens_user", default=None)
_guest_id: ContextVar[str | None] = ContextVar("querylens_guest_id", default=None)


def current_user():
    return _request_user.get()


def current_guest_id():
    return _guest_id.get()


def is_persistent_session():
    return current_user() is not None


def _hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _PASSWORD_ROUNDS)
    return f"pbkdf2_sha256${_PASSWORD_ROUNDS}${salt.hex()}${digest.hex()}"


def _verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, rounds, salt, expected = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        actual = _hash_password(password, bytes.fromhex(salt)).split("$", 3)[3]
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def public_user(user):
    return {"id": user["id"], "email": user["email"], "display_name": user["display_name"]}


def _issue_session(user_id: str):
    raw_token = secrets.token_urlsafe(40)
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    now = datetime.now(timezone.utc)
    expires = (now + timedelta(days=SESSION_DAYS)).isoformat()
    with get_db_connection() as conn:
        conn.execute("DELETE FROM auth_sessions WHERE expires_at <= ?", (now.isoformat(),))
        conn.execute("INSERT INTO auth_sessions(token_hash,user_id,expires_at,created_at) VALUES(?,?,?,?)", (token_hash, user_id, expires, now.isoformat()))
    return raw_token


def _user_for_token(token: str | None):
    if not token:
        return None
    digest = hashlib.sha256(token.encode()).hexdigest()
    now = datetime.now(timezone.utc).isoformat()
    with get_db_connection() as conn:
        row = conn.execute("""SELECT u.id,u.email,u.display_name FROM auth_sessions s
            JOIN auth_users u ON u.id=s.user_id WHERE s.token_hash=? AND s.expires_at>?""", (digest, now)).fetchone()
    return public_user(row) if row else None


class AuthContextMiddleware:
    """Attach authenticated or ephemeral guest identity to each API request."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        request = Request(scope, receive=receive)
        user = _user_for_token(request.cookies.get(SESSION_COOKIE))
        guest = request.cookies.get(GUEST_COOKIE) or uuid.uuid4().hex
        user_token = _request_user.set(user)
        guest_token = _guest_id.set(guest)

        async def send_with_guest_cookie(message):
            if message["type"] == "http.response.start" and not request.cookies.get(GUEST_COOKIE):
                headers = list(message.get("headers", []))
                cookie = f"{GUEST_COOKIE}={guest}; Path=/; HttpOnly; SameSite=Lax"
                headers.append((b"set-cookie", cookie.encode("latin-1")))
                message = {**message, "headers": headers}
            await send(message)

        try:
            await self.app(scope, receive, send_with_guest_cookie)
        finally:
            _request_user.reset(user_token)
            _guest_id.reset(guest_token)


class Credentials(BaseModel):
    email: str = Field(min_length=5, max_length=254)
    password: str = Field(min_length=8, max_length=256)
    display_name: str | None = Field(default=None, max_length=80)


class LoginCredentials(BaseModel):
    email: str = Field(min_length=5, max_length=254)
    password: str = Field(min_length=1, max_length=256)


router = APIRouter(prefix="/api/auth", tags=["authentication"])


def _set_auth_cookie(response: Response, token: str, request: Request):
    response.set_cookie(SESSION_COOKIE, token, max_age=SESSION_DAYS * 24 * 60 * 60,
        httponly=True, secure=request.url.scheme == "https", samesite="lax", path="/")


@router.get("/me")
async def auth_me():
    return {"user": current_user()}


@router.post("/signup", status_code=201)
async def signup(payload: Credentials, request: Request, response: Response):
    email = str(payload.email).strip().casefold()
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
        raise HTTPException(status_code=422, detail="Enter a valid email address.")
    display_name = (payload.display_name or email.split("@", 1)[0]).strip()[:80]
    user_id = str(uuid.uuid4())
    try:
        with get_db_connection() as conn:
            conn.execute("INSERT INTO auth_users(id,email,display_name,password_hash,created_at) VALUES(?,?,?,?,?)",
                (user_id, email, display_name, _hash_password(payload.password), utc_now_iso()))
            row = conn.execute("SELECT id,email,display_name FROM auth_users WHERE id=?", (user_id,)).fetchone()
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=409, detail="An account with this email already exists.")
    _set_auth_cookie(response, _issue_session(user_id), request)
    return {"user": public_user(row)}


@router.post("/signin")
async def signin(payload: LoginCredentials, request: Request, response: Response):
    email = str(payload.email).strip().casefold()
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
        raise HTTPException(status_code=401, detail="Email or password is incorrect.")
    with get_db_connection() as conn:
        row = conn.execute("SELECT * FROM auth_users WHERE email=?", (email,)).fetchone()
    if not row or not _verify_password(payload.password, row["password_hash"]):
        raise HTTPException(status_code=401, detail="Email or password is incorrect.")
    _set_auth_cookie(response, _issue_session(row["id"]), request)
    return {"user": public_user(row)}


@router.post("/signout")
async def signout(request: Request, response: Response):
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        digest = hashlib.sha256(token.encode()).hexdigest()
        with get_db_connection() as conn:
            conn.execute("DELETE FROM auth_sessions WHERE token_hash=?", (digest,))
    response.delete_cookie(SESSION_COOKIE, path="/", httponly=True, samesite="lax")
    return {"success": True}
