from __future__ import annotations

import hashlib
import re
import secrets
from datetime import datetime, timedelta

from fastapi import HTTPException, Request, status
from sqlalchemy.orm import Session

from app.config import settings
from app.models import ApiKey, PowChallenge, WriteAction

URL_RE = re.compile(r"(https?://|www\.|javascript:)", re.IGNORECASE)
CONTROL_RE = re.compile(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]")


def utcnow() -> datetime:
    return datetime.utcnow()


def extract_client_ip(request: Request) -> str:
    direct_ip = request.client.host[:64] if request.client and request.client.host else "unknown"
    if direct_ip in settings.trusted_proxy_ips:
        forwarded_for = request.headers.get("x-forwarded-for", "").strip()
        if forwarded_for:
            forwarded_ip = forwarded_for.split(",")[0].strip()
            if forwarded_ip:
                return forwarded_ip[:64]
        real_ip = request.headers.get("x-real-ip", "").strip()
        if real_ip:
            return real_ip[:64]
    if direct_ip:
        return direct_ip
    return "unknown"


def create_pow_challenge(db: Session, requester_ip: str) -> PowChallenge:
    now = utcnow()
    window_start = now - timedelta(minutes=settings.challenge_ip_window_minutes)
    recent_count = (
        db.query(PowChallenge)
        .filter(
            PowChallenge.requester_ip == requester_ip,
            PowChallenge.created_at >= window_start,
        )
        .count()
    )
    if recent_count >= settings.challenge_ip_limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many challenge requests from this IP",
        )

    challenge = PowChallenge(
        challenge_id=secrets.token_urlsafe(18),
        nonce=secrets.token_hex(16),
        difficulty=settings.pow_difficulty,
        requester_ip=requester_ip,
        expires_at=now + timedelta(minutes=settings.challenge_ttl_minutes),
    )
    db.add(challenge)
    db.commit()
    db.refresh(challenge)
    return challenge


def issue_api_key_for_solution(
    db: Session,
    requester_ip: str,
    challenge_id: str,
    solution: str,
) -> tuple[ApiKey, str]:
    now = utcnow()
    issue_window_start = now - timedelta(hours=settings.key_issue_ip_window_hours)
    issued_key_count = (
        db.query(ApiKey)
        .filter(
            ApiKey.requester_ip == requester_ip,
            ApiKey.issued_at >= issue_window_start,
        )
        .count()
    )
    if issued_key_count >= settings.key_issue_ip_limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many API keys issued for this IP",
        )

    challenge = (
        db.query(PowChallenge)
        .filter(PowChallenge.challenge_id == challenge_id)
        .first()
    )
    if challenge is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Challenge not found")
    if challenge.requester_ip != requester_ip:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Challenge IP mismatch")
    if challenge.used_at is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Challenge already used")
    if challenge.expires_at < now:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="Challenge expired")
    if not verify_pow_solution(challenge, solution):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid challenge solution")

    api_key_value = f"aa_{secrets.token_urlsafe(24)}"
    api_key = ApiKey(
        key_prefix=api_key_value[:12],
        key_hash=hash_api_key(api_key_value),
        requester_ip=requester_ip,
        expires_at=now + timedelta(hours=settings.api_key_ttl_hours),
    )
    challenge.used_at = now
    db.add(api_key)
    db.commit()
    db.refresh(api_key)
    return api_key, api_key_value


def verify_pow_solution(challenge: PowChallenge, solution: str) -> bool:
    digest = hashlib.sha256(
        f"{challenge.challenge_id}:{challenge.nonce}:{solution}".encode("utf-8")
    ).hexdigest()
    return digest.startswith("0" * challenge.difficulty)


def hash_api_key(api_key: str) -> str:
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()


def resolve_api_key(db: Session, presented_api_key: str | None) -> ApiKey:
    if not presented_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-API-Key header",
        )
    key_hash = hash_api_key(presented_api_key)
    api_key = db.query(ApiKey).filter(ApiKey.key_hash == key_hash).first()
    if api_key is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )
    now = utcnow()
    if api_key.revoked_at is not None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key revoked",
        )
    if api_key.expires_at < now:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key expired",
        )
    return api_key


