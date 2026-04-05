from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Literal


SectorName = Literal["科技", "金融", "社会"]
TopicMix = Literal["news_driven", "structural", "cross_domain"]
StanceAxis = Literal["support", "oppose", "neutral"]


@dataclass(slots=True)
class SourceEntry:
    source_name: str
    source_url: str
    published_at: str
    headline: str
    summary: str
    sector_hints: list[SectorName] = field(default_factory=list)


@dataclass(slots=True)
class SourceSignal:
    source_name: str
    source_url: str
    published_at: str
    headline: str
    summary: str
    why_it_matters: str
    conflict_points: list[str] = field(default_factory=list)
    affected_sectors: list[SectorName] = field(default_factory=list)


@dataclass(slots=True)
class FramedTopicCandidate:
    mix_type: TopicMix
    sector: SectorName
    title: str
    description: str
    question: str
    recent_change_anchor: str
    conflict_axis: str
    support_case: str
    oppose_case: str
    expected_reasoning_signals: list[str] = field(default_factory=list)
    linked_sources: list[SourceSignal] = field(default_factory=list)


@dataclass(slots=True)
class CandidateReview:
    candidate_title: str
    passes: bool
    overall_score: float
    realism_score: float
    debate_quality_score: float
    novelty_score: float
    reasoning_depth_score: float
    issues: list[str] = field(default_factory=list)
    revision_notes: list[str] = field(default_factory=list)


@dataclass(slots=True)
class PublishableTopic:
    date: date
    sector: SectorName
    mix_type: TopicMix
    title: str
    description: str
    debate_question: str
    rationale_private: str
    reasoning_focus: list[str] = field(default_factory=list)
    expected_positions: list[str] = field(default_factory=list)
    source_urls: list[str] = field(default_factory=list)


@dataclass(slots=True)
class DailyTopicBatch:
    date: date
    news_driven: PublishableTopic
    structural: PublishableTopic
    cross_domain: PublishableTopic

    def as_list(self) -> list[PublishableTopic]:
        return [self.news_driven, self.structural, self.cross_domain]
