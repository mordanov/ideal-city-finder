"""
JWT authentication service.

We have exactly two static accounts configured via environment variables.
There is no users table in the database — the user identity ("user1"/"user2")
is derived purely from which env credential pair matches at login time.
This is intentional for this MVP: credentials live only in .env and are never
stored or hashed in the DB. The tradeoff is that changing a password requires
redeploying the service, which is acceptable at this scale.
"""

import secrets
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from app.config import settings

_bearer_scheme = HTTPBearer(auto_error=False)


def authenticate_user(username: str, password: str) -> str | None:
    """Return 'user1' or 'user2' if credentials match, None otherwise.

    Uses secrets.compare_digest for constant-time comparison to prevent
    timing-based username enumeration. Passwords are never logged.
    """
    pairs = [
        ("user1", settings.auth_user_1_username, settings.auth_user_1_password),
        ("user2", settings.auth_user_2_username, settings.auth_user_2_password),
    ]
    for user_id, env_username, env_password in pairs:
        username_match = secrets.compare_digest(username.encode(), env_username.encode())
        password_match = secrets.compare_digest(password.encode(), env_password.encode())
        if username_match and password_match:
            return user_id
    return None


def create_access_token(user_id: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes)
    payload = {"sub": user_id, "exp": expire}
    return jwt.encode(payload, settings.jwt_secret_key, algorithm="HS256")


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> str:
    """FastAPI dependency: extracts and validates the JWT from Authorization: Bearer.

    Raises 401 if the header is missing, token is invalid, or token is expired.
    Returns the user_id ("user1" or "user2") on success.
    """
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    try:
        payload = jwt.decode(credentials.credentials, settings.jwt_secret_key, algorithms=["HS256"])
        user_id: str | None = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
        return user_id
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")
