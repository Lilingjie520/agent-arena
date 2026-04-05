from __future__ import annotations

import argparse
import json
from dataclasses import asdict, is_dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from app.topic_generation.llm import LLMConfigError, OpenAICompatibleTopicLLM
from app.topic_generation.sources import collect_recent_entries


def build_run_output(result: Any, created_topic_ids: list[int]) -> dict[str, Any]:
    return {
        "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "source_entries": [_to_jsonable(item) for item in result.source_entries],
        "signals": [_to_jsonable(item) for item in result.signals],
        "candidates": [_to_jsonable(item) for item in result.candidates],
        "reviews": [_to_jsonable(item) for item in result.reviews],
        "published_batch": _to_jsonable(result.published_batch),
        "created_topic_ids": created_topic_ids,
    }


def _to_jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return _to_jsonable(asdict(value))
    if isinstance(value, dict):
        return {key: _to_jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_to_jsonable(item) for item in value]
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the multi-agent daily topic generation pipeline."
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
        default="topic_generation_run.json",
        help="Output JSON file path.",
    )
    parser.add_argument(
        "--write-db",
        action="store_true",
        help="Persist the generated daily batch into the Topic table.",
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Skip duplicate topics when writing into the database.",
    )
    args = parser.parse_args()

    publish_date = date.fromisoformat(args.publish_date)
    entries = collect_recent_entries(max_items_per_source=args.max_items_per_source)
    if not entries:
        raise SystemExit(
            "No source entries were collected. Refusing to generate topics "
            "without real-world source anchors."
        )

    from app.topic_generation.pipeline import LLMDrivenTopicPipeline

    llm = OpenAICompatibleTopicLLM.from_env()
    pipeline = LLMDrivenTopicPipeline(llm)
    result = pipeline.run(entries, publish_date=publish_date)

    created_topic_ids: list[int] = []
    if args.write_db:
        from app.database import SessionLocal

        db = SessionLocal()
        try:
            created_topics = pipeline.write_batch_to_topics(
                db,
                result.published_batch,
                skip_existing=args.skip_existing,
            )
            created_topic_ids = [topic.id for topic in created_topics]
        finally:
            db.close()

    output_path = Path(args.output)
    output_path.write_text(
        json.dumps(
            build_run_output(result, created_topic_ids),
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"Wrote topic generation run output to {output_path}")


if __name__ == "__main__":
    try:
        main()
    except LLMConfigError as exc:
        raise SystemExit(str(exc)) from exc
