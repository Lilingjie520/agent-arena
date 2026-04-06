from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import date
from typing import Any, Iterable

from sqlalchemy.orm import Session

from app.models import Sector, Topic
from app.topic_generation.llm import TopicGenerationLLM
from app.topic_generation.prompts import (
    build_critic_prompt,
    build_editor_prompt,
    build_framing_prompt,
    build_scout_prompt,
)
from app.topic_generation.schemas import (
    CandidateReview,
    DailyTopicBatch,
    FramedTopicCandidate,
    PublishableTopic,
    SourceEntry,
    SourceSignal,
)
from app.topic_generation.sources import build_source_brief


@dataclass(slots=True)
class TopicGenerationResult:
    source_entries: list[SourceEntry]
    signals: list[SourceSignal]
    candidates: list[FramedTopicCandidate]
    reviews: list[CandidateReview]
    published_batch: DailyTopicBatch


class DailyTopicPipeline:
    """Base pipeline for multi-agent daily topic generation."""

    def scout_signals(
        self,
        source_entries: Iterable[SourceEntry],
    ) -> list[SourceSignal]:
        raise NotImplementedError

    def frame_candidates(
        self,
        signals: list[SourceSignal],
    ) -> list[FramedTopicCandidate]:
        raise NotImplementedError

    def critique_candidates(
        self,
        candidates: list[FramedTopicCandidate],
    ) -> list[CandidateReview]:
        raise NotImplementedError

    def edit_batch(
        self,
        approved_candidates: list[FramedTopicCandidate],
        publish_date: date,
    ) -> DailyTopicBatch:
        raise NotImplementedError

    def run(
        self,
        source_entries: Iterable[SourceEntry],
        publish_date: date,
    ) -> TopicGenerationResult:
        normalized_entries = list(source_entries)
        signals = self.scout_signals(normalized_entries)
        candidates = self.frame_candidates(signals)
        reviews = self.critique_candidates(candidates)
        approved_candidates = self._approved_candidates(candidates, reviews)
        batch = self.edit_batch(approved_candidates, publish_date)
        return TopicGenerationResult(
            source_entries=normalized_entries,
            signals=signals,
            candidates=candidates,
            reviews=reviews,
            published_batch=batch,
        )

    @staticmethod
    def _approved_candidates(
        candidates: list[FramedTopicCandidate],
        reviews: list[CandidateReview],
    ) -> list[FramedTopicCandidate]:
        review_map = {
            review.candidate_title.strip().lower(): review
            for review in reviews
        }
        approved: list[FramedTopicCandidate] = []

        for index, candidate in enumerate(candidates):
            review = review_map.get(candidate.title.strip().lower())
            if review is None and index < len(reviews):
                review = reviews[index]
            if review is not None and review.passes:
                approved.append(candidate)

        if len(approved) < 3:
            raise ValueError(
                "Critic stage approved fewer than 3 candidates. "
                "The pipeline cannot produce the required daily mix."
            )
        return approved

    @staticmethod
    def write_batch_to_topics(
        db: Session,
        batch: DailyTopicBatch,
        *,
        skip_existing: bool = False,
    ) -> list[Topic]:
        sectors = {sector.name: sector for sector in db.query(Sector).all()}
        created_topics: list[Topic] = []

        for item in batch.as_list():
            sector = sectors.get(item.sector)
            if sector is None:
                raise ValueError(f"Unknown sector: {item.sector}")

            existing = (
                db.query(Topic)
                .filter(Topic.date == item.date, Topic.title == item.title)
                .one_or_none()
            )
            if existing is not None:
                if skip_existing:
                    continue
                raise ValueError(
                    f"Topic already exists for {item.date}: {item.title}"
                )

            topic = Topic(
                sector_id=sector.id,
                title=item.title,
                description=item.description,
                topic_type="debate",
                date=item.date,
            )
            db.add(topic)
            created_topics.append(topic)

        db.commit()
        for topic in created_topics:
            db.refresh(topic)
        return created_topics

    @staticmethod
    def topic_debug_payload(item: PublishableTopic) -> dict[str, Any]:
        return {
            "mix_type": item.mix_type,
            "debate_question": item.debate_question,
            "rationale_private": item.rationale_private,
            "reasoning_focus": item.reasoning_focus,
            "expected_positions": item.expected_positions,
            "source_urls": item.source_urls,
        }


