import os
import secrets
from datetime import datetime, timedelta, timezone

import bcrypt
from fastapi import APIRouter, Cookie, Depends, HTTPException, Response
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token
from pydantic import BaseModel

from database import db_conn

SESSION_COOKIE = "kanji_session"
SESSION_TTL_DAYS = 30
ALLOWED_UI_LANGUAGES = {"en", "ru"}
ALLOWED_STUDY_SCRIPTS = {"ja-kanji", "zh-Hans", "zh-Hant"}

# Set in the environment (not committed) for both local dev and the systemd service —
# see CLAUDE.md "Google SSO" for how to obtain this from Google Cloud Console. It's a
# public identifier, not a secret; the frontend embeds the same value at build time.
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID")

# Reused across requests per Google's guidance — it caches Google's signing-key fetch
# internally instead of hitting the network on every login.
_google_request = google_requests.Request()

router = APIRouter(prefix="/auth", tags=["auth"])


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode(), password_hash.encode())


def create_session(conn, user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    expires_at = (now + timedelta(days=SESSION_TTL_DAYS)).isoformat()
    conn.execute(
        "INSERT INTO sessions (token, user_id, expires_at) VALUES (?, ?, ?)",
        (token, user_id, expires_at),
    )
    conn.execute("DELETE FROM sessions WHERE expires_at < ?", (now.isoformat(),))
    conn.commit()
    return token


def _set_session_cookie(response: Response, token: str):
    response.set_cookie(
        SESSION_COOKIE, token,
        httponly=True, secure=True, samesite="lax",
        max_age=SESSION_TTL_DAYS * 24 * 3600, path="/",
    )


def current_user(kanji_session: str | None = Cookie(default=None), conn=Depends(db_conn)) -> dict | None:
    """Optional-auth dependency: returns the logged-in user's
    {id, username, display_name, ui_language, study_script}, or None."""
    if not kanji_session:
        return None
    row = conn.execute(
        """SELECT u.id, u.username, u.display_name, u.ui_language, u.study_script FROM sessions s
           JOIN users u ON u.id = s.user_id
           WHERE s.token = ? AND s.expires_at > ?""",
        (kanji_session, datetime.now(timezone.utc).isoformat()),
    ).fetchone()
    return dict(row) if row else None


def require_user(user: dict | None = Depends(current_user)) -> dict:
    """Required-auth dependency: 401s if not logged in. Use on all write endpoints."""
    if user is None:
        raise HTTPException(status_code=401, detail="Login required")
    return user


class Credentials(BaseModel):
    username: str
    password: str


class RegisterBody(Credentials):
    # Seeded from the client's current (possibly anonymous, localStorage-only)
    # preferences so registering doesn't silently reset a language/study-script
    # choice the user already made before creating an account.
    ui_language: str = "en"
    study_script: str | None = None


@router.post("/register")
def register(body: RegisterBody, response: Response, conn=Depends(db_conn)):
    username = body.username.strip().lower()
    if not username or len(body.password) < 8:
        raise HTTPException(status_code=400, detail="Username required, password must be at least 8 characters")
    if body.ui_language not in ALLOWED_UI_LANGUAGES:
        raise HTTPException(status_code=400, detail="Invalid ui_language")
    if body.study_script is not None and body.study_script not in ALLOWED_STUDY_SCRIPTS:
        raise HTTPException(status_code=400, detail="Invalid study_script")
    existing = conn.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
    if existing:
        raise HTTPException(status_code=409, detail="Username already taken")
    cur = conn.execute(
        "INSERT INTO users (username, password_hash, auth_provider, ui_language, study_script) "
        "VALUES (?, ?, 'local', ?, ?)",
        (username, hash_password(body.password), body.ui_language, body.study_script),
    )
    conn.commit()
    user_id = cur.lastrowid
    token = create_session(conn, user_id)
    _set_session_cookie(response, token)
    return {"id": user_id, "username": username, "ui_language": body.ui_language, "study_script": body.study_script}


class GoogleLoginBody(BaseModel):
    # The ID token (a signed JWT) returned client-side by Google Identity Services —
    # verified here, never trusted as-is. Same ui_language/study_script carry-over
    # rationale as RegisterBody.
    credential: str
    ui_language: str = "en"
    study_script: str | None = None


def _unique_username(conn, base: str) -> str:
    """First-come username derived from the Google account (email local-part or a
    google<sub> fallback); suffixed with an incrementing number on collision. Doesn't
    coordinate with local (password) accounts beyond the shared UNIQUE constraint —
    a Google sign-in never merges into an existing local account with a matching
    username, it just picks the next free one."""
    username = base
    suffix = 1
    while conn.execute("SELECT 1 FROM users WHERE username = ?", (username,)).fetchone():
        suffix += 1
        username = f"{base}{suffix}"
    return username


@router.post("/google")
def google_login(body: GoogleLoginBody, response: Response, conn=Depends(db_conn)):
    if not GOOGLE_CLIENT_ID:
        raise HTTPException(status_code=500, detail="Google sign-in is not configured on this server")
    if body.ui_language not in ALLOWED_UI_LANGUAGES:
        raise HTTPException(status_code=400, detail="Invalid ui_language")
    if body.study_script is not None and body.study_script not in ALLOWED_STUDY_SCRIPTS:
        raise HTTPException(status_code=400, detail="Invalid study_script")

    try:
        idinfo = google_id_token.verify_oauth2_token(body.credential, _google_request, GOOGLE_CLIENT_ID)
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid Google credential")

    provider_user_id = idinfo["sub"]
    row = conn.execute(
        "SELECT id, username, ui_language, study_script FROM users WHERE auth_provider = 'google' AND provider_user_id = ?",
        (provider_user_id,),
    ).fetchone()

    if row:
        user_id = row["id"]
    else:
        email = idinfo.get("email")
        base_username = (email.split("@")[0] if email else f"google{provider_user_id}").strip().lower() or f"google{provider_user_id}"
        username = _unique_username(conn, base_username)
        cur = conn.execute(
            "INSERT INTO users (username, password_hash, auth_provider, provider_user_id, display_name, ui_language, study_script) "
            "VALUES (?, NULL, 'google', ?, ?, ?, ?)",
            (username, provider_user_id, idinfo.get("name") or username, body.ui_language, body.study_script),
        )
        conn.commit()
        user_id = cur.lastrowid

    token = create_session(conn, user_id)
    _set_session_cookie(response, token)
    row = conn.execute("SELECT id, username, ui_language, study_script FROM users WHERE id = ?", (user_id,)).fetchone()
    return dict(row)


@router.post("/login")
def login(body: Credentials, response: Response, conn=Depends(db_conn)):
    username = body.username.strip().lower()
    row = conn.execute(
        "SELECT id, username, password_hash, ui_language, study_script FROM users WHERE username = ?", (username,)
    ).fetchone()
    # Generic message either way (bad username or bad password or SSO-only account
    # with no password_hash) — avoids leaking which usernames are registered.
    if not row or not row["password_hash"] or not verify_password(body.password, row["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid username or password")
    token = create_session(conn, row["id"])
    _set_session_cookie(response, token)
    return {
        "id": row["id"], "username": row["username"],
        "ui_language": row["ui_language"], "study_script": row["study_script"],
    }


class PreferencesUpdate(BaseModel):
    ui_language: str | None = None
    study_script: str | None = None


@router.patch("/preferences")
def update_preferences(body: PreferencesUpdate, conn=Depends(db_conn), user=Depends(require_user)):
    # exclude_unset (not `is not None`) so {"study_script": null} — explicitly
    # clearing the preference — is distinguishable from the field being omitted.
    updates = body.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    if "ui_language" in updates and updates["ui_language"] not in ALLOWED_UI_LANGUAGES:
        raise HTTPException(status_code=400, detail="Invalid ui_language")
    if updates.get("study_script") is not None and updates["study_script"] not in ALLOWED_STUDY_SCRIPTS:
        raise HTTPException(status_code=400, detail="Invalid study_script")

    set_clause = ", ".join(f"{k} = ?" for k in updates)
    conn.execute(f"UPDATE users SET {set_clause} WHERE id = ?", (*updates.values(), user["id"]))
    conn.commit()
    row = conn.execute(
        "SELECT ui_language, study_script FROM users WHERE id = ?", (user["id"],)
    ).fetchone()
    return dict(row)


@router.post("/logout")
def logout(response: Response, kanji_session: str | None = Cookie(default=None), conn=Depends(db_conn)):
    if kanji_session:
        conn.execute("DELETE FROM sessions WHERE token = ?", (kanji_session,))
        conn.commit()
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"status": "ok"}


@router.get("/me")
def me(user: dict | None = Depends(current_user)):
    if user is None:
        return {"authenticated": False}
    return {"authenticated": True, **user}
