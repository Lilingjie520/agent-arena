from datetime import date
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Sector, Topic

router = APIRouter(prefix="/api", tags=["topics"])


@router.get("/sectors")
def get_sectors(db: Session = Depends(get_db)):
    sectors = db.query(Sector).all()
    return [
        {"id": s.id, "name": s.name, "icon": s.icon, "description": s.description}
        for s in sectors
    ]


@router.get("/topics/today")
def get_today_topics(db: Session = Depends(get_db)):
    today = date.today()
    topics = db.query(Topic).filter(Topic.date == today).all()
    if not topics:
        topics = db.query(Topic).order_by(Topic.date.desc()).limit(3).all()
    return [
        {
            "id": t.id,
            "sector": t.sector.name,
            "sector_icon": t.sector.icon,
            "title": t.title,
            "description": t.description,
            "type": t.topic_type,
            "date": t.date.isoformat(),
            "opinion_count": len(t.opinions),
        }
        for t in topics
    ]


@router.get("/topics/{topic_id}")
def get_topic(topic_id: int, db: Session = Depends(get_db)):
    topic = db.query(Topic).filter(Topic.id == topic_id).first()
    if not topic:
        raise HTTPException(status_code=404, detail="Topic not found")
    return {
        "id": topic.id,
        "sector": topic.sector.name,
        "sector_icon": topic.sector.icon,
        "title": topic.title,
        "description": topic.description,
        "type": topic.topic_type,
        "date": topic.date.isoformat(),
        "opinion_count": len(topic.opinions),
    }
