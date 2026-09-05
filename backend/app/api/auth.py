from fastapi import APIRouter, Header, HTTPException, Response, status
from pydantic import BaseModel

from app.i18n.strings import t
from app.services.auth import authenticate_user, create_access_token

router = APIRouter()


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


@router.post("/login", response_model=TokenResponse)
async def login(
    body: LoginRequest,
    response: Response,
    accept_language: str = Header(default="en", alias="Accept-Language"),
):
    language = accept_language.split(",")[0].split("-")[0].strip() or "en"
    user_id = authenticate_user(body.username, body.password)
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=t("invalid_credentials", language),
        )

    token = create_access_token(user_id)

    # Set an httpOnly cookie so browser clients can authenticate without
    # storing the token in localStorage (which may be unreliable in some
    # embedding contexts). The token is also returned in the body for API
    # clients that prefer Authorization: Bearer.
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        samesite="lax",
        max_age=60 * 60 * 24,  # 24 h
    )

    return TokenResponse(access_token=token)
