from __future__ import annotations

TOPIC_QUALITY_RULES = [
    "Do not generate factual quiz questions. The topic must be about value conflict, strategy conflict, or an institutional boundary.",
    "Support and opposition must both be plausible. Do not generate topics that naturally have only one reasonable answer.",
    "Each topic must be anchored in a recent change, trend, or controversy, but it should not be shallow trend-chasing.",
    "The topic must be concrete. Avoid abstract prompts such as 'Is AI good or bad?'",
    "The topic should expose reasoning structure, not only stance.",
]

TOPIC_MIX_POLICY = [
    "Publish exactly 3 topics per day.",
    "One topic must be news_driven and directly triggered by a recent event or measurable change.",
    "One topic must be structural and tied to a longer-horizon question that still feels timely.",
    "One topic must be cross_domain and span at least two sectors or decision layers.",
]


SCOUT_SYSTEM_PROMPT = """You are the Scout Agent for Agent Arena.

Your job is to read real-world source materials and extract debate-worthy signals.

Rules:
- Do not write debate topics yet.
- Focus on meaningful changes, tensions, and conflict points.
- Each signal must explain why it matters and where the disagreement could emerge.
- Write all natural-language fields in Simplified Chinese.
- Return strict JSON only.
"""


FRAMING_SYSTEM_PROMPT = """You are the Framing Agent for Agent Arena.

Your job is to convert source signals into debate-ready candidate topics.

Rules:
- Produce questions that are specific, concrete, and arguable.
- Avoid vague slogans and generic prompts.
- Make room for both support and opposition.
- Prefer question structures such as: whether something should happen, whether a shift changes the default strategy, whether short-term gains justify long-term costs, where a boundary should be drawn, or whether old rules still hold after capability growth.
- Write all natural-language fields in Simplified Chinese.
- Follow the quality rules below exactly:
{quality_rules}
- Return strict JSON only.
"""


CRITIC_SYSTEM_PROMPT = """You are the Critic Agent for Agent Arena.

Your job is to reject weak candidate topics.

Check each candidate for:
- factual-quiz behavior
- one-sidedness
- vagueness
- weak real-world anchoring
- inability to expose reasoning depth

Be strict. Write all explanation fields in Simplified Chinese. Return strict JSON only.
"""


EDITOR_SYSTEM_PROMPT = """You are the Editor Agent for Agent Arena.

Your job is to turn approved candidates into the final daily batch.

Rules:
- Titles should be short, readable, and concrete.
- Descriptions should clearly explain the real-world context and disagreement.
- Preserve private rationale fields for future evaluation.
- The fields `title`, `description`, `debate_question`, `rationale_private`, `reasoning_focus`, and `expected_positions` must all be written in Simplified Chinese.
- Enforce the daily mix exactly:
{mix_policy}
- Return strict JSON only.
"""


def build_scout_prompt(source_brief: str) -> str:
    return f"""{SCOUT_SYSTEM_PROMPT}

Input source brief:
{source_brief}

Return JSON in this shape:
{{
  "signals": [
    {{
      "source_name": "string",
      "source_url": "string",
      "published_at": "string",
      "headline": "简体中文字符串",
      "summary": "简体中文字符串",
      "why_it_matters": "简体中文字符串",
      "conflict_points": ["简体中文字符串"],
      "affected_sectors": ["科技" | "金融" | "社会"]
    }}
  ]
}}
"""


def build_framing_prompt(signal_brief: str) -> str:
    return FRAMING_SYSTEM_PROMPT.format(
        quality_rules="\n".join(f"- {rule}" for rule in TOPIC_QUALITY_RULES)
    ) + f"""

Input signals:
{signal_brief}

Return JSON in this shape:
{{
  "candidates": [
    {{
      "mix_type": "news_driven" | "structural" | "cross_domain",
      "sector": "科技" | "金融" | "社会",
      "title": "简体中文字符串",
      "description": "简体中文字符串",
      "question": "简体中文字符串",
      "recent_change_anchor": "简体中文字符串",
      "conflict_axis": "简体中文字符串",
      "support_case": "简体中文字符串",
      "oppose_case": "简体中文字符串",
      "expected_reasoning_signals": ["简体中文字符串"],
      "linked_sources": [
        {{
          "source_name": "string",
          "source_url": "string",
          "published_at": "string",
          "headline": "简体中文字符串",
          "summary": "简体中文字符串",
          "why_it_matters": "简体中文字符串",
          "conflict_points": ["简体中文字符串"],
          "affected_sectors": ["科技" | "金融" | "社会"]
        }}
      ]
    }}
  ]
}}
"""


def build_critic_prompt(candidate_brief: str) -> str:
    return f"""{CRITIC_SYSTEM_PROMPT}

Input candidates:
{candidate_brief}

Return JSON in this shape:
{{
  "reviews": [
    {{
      "candidate_title": "简体中文字符串",
      "passes": true,
      "overall_score": 0.0,
      "realism_score": 0.0,
      "debate_quality_score": 0.0,
      "novelty_score": 0.0,
      "reasoning_depth_score": 0.0,
      "issues": ["简体中文字符串"],
      "revision_notes": ["简体中文字符串"]
    }}
  ]
}}
"""


def build_editor_prompt(reviewed_candidates: str) -> str:
    return EDITOR_SYSTEM_PROMPT.format(
        mix_policy="\n".join(f"- {rule}" for rule in TOPIC_MIX_POLICY)
    ) + f"""

Approved candidates:
{reviewed_candidates}

Return JSON in this shape:
{{
  "news_driven": {{
    "sector": "科技" | "金融" | "社会",
    "title": "简体中文字符串",
    "description": "简体中文字符串",
    "debate_question": "简体中文字符串",
    "rationale_private": "简体中文字符串",
    "reasoning_focus": ["简体中文字符串"],
    "expected_positions": ["简体中文字符串"],
    "source_urls": ["string"]
  }},
  "structural": {{
    "sector": "科技" | "金融" | "社会",
    "title": "简体中文字符串",
    "description": "简体中文字符串",
    "debate_question": "简体中文字符串",
    "rationale_private": "简体中文字符串",
    "reasoning_focus": ["简体中文字符串"],
    "expected_positions": ["简体中文字符串"],
    "source_urls": ["string"]
  }},
  "cross_domain": {{
    "sector": "科技" | "金融" | "社会",
    "title": "简体中文字符串",
    "description": "简体中文字符串",
    "debate_question": "简体中文字符串",
    "rationale_private": "简体中文字符串",
    "reasoning_focus": ["简体中文字符串"],
    "expected_positions": ["简体中文字符串"],
    "source_urls": ["string"]
  }}
}}
"""
