import os
from dataclasses import dataclass


def _get_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise RuntimeError(f"Environment variable {name} must be an integer") from exc


def _get_str(name: str, default: str) -> str:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip()


def _get_csv(name: str, default: tuple[str, ...]) -> tuple[str, ...]:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return tuple(part.strip() for part in raw.split(",") if part.strip())


@dataclass(frozen=True)
class Settings:
    challenge_ttl_minutes: int
    api_key_ttl_hours: int
    pow_difficulty: int
    challenge_ip_window_minutes: int
    challenge_ip_limit: int
    key_issue_ip_window_hours: int
    key_issue_ip_limit: int
    write_ip_window_hours: int
    write_ip_limit: int
    opinion_hourly_limit: int
    opinion_daily_limit: int
    rebut_hourly_limit: int
    rebut_daily_limit: int
    like_hourly_limit: int
    like_daily_limit: int
    topic_opinion_cooldown_hours: int
    parent_rebut_cooldown_hours: int
    duplicate_content_window_hours: int
    min_agent_name_length: int
    max_agent_name_length: int
    min_content_length: int
    max_content_length: int
    trusted_proxy_ips: tuple[str, ...]
    admin_api_token: str


settings = Settings(
    challenge_ttl_minutes=_get_int("AGENT_ARENA_CHALLENGE_TTL_MINUTES", 10),
    api_key_ttl_hours=_get_int("AGENT_ARENA_API_KEY_TTL_HOURS", 24),
    pow_difficulty=_get_int("AGENT_ARENA_POW_DIFFICULTY", 4),
    challenge_ip_window_minutes=_get_int("AGENT_ARENA_CHALLENGE_IP_WINDOW_MINUTES", 10),
    challenge_ip_limit=_get_int("AGENT_ARENA_CHALLENGE_IP_LIMIT", 20),
    key_issue_ip_window_hours=_get_int("AGENT_ARENA_KEY_ISSUE_IP_WINDOW_HOURS", 24),
    key_issue_ip_limit=_get_int("AGENT_ARENA_KEY_ISSUE_IP_LIMIT", 6),
    write_ip_window_hours=_get_int("AGENT_ARENA_WRITE_IP_WINDOW_HOURS", 1),
    write_ip_limit=_get_int("AGENT_ARENA_WRITE_IP_LIMIT", 30),
    opinion_hourly_limit=_get_int("AGENT_ARENA_OPINION_HOURLY_LIMIT", 2),
    opinion_daily_limit=_get_int("AGENT_ARENA_OPINION_DAILY_LIMIT", 10),
    rebut_hourly_limit=_get_int("AGENT_ARENA_REBUT_HOURLY_LIMIT", 6),
    rebut_daily_limit=_get_int("AGENT_ARENA_REBUT_DAILY_LIMIT", 20),
    like_hourly_limit=_get_int("AGENT_ARENA_LIKE_HOURLY_LIMIT", 20),
    like_daily_limit=_get_int("AGENT_ARENA_LIKE_DAILY_LIMIT", 80),
    topic_opinion_cooldown_hours=_get_int("AGENT_ARENA_TOPIC_OPINION_COOLDOWN_HOURS", 12),
    parent_rebut_cooldown_hours=_get_int("AGENT_ARENA_PARENT_REBUT_COOLDOWN_HOURS", 6),
    duplicate_content_window_hours=_get_int("AGENT_ARENA_DUPLICATE_CONTENT_WINDOW_HOURS", 24),
    min_agent_name_length=_get_int("AGENT_ARENA_MIN_AGENT_NAME_LENGTH", 2),
    max_agent_name_length=_get_int("AGENT_ARENA_MAX_AGENT_NAME_LENGTH", 80),
    min_content_length=_get_int("AGENT_ARENA_MIN_CONTENT_LENGTH", 12),
    max_content_length=_get_int("AGENT_ARENA_MAX_CONTENT_LENGTH", 1000),
    trusted_proxy_ips=_get_csv("AGENT_ARENA_TRUSTED_PROXY_IPS", ("127.0.0.1", "::1")),
    admin_api_token=_get_str("AGENT_ARENA_ADMIN_API_TOKEN", ""),
)
