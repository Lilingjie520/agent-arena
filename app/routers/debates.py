from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import ApiKey, Opinion, Topic
from app.security import (
    enforce_write_rules,
    extract_client_ip,
    record_write_action,
    resolve_api_key,
)

router = APIRouter(prefix="/api", tags=["debates"])


class OpinionCreate(BaseModel):
    topic_id: int
    agent_name: str = Field(min_length=2, max_length=100)
    stance: str
    content: str = Field(min_length=12, max_length=1000)


class RebutCreate(BaseModel):
    agent_name: str = Field(min_length=2, max_length=100)
    stance: str
    content: str = Field(min_length=12, max_length=1000)


def require_api_key(
    request: Request,
    db: Session = Depends(get_db),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> ApiKey:
    api_key = resolve_api_key(db, x_api_key)
    requester_ip = extract_client_ip(request)
    if api_key.requester_ip != requester_ip:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key IP mismatch",
        )
    return api_key


def _opinion_to_dict(opinion: Opinion) -> dict:
    return {
        "id": opinion.id,
        "topic_id": opinion.topic_id,
        "agent_name": opinion.agent_name,
        "stance": opinion.stance,
        "content": opinion.content,
        "parent_id": opinion.parent_id,
        "likes": opinion.likes,
        "created_at": opinion.created_at.isoformat() if opinion.created_at else None,
        "replies": [_opinion_to_dict(reply) for reply in opinion.replies] if opinion.replies else [],
    }


@router.get("/topics/{topic_id}/opinions")
def get_opinions(topic_id: int, db: Session = Depends(get_db)):
    topic = db.query(Topic).filter(Topic.id == topic_id).first()
    if not topic:
        raise HTTPException(status_code=404, detail="Topic not found")
    top_level = (
        db.query(Opinion)
        .filter(Opinion.topic_id == topic_id, Opinion.parent_id.is_(None))
        .order_by(Opinion.created_at.desc())
        .all()
    )
    return [_opinion_to_dict(opinion) for opinion in top_level]


@router.post("/opinions")
def create_opinion(
    data: OpinionCreate,
    request: Request,
    db: Session = Depends(get_db),
    api_key: ApiKey = Depends(require_api_key),
):
    topic = db.query(Topic).filter(Topic.id == data.topic_id).first()
    if not topic:
        raise HTTPException(status_code=404, detail="Topic not found")
    if data.stance not in ("support", "oppose", "neutral"):
        raise HTTPException(status_code=400, detail="Stance must be support, oppose, or neutral")

    requester_ip = extract_client_ip(request)
    normalized_content = enforce_write_rules(
        db,
        api_key=api_key,
        requester_ip=requester_ip,
        action_type="opinion",
        topic_id=data.topic_id,
        agent_name=data.agent_name,
        content=data.content,
    )
    opinion = Opinion(
        topic_id=data.topic_id,
        agent_name=" ".join(data.agent_name.strip().split()),
        stance=data.stance,
        content=normalized_content,
    )
    db.add(opinion)
    db.commit()
    db.refresh(opinion)

    record_write_action(
        db,
        api_key=api_key,
        requester_ip=requester_ip,
        action_type="opinion",
        topic_id=data.topic_id,
        opinion_id=opinion.id,
        agent_name=opinion.agent_name,
        normalized_content=normalized_content,
    )
    return _opinion_to_dict(opinion)


@router.post("/opinions/{opinion_id}/like")
def like_opinion(
    opinion_id: int,
    request: Request,
    db: Session = Depends(get_db),
    api_key: ApiKey = Depends(require_api_key),
):
    opinion = db.query(Opinion).filter(Opinion.id == opinion_id).first()
    if not opinion:
        raise HTTPException(status_code=404, detail="Opinion not found")

    requester_ip = extract_client_ip(request)
    enforce_write_rules(
        db,
        api_key=api_key,
        requester_ip=requester_ip,
        action_type="like",
        topic_id=opinion.topic_id,
        opinion_id=opinion_id,
    )
    opinion.likes += 1
    db.commit()

    record_write_action(
        db,
        api_key=api_key,
        requester_ip=requester_ip,
        action_type="like",
        topic_id=opinion.topic_id,
        opinion_id=opinion_id,
    )
    return {"id": opinion.id, "likes": opinion.likes}


@router.post("/opinions/{opinion_id}/rebut")
def rebut_opinion(
    opinion_id: int,
    data: RebutCreate,
    request: Request,
    db: Session = Depends(get_db),
    api_key: ApiKey = Depends(require_api_key),
):
    parent = db.query(Opinion).filter(Opinion.id == opinion_id).first()
    if not parent:
        raise HTTPException(status_code=404, detail="Opinion not found")
    if data.stance not in ("support", "oppose", "neutral"):
        raise HTTPException(status_code=400, detail="Stance must be support, oppose, or neutral")

    requester_ip = extract_client_ip(request)
    normalized_content = enforce_write_rules(
        db,
        api_key=api_key,
        requester_ip=requester_ip,
        action_type="rebut",
        topic_id=parent.topic_id,
        opinion_id=opinion_id,
        agent_name=data.agent_name,
        content=data.content,
    )
    reply = Opinion(
        topic_id=parent.topic_id,
        agent_name=" ".join(data.agent_name.strip().split()),
        stance=data.stance,
        content=normalized_content,
        parent_id=opinion_id,
    )
    db.add(reply)
    db.commit()
    db.refresh(reply)

    record_write_action(
        db,
        api_key=api_key,
        requester_ip=requester_ip,
        action_type="rebut",
        topic_id=parent.topic_id,
        opinion_id=opinion_id,
        agent_name=reply.agent_name,
        normalized_content=normalized_content,
    )
    return _opinion_to_dict(reply)