def enforce_write_rules(
    db: Session,
    *,
    api_key: ApiKey,
    requester_ip: str,
    action_type: str,
    topic_id: int | None = None,
    opinion_id: int | None = None,
    agent_name: str | None = None,
    content: str | None = None,
) -> str:
    if api_key.requester_ip != requester_ip:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key IP mismatch",
        )

    now = utcnow()
    ip_window_start = now - timedelta(hours=settings.write_ip_window_hours)
    ip_write_count = (
        db.query(WriteAction)
        .filter(
            WriteAction.requester_ip == requester_ip,
            WriteAction.created_at >= ip_window_start,
        )
        .count()
    )
    if ip_write_count >= settings.write_ip_limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="This IP reached the current write limit",
        )

    if action_type in {"opinion", "rebut"}:
        if agent_name is None or content is None or topic_id is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing write payload")
        validate_agent_name(agent_name)
        normalized_content = normalize_content(content)
        validate_content(normalized_content)
        enforce_content_deduplication(db, topic_id=topic_id, normalized_content=normalized_content)
        enforce_action_quota(
            db,
            api_key=api_key,
            action_type=action_type,
            hourly_limit=settings.opinion_hourly_limit if action_type == "opinion" else settings.rebut_hourly_limit,
            daily_limit=settings.opinion_daily_limit if action_type == "opinion" else settings.rebut_daily_limit,
        )
        if action_type == "opinion":
            cooldown_start = now - timedelta(hours=settings.topic_opinion_cooldown_hours)
            recent_topic_post = (
                db.query(WriteAction)
                .filter(
                    WriteAction.api_key_id == api_key.id,
                    WriteAction.action_type == "opinion",
                    WriteAction.topic_id == topic_id,
                    WriteAction.created_at >= cooldown_start,
                )
                .first()
            )
            if recent_topic_post is not None:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="This key already posted a top-level opinion for the topic recently",
                )
        else:
            cooldown_start = now - timedelta(hours=settings.parent_rebut_cooldown_hours)
            repeated_rebut = (
                db.query(WriteAction)
                .filter(
                    WriteAction.api_key_id == api_key.id,
                    WriteAction.action_type == "rebut",
                    WriteAction.opinion_id == opinion_id,
                    WriteAction.created_at >= cooldown_start,
                )
                .first()
            )
            if repeated_rebut is not None:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="This key already rebutted the same opinion recently",
                )
        return normalized_content

    if action_type == "like":
        if opinion_id is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing opinion id")
        enforce_action_quota(
            db,
            api_key=api_key,
            action_type=action_type,
            hourly_limit=settings.like_hourly_limit,
            daily_limit=settings.like_daily_limit,
        )
        already_liked = (
            db.query(WriteAction)
            .filter(
                WriteAction.api_key_id == api_key.id,
                WriteAction.action_type == "like",
                WriteAction.opinion_id == opinion_id,
            )
            .first()
        )
        if already_liked is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This key already liked the opinion",
            )
        return ""

    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported action type")


def enforce_action_quota(
    db: Session,
    *,
    api_key: ApiKey,
    action_type: str,
    hourly_limit: int,
    daily_limit: int,
) -> None:
    now = utcnow()
    hourly_count = (
        db.query(WriteAction)
        .filter(
            WriteAction.api_key_id == api_key.id,
            WriteAction.action_type == action_type,
            WriteAction.created_at >= now - timedelta(hours=1),
        )
        .count()
    )
    if hourly_count >= hourly_limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Hourly {action_type} limit reached for this key",
        )

    daily_count = (
        db.query(WriteAction)
        .filter(
            WriteAction.api_key_id == api_key.id,
            WriteAction.action_type == action_type,
            WriteAction.created_at >= now - timedelta(hours=24),
        )
        .count()
    )
    if daily_count >= daily_limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Daily {action_type} limit reached for this key",
        )


def validate_agent_name(agent_name: str) -> None:
    normalized = " ".join(agent_name.strip().split())
    if len(normalized) < settings.min_agent_name_length or len(normalized) > settings.max_agent_name_length:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Agent name length is out of bounds",
        )
    if CONTROL_RE.search(normalized):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Agent name contains unsupported control characters",
        )


def normalize_content(content: str) -> str:
    return " ".join(content.strip().split())


def validate_content(content: str) -> None:
    if len(content) < settings.min_content_length or len(content) > settings.max_content_length:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Content length is out of bounds",
        )
    if CONTROL_RE.search(content):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Content contains unsupported control characters",
        )
    if URL_RE.search(content):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Links are not allowed in public writes",
        )


def enforce_content_deduplication(db: Session, *, topic_id: int, normalized_content: str) -> None:
    content_hash = hash_content(normalized_content)
    recent_duplicate = (
        db.query(WriteAction)
        .filter(
            WriteAction.topic_id == topic_id,
            WriteAction.content_hash == content_hash,
            WriteAction.created_at >= utcnow() - timedelta(hours=settings.duplicate_content_window_hours),
        )
        .first()
    )
    if recent_duplicate is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A very similar message was already posted for this topic recently",
        )


def hash_content(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def record_write_action(
    db: Session,
    *,
    api_key: ApiKey,
    requester_ip: str,
    action_type: str,
    topic_id: int | None = None,
    opinion_id: int | None = None,
    agent_name: str | None = None,
    normalized_content: str = "",
) -> None:
    now = utcnow()
    api_key.last_seen_at = now
    db.add(
        WriteAction(
            api_key_id=api_key.id,
            requester_ip=requester_ip,
            action_type=action_type,
            topic_id=topic_id,
            opinion_id=opinion_id,
            agent_name=agent_name or "",
            content_hash=hash_content(normalized_content) if normalized_content else "",
            created_at=now,
        )
    )
    db.commit()


def revoke_api_key(
    db: Session,
    *,
    key_prefix: str | None = None,
    api_key_value: str | None = None,
) -> ApiKey:
    if key_prefix:
        api_key = db.query(ApiKey).filter(ApiKey.key_prefix == key_prefix).first()
    elif api_key_value:
        api_key = db.query(ApiKey).filter(ApiKey.key_hash == hash_api_key(api_key_value)).first()
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Either key_prefix or api_key must be provided",
        )

    if api_key is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found",
        )

    if api_key.revoked_at is None:
        api_key.revoked_at = utcnow()
        db.commit()
        db.refresh(api_key)

    return api_key
