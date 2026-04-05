from __future__ import annotations

import os
import re
from dataclasses import dataclass
from html import unescape
from typing import Iterable
from urllib.error import URLError
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET

from app.topic_generation.schemas import SectorName, SourceEntry


USER_AGENT = "AgentArenaTopicScout/0.2 (+https://github.com/Lilingjie520/agent-arena)"
ATOM_NS = {"atom": "http://www.w3.org/2005/Atom"}
TAG_RE = re.compile(r"<[^>]+>")
WHITESPACE_RE = re.compile(r"\s+")


@dataclass(frozen=True, slots=True)
class FeedSource:
    name: str
    url: str
    sector_hints: tuple[SectorName, ...]


# DEFAULT_FEED_SOURCES v2
# Goal:
# - use sources that are relatively stable for code integration
# - prefer official or institution-grade feeds
# - balance product/news, regulation, labor/economic signals
# - produce enough disagreement-rich context for Scout -> Framing -> Critic
DEFAULT_FEED_SOURCES: tuple[FeedSource, ...] = (
    # Product / capability shifts
    FeedSource(
        name="OpenAI News",
        url="https://openai.com/news/rss.xml",
        sector_hints=("科技",),
    ),
    # Regulation / institutional boundary shifts
    FeedSource(
        name="SEC Press Releases",
        url="https://www.sec.gov/news/pressreleases.rss",
        sector_hints=("金融", "社会"),
    ),
    FeedSource(
        name="SEC Speeches and Statements",
        url="https://www.sec.gov/news/speeches-statements.rss",
        sector_hints=("金融", "科技", "社会"),
    ),
    # Labor / macro / broad economic signals
    FeedSource(
        name="BLS Latest Numbers",
        url="https://www.bls.gov/feed/bls_latest.rss",
        sector_hints=("金融", "社会"),
    ),
    FeedSource(
        name="BLS Employment Situation",
        url="https://www.bls.gov/feed/empsit.rss",
        sector_hints=("金融", "社会"),
    ),
    FeedSource(
        name="BLS JOLTS",
        url="https://www.bls.gov/feed/jolts.rss",
        sector_hints=("金融", "社会"),
    ),
    # Structural and policy-friendly public data anchors
    FeedSource(
        name="US Census Economic Indicators",
        url="https://www.census.gov/economic-indicators/indicator.xml",
        sector_hints=("金融", "社会"),
    ),
    FeedSource(
        name="US Census News Releases",
        url="https://www.census.gov/content/census/en/newsroom/press-releases.xml",
        sector_hints=("社会", "金融"),
    ),
)


def _env_feed_sources() -> tuple[FeedSource, ...]:
    raw = os.getenv("AGENT_ARENA_TOPIC_FEED_URLS", "").strip()
    if not raw:
        return DEFAULT_FEED_SOURCES

    parsed: list[FeedSource] = []
    for chunk in raw.split(","):
        part = chunk.strip()
        if not part:
            continue
        parsed.append(
            FeedSource(
                name=part,
                url=part,
                sector_hints=("科技", "金融", "社会"),
            )
        )
    return tuple(parsed) or DEFAULT_FEED_SOURCES


def _strip_html(value: str) -> str:
    cleaned = TAG_RE.sub(" ", value)
    return WHITESPACE_RE.sub(" ", unescape(cleaned)).strip()


def _text(node: ET.Element | None, default: str = "") -> str:
    if node is None:
        return default
    text = "".join(node.itertext())
    return _strip_html(text) or default


def _pick_first_text(parent: ET.Element, *tags: str) -> str:
    for tag in tags:
        child = parent.find(tag)
        if child is not None:
            value = _text(child)
            if value:
                return value
    return ""


def _parse_rss_items(root: ET.Element, source: FeedSource) -> list[SourceEntry]:
    items: list[SourceEntry] = []
    for item in root.findall("./channel/item"):
        items.append(
            SourceEntry(
                source_name=source.name,
                source_url=_pick_first_text(item, "link") or source.url,
                published_at=_pick_first_text(item, "pubDate"),
                headline=_pick_first_text(item, "title", "headline"),
                summary=_pick_first_text(item, "description", "content"),
                sector_hints=list(source.sector_hints),
            )
        )
    return [item for item in items if item.headline]


def _parse_atom_entries(root: ET.Element, source: FeedSource) -> list[SourceEntry]:
    entries: list[SourceEntry] = []
    for entry in root.findall("atom:entry", ATOM_NS):
        link = entry.find("atom:link[@rel='alternate']", ATOM_NS)
        href = ""
        if link is not None:
            href = link.attrib.get("href", "")
        if not href:
            fallback = entry.find("atom:link", ATOM_NS)
            if fallback is not None:
                href = fallback.attrib.get("href", "")

        summary = _pick_first_text(
            entry,
            "{http://www.w3.org/2005/Atom}summary",
            "{http://www.w3.org/2005/Atom}content",
        )
        entries.append(
            SourceEntry(
                source_name=source.name,
                source_url=href or source.url,
                published_at=_pick_first_text(
                    entry,
                    "{http://www.w3.org/2005/Atom}updated",
                ),
                headline=_pick_first_text(
                    entry,
                    "{http://www.w3.org/2005/Atom}title",
                ),
                summary=summary,
                sector_hints=list(source.sector_hints),
            )
        )
    return [entry for entry in entries if entry.headline]


def fetch_feed_entries(source: FeedSource, timeout_seconds: int = 12) -> list[SourceEntry]:
    request = Request(
        source.url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": (
                "application/rss+xml, application/atom+xml, "
                "application/xml, text/xml;q=0.9, */*;q=0.8"
            ),
        },
    )

    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            payload = response.read()
    except URLError as exc:
        raise RuntimeError(f"Failed to fetch feed: {source.url}") from exc

    root = ET.fromstring(payload)
    if root.tag.endswith("rss"):
        return _parse_rss_items(root, source)
    if root.tag.endswith("feed"):
        return _parse_atom_entries(root, source)
    return []


def collect_recent_entries(
    max_items_per_source: int = 4,
    sources: Iterable[FeedSource] | None = None,
) -> list[SourceEntry]:
    selected_sources = tuple(sources or _env_feed_sources())
    collected: list[SourceEntry] = []

    for source in selected_sources:
        try:
            items = fetch_feed_entries(source)
        except RuntimeError:
            continue
        collected.extend(items[:max_items_per_source])

    return collected


def build_source_brief(entries: list[SourceEntry]) -> str:
    if not entries:
        return "No recent feed entries were collected."

    lines: list[str] = []
    for index, entry in enumerate(entries, start=1):
        sector_hint = "/".join(entry.sector_hints) if entry.sector_hints else "uncategorized"
        lines.append(
            f"{index}. [{entry.source_name}] {entry.headline}\n"
            f"   url: {entry.source_url}\n"
            f"   published_at: {entry.published_at or 'unknown'}\n"
            f"   sector_hints: {sector_hint}\n"
            f"   summary: {entry.summary or 'No summary available.'}"
        )
    return "\n\n".join(lines)