class LLMDrivenTopicPipeline(DailyTopicPipeline):
    """Run the four-stage topic pipeline through a pluggable LLM backend."""

    def __init__(self, llm: TopicGenerationLLM):
        self.llm = llm

    def scout_signals(
        self,
        source_entries: Iterable[SourceEntry],
    ) -> list[SourceSignal]:
        entries = list(source_entries)
        if not entries:
            raise ValueError(
                "Scout stage requires real source entries. "
                "Refusing to generate topics from an empty source set."
            )
        source_brief = build_source_brief(entries)
        payload = self.llm.generate_json(
            system_prompt=(
                "You are the Scout Agent for Agent Arena. "
                "Return strict JSON only."
            ),
            user_prompt=(
                build_scout_prompt(source_brief)
                + "\n\nReturn a JSON object with a `signals` array."
            ),
            schema_name="scout_signals",
        )
        return [_parse_source_signal(item) for item in _require_list(payload, "signals")]

    def frame_candidates(
        self,
        signals: list[SourceSignal],
    ) -> list[FramedTopicCandidate]:
        signal_brief = _pretty_json(signals)
        payload = self.llm.generate_json(
            system_prompt=(
                "You are the Framing Agent for Agent Arena. "
                "Return strict JSON only."
            ),
            user_prompt=(
                build_framing_prompt(signal_brief)
                + "\n\nReturn a JSON object with a `candidates` array."
            ),
            schema_name="framed_candidates",
        )
        return [
            _parse_framed_topic_candidate(item)
            for item in _require_list(payload, "candidates")
        ]

    def critique_candidates(
        self,
        candidates: list[FramedTopicCandidate],
    ) -> list[CandidateReview]:
        candidate_brief = _pretty_json(candidates)
        payload = self.llm.generate_json(
            system_prompt=(
                "You are the Critic Agent for Agent Arena. "
                "Return strict JSON only."
            ),
            user_prompt=(
                build_critic_prompt(candidate_brief)
                + "\n\nReturn a JSON object with a `reviews` array."
            ),
            schema_name="candidate_reviews",
        )
        return [_parse_candidate_review(item) for item in _require_list(payload, "reviews")]

    def edit_batch(
        self,
        approved_candidates: list[FramedTopicCandidate],
        publish_date: date,
    ) -> DailyTopicBatch:
        candidate_brief = _pretty_json(approved_candidates)
        payload = self.llm.generate_json(
            system_prompt=(
                "You are the Editor Agent for Agent Arena. "
                "Return strict JSON only."
            ),
            user_prompt=(
                build_editor_prompt(candidate_brief)
                + "\n\nReturn a JSON object with "
                "`news_driven`, `structural`, and `cross_domain` keys."
            ),
            schema_name="daily_topic_batch",
        )

        return DailyTopicBatch(
            date=publish_date,
            news_driven=_parse_publishable_topic(
                payload["news_driven"],
                publish_date=publish_date,
                mix_type="news_driven",
            ),
            structural=_parse_publishable_topic(
                payload["structural"],
                publish_date=publish_date,
                mix_type="structural",
            ),
            cross_domain=_parse_publishable_topic(
                payload["cross_domain"],
                publish_date=publish_date,
                mix_type="cross_domain",
            ),
        )


def _require_list(payload: dict[str, Any], key: str) -> list[dict[str, Any]]:
    value = payload.get(key)
    if not isinstance(value, list):
        raise ValueError(f"Expected `{key}` to be a list.")
    return [item for item in value if isinstance(item, dict)]


def _pretty_json(value: Any) -> str:
    if hasattr(value, "__dataclass_fields__"):
        payload = asdict(value)
    elif isinstance(value, list):
        payload = [
            asdict(item) if hasattr(item, "__dataclass_fields__") else item
            for item in value
        ]
    else:
        payload = value
    return json.dumps(
        payload,
        ensure_ascii=False,
        indent=2,
        default=_json_default,
    )


