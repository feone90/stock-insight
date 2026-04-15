"""JWT 인증 시스템."""

import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from pydantic import BaseModel

from app.config import settings

router = APIRouter(prefix="/api/auth", tags=["auth"])

security = HTTPBearer(auto_error=False)

ALGORITHM = "HS256"


class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    email: str


class UserInfo(BaseModel):
    email: str
    role: str


# --- 사용자 저장소 (.env 기반, 추후 DB 전환) ---

def _verify_user(email: str, password: str) -> dict | None:
    """이메일/비밀번호를 검증하고 사용자 정보를 반환한다."""
    if not settings.admin_email or not settings.admin_password:
        return None
    email_match = secrets.compare_digest(email, settings.admin_email)
    pass_match = secrets.compare_digest(password, settings.admin_password)
    if email_match and pass_match:
        return {"email": email, "role": "admin"}
    return None


# --- JWT 토큰 ---

def create_token(email: str, role: str) -> str:
    """JWT 토큰을 생성한다."""
    expire = datetime.now(timezone.utc) + timedelta(hours=settings.jwt_expire_hours)
    payload = {"sub": email, "role": role, "exp": expire}
    return jwt.encode(payload, settings.jwt_secret, algorithm=ALGORITHM)


def decode_token(token: str) -> dict:
    """JWT 토큰을 디코딩한다."""
    return jwt.decode(token, settings.jwt_secret, algorithms=[ALGORITHM])


# --- 의존성 ---

async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> UserInfo:
    """현재 인증된 사용자를 반환한다. 미인증 시 401. DEV_MODE 시 바이패스."""
    if settings.dev_mode:
        return UserInfo(email=settings.admin_email or "dev@local", role="admin")
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="인증이 필요합니다",
        )
    try:
        payload = decode_token(credentials.credentials)
        email = payload.get("sub")
        role = payload.get("role", "user")
        if not email:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="잘못된 토큰")
        return UserInfo(email=email, role=role)
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="토큰 만료 또는 무효")


async def require_admin(user: UserInfo = Depends(get_current_user)) -> UserInfo:
    """admin 역할을 요구한다. 아니면 403."""
    if user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="관리자 권한이 필요합니다",
        )
    return user


# --- 엔드포인트 ---

@router.post("/login", response_model=TokenResponse)
async def login(req: LoginRequest):
    user = _verify_user(req.email, req.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="이메일 또는 비밀번호가 올바르지 않습니다",
        )
    token = create_token(user["email"], user["role"])
    return TokenResponse(
        access_token=token,
        role=user["role"],
        email=user["email"],
    )


@router.get("/me", response_model=UserInfo)
async def me(user: UserInfo = Depends(get_current_user)):
    return user
