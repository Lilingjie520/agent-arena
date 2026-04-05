from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.security import (
    create_pow_challenge,
    extract_client_ip,
    issue_api_key_for_solution,
    revoke_api_key,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


class ChallengeOut(BaseModel):
    challenge_id: str
    nonce: str
    difficulty: int
    expires_at: str


class IssueKeyIn(BaseModel):
    challenge_id: str = Field(min_length=8, max_length=128)
    solution: str = Field(min_length=1, max_length=64)


class IssueKeyOut(BaseModel):
    api_key: str
    expires_at: str
    key_prefix: str


class RevokeKeyIn(BaseModel):
    key_prefix: str | None = Field(default=None, min_length=4, max_length=16)
    api_key: str | None = Field(default=None, min_length=8, max_length=128)


class RevokeKeyOut(BaseModel):
    revoked: bool
    key_prefix: str
    revoked_at: str


class AdminStatusOut(BaseModel):
    ok: bool


def require_admin_token(
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
) -> None:
    if not settings.admin_api_token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Admin revoke endpoint is not configured",
        )
    if x_admin_token != settings.admin_api_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid admin token",
        )


@router.post("/challenge", response_model=ChallengeOut)
def create_challenge(
    request: Request,
    db: Session = Depends(get_db),
) -> ChallengeOut:
    challenge = create_pow_challenge(db, extract_client_ip(request))
    return ChallengeOut(
        challenge_id=challenge.challenge_id,
        nonce=challenge.nonce,
        difficulty=challenge.difficulty,
        expires_at=challenge.expires_at.isoformat(),
    )


@router.post("/issue-key", response_model=IssueKeyOut)
def issue_key(
    payload: IssueKeyIn,
    request: Request,
    db: Session = Depends(get_db),
) -> IssueKeyOut:
    api_key, api_key_value = issue_api_key_for_solution(
        db,
        requester_ip=extract_client_ip(request),
        challenge_id=payload.challenge_id,
        solution=payload.solution,
    )
    return IssueKeyOut(
        api_key=api_key_value,
        expires_at=api_key.expires_at.isoformat(),
        key_prefix=api_key.key_prefix,
    )


@router.post("/revoke-key", response_model=RevokeKeyOut)
def revoke_key(
    payload: RevokeKeyIn,
    _: None = Depends(require_admin_token),
    db: Session = Depends(get_db),
) -> RevokeKeyOut:
    api_key = revoke_api_key(
        db,
        key_prefix=payload.key_prefix,
        api_key_value=payload.api_key,
    )
    return RevokeKeyOut(
        revoked=True,
        key_prefix=api_key.key_prefix,
        revoked_at=api_key.revoked_at.isoformat() if api_key.revoked_at else "",
    )


@router.get("/admin-status", response_model=AdminStatusOut)
def admin_status(_: None = Depends(require_admin_token)) -> AdminStatusOut:
    return AdminStatusOut(ok=True)
