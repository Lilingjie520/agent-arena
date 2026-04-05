from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from datetime import UTC, date, datetime
from pathlib import Path

from app.topic_generation.prompts import (
    TOPIC_MIX_POLICY,
    TOPIC_QUALITY_RULES,
    build_critic_prompt,
    build_editor_prompt,
    build_framing_prompt,
    build_scout_prompt,
)
from app.topic_generation.sources import build_source_brief, collect_recent_entries


def build_work_packet(publish_date: date, max_items_per_source: int) -> dict:
    entries = collect_recent_entries(max_items_per_source=max_items_per_source)
    source_brief = build_source_brief(entries)

    return {
        "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "publish_date": publish_date.isoformat(),
        "quality_rules": TOPIC_QUALITY_RULES,
        "mix_policy": TOPIC_MIX_POLICY,
        "source_entries": [asdict(entry) for entry in entries],
        "source_brief": source_brief,
        "prompts": {
            "scout": build_scout_prompt(source_brief),
            "framing_template": build_framing_prompt(
                "将 Scout Agent 产出的 signals 粘贴到这里。"
            ),
            "critic_template": build_critic_prompt(
                "将 Framing Agent 产出的候选题粘贴到这里。"
            ),
            "editor_template": build_editor_prompt(
                "将 Critic Agent 通过后的候选题粘贴到这里。"
            ),
        },
        "notes": {
            "intent": "Use real-world changes to generate debate-ready daily topics.",
            "next_stage": "Pass this packet through Scout -> Framing -> Critic -> Editor.",
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build a daily topic generation work packet for Agent Arena."
    )
    parser.add_argument(
        "--date",
        dest="publish_date",
        default=date.today().isoformat(),
        help="Publish date in YYYY-MM-DD format.",
    )
    parser.add_argument(
        "--max-items-per-source",
        type=int,
        default=4,
        help="Maximum feed entries to keep from each source.",
    )
    parser.add_argument(
        "--output",
        default="topic_generation_packet.json",
        help="Output JSON file path.",
    )
    args = parser.parse_args()

    publish_date = date.fromisoformat(args.publish_date)
    packet = build_work_packet(
        publish_date=publish_date,
        max_items_per_source=args.max_items_per_source,
    )

    output_path = Path(args.output)
    output_path.write_text(
        json.dumps(packet, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Wrote topic generation packet to {output_path}")


if __name__ == "__main__":
    main()
