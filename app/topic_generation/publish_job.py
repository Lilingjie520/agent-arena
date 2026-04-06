from __future__ import annotations

import argparse
import json
from dataclasses import asdict, is_dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from app.topic_generation.llm import LLMConfigError, OpenAICompatibleTopicLLM
from app.topic_generation.sources import collect_recent_entries


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


def build_publish_output(
    *,
    publish_date: date,
    status: str,
    reason: str,
    result: Any | None,
    created_topic_ids: list[int],
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "publish_date": publish_date.isoformat(),
        "status": status,
        "reason": reason,
        "created_topic_ids": created_topic_ids,
    }
    if result is not None:
        payload["source_entries"] = [_to_jsonable(item) for item in result.source_entries]
        payload["signals"] = [_to_jsonable(item) for item in result.signals]
        payload["candidates"] = [_to_jsonable(item) for item in result.candidates]
        payload["reviews"] = [_to_jsonable(item) for item in result.reviews]
        payload["published_batch"] = _to_jsonable(result.published_batch)
    return payload


def ensure_output_path(output_dir: Path, publish_date: date) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%H%M%S")
    return output_dir / f"{publish_date.isoformat()}-{timestamp}.json"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate and publish the daily topic batch into the Topic table."
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
        "--output-dir",
        default="topic_generation_runs",
        help="Directory for job artifacts.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run the pipeline but do not write the final topics into the database.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Run even if the target date already has published topics.",
    )
    args = parser.parse_args()

    publish_date = date.fromisoformat(args.publish_date)
    output_path = ensure_output_path(Path(args.output_dir), publish_date)

    from app.database import SessionLocal
    from app.models import Topic
    from app.topic_generation.pipeline import LLMDrivenTopicPipeline

    db = SessionLocal()
    try:
        existing_count = db.query(Topic).filter(Topic.date == publish_date).count()
        if existing_count >= 3 and not args.force:
            payload = build_publish_output(
                publish_date=publish_date,
                status="skipped",
                reason=(
                    f"{publish_date.isoformat()} already has {existing_count} topics. "
                    "Use --force to run anyway."
                ),
                result=None,
                created_topic_ids=[],
            )
            output_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            print(f"Skipped publish job for {publish_date}; wrote {output_path}")
            return

        entries = collect_recent_entries(max_items_per_source=args.max_items_per_source)
        if not entries:
            raise SystemExit(
                "No source entries were collected. Refusing to generate topics "
                "without real-world source anchors."
            )

        llm = OpenAICompatibleTopicLLM.from_env()
        pipeline = LLMDrivenTopicPipeline(llm)
        result = pipeline.run(entries, publish_date=publish_date)

        created_topic_ids: list[int] = []
        status = "dry_run" if args.dry_run else "published"
        reason = "Generated successfully."

        if not args.dry_run:
            created_topics = pipeline.write_batch_to_topics(
                db,
                result.published_batch,
                skip_existing=args.force,
            )
            created_topic_ids = [topic.id for topic in created_topics]
            reason = (
                f"Published {len(created_topic_ids)} topics for {publish_date.isoformat()}."
            )

        payload = build_publish_output(
            publish_date=publish_date,
            status=status,
            reason=reason,
            result=result,
            created_topic_ids=created_topic_ids,
        )
        output_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"Completed publish job; wrote {output_path}")
    finally:
        db.close()


if __name__ == "__main__":
    try:
        main()
    except LLMConfigError as exc:
        raise SystemExit(str(exc)) from exc