def _json_default(value: Any) -> str:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def _parse_source_signal(payload: dict[str, Any]) -> SourceSignal:
    return SourceSignal(
        source_name=_pick_value(payload, "source_name", "source", "outlet"),
        source_url=_pick_value(payload, "source_url", "url", "link"),
        published_at=_pick_optional_value(
            payload,
            "published_at",
            "date",
            "published",
            "published_date",
        ),
        headline=_pick_value(payload, "headline", "title"),
        summary=_pick_optional_value(payload, "summary", "description"),
        why_it_matters=_pick_value(payload, "why_it_matters", "importance", "why"),
        conflict_points=_string_list(
            payload.get("conflict_points") or payload.get("conflicts")
        ),
        affected_sectors=_string_list(
            payload.get("affected_sectors") or payload.get("sectors")
        ),
    )


def _parse_framed_topic_candidate(payload: dict[str, Any]) -> FramedTopicCandidate:
    raw_sources = payload.get("linked_sources") or []
    linked_sources = [
        _parse_source_signal(item)
        for item in raw_sources
        if isinstance(item, dict)
    ]
    return FramedTopicCandidate(
        mix_type=_pick_value(payload, "mix_type", "mix", "topic_type"),
        sector=_normalize_sector(_pick_value(payload, "sector", "category")),
        title=_pick_value(payload, "title", "headline"),
        description=_pick_value(payload, "description", "summary"),
        question=_pick_value(payload, "question", "debate_question"),
        recent_change_anchor=_pick_value(
            payload,
            "recent_change_anchor",
            "anchor",
            "news_anchor",
        ),
        conflict_axis=_pick_value(payload, "conflict_axis", "conflict", "axis"),
        support_case=_pick_value(payload, "support_case", "pro_case", "support"),
        oppose_case=_pick_value(payload, "oppose_case", "con_case", "oppose"),
        expected_reasoning_signals=_string_list(
            payload.get("expected_reasoning_signals")
            or payload.get("reasoning_signals")
        ),
        linked_sources=linked_sources,
    )


def _parse_candidate_review(payload: dict[str, Any]) -> CandidateReview:
    return CandidateReview(
        candidate_title=str(
            payload.get("candidate_title") or payload.get("title") or ""
        ).strip(),
        passes=bool(payload["passes"]),
        overall_score=float(payload["overall_score"]),
        realism_score=float(payload["realism_score"]),
        debate_quality_score=float(payload["debate_quality_score"]),
        novelty_score=float(payload["novelty_score"]),
        reasoning_depth_score=float(payload["reasoning_depth_score"]),
        issues=_string_list(payload.get("issues")),
        revision_notes=_string_list(payload.get("revision_notes")),
    )


def _parse_publishable_topic(
    payload: dict[str, Any],
    *,
    publish_date: date,
    mix_type: str,
) -> PublishableTopic:
    return PublishableTopic(
        date=publish_date,
        sector=_normalize_sector(_pick_value(payload, "sector", "category")),
        mix_type=mix_type,
        title=_pick_value(payload, "title", "headline"),
        description=_pick_value(payload, "description", "summary"),
        debate_question=_pick_value(payload, "debate_question", "question"),
        rationale_private=_pick_value(
            payload,
            "rationale_private",
            "rationale",
            "editor_notes",
        ),
        reasoning_focus=_string_list(
            payload.get("reasoning_focus") or payload.get("reasoning_axes")
        ),
        expected_positions=_string_list(
            payload.get("expected_positions") or payload.get("positions")
        ),
        source_urls=_string_list(payload.get("source_urls") or payload.get("sources")),
    )


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _pick_value(payload: dict[str, Any], *keys: str) -> str:
    value = _pick_optional_value(payload, *keys)
    if value:
        return value
    raise ValueError(f"Missing required field. Expected one of: {', '.join(keys)}")


def _pick_optional_value(payload: dict[str, Any], *keys: str) -> str:
    for key in keys:
        raw = payload.get(key)
        if raw is None:
            continue
        value = str(raw).strip()
        if value:
            return value
    return ""


def _normalize_sector(value: str) -> str:
    mapping = {
        "科技": "科技",
        "technology": "科技",
        "tech": "科技",
        "金融": "金融",
        "finance": "金融",
        "financial": "金融",
        "社会": "社会",
        "society": "社会",
        "social": "社会",
        "education": "社会",
        "教育": "社会",
        "industry": "科技",
        "industrial": "科技",
        "制造": "科技",
        "manufacturing": "科技",
    }
    normalized = mapping.get(value.strip().lower(), value.strip())
    return normalized
