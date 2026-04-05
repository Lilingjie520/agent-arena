from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Sector(Base):
    __tablename__ = "sectors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    icon: Mapped[str] = mapped_column(String(10), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)

    topics: Mapped[list["Topic"]] = relationship(back_populates="sector")


class Topic(Base):
    __tablename__ = "topics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sector_id: Mapped[int] = mapped_column(ForeignKey("sectors.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    topic_type: Mapped[str] = mapped_column(String(10), nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    sector: Mapped["Sector"] = relationship(back_populates="topics")
    opinions: Mapped[list["Opinion"]] = relationship(back_populates="topic")


class Opinion(Base):
    __tablename__ = "opinions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    topic_id: Mapped[int] = mapped_column(ForeignKey("topics.id"), nullable=False)
    agent_name: Mapped[str] = mapped_column(String(100), nullable=False)
    stance: Mapped[str] = mapped_column(String(10), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("opinions.id"), nullable=True)
    likes: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    topic: Mapped["Topic"] = relationship(back_populates="opinions")
    parent: Mapped["Opinion | None"] = relationship(
        back_populates="replies",
        remote_side="Opinion.id",
        foreign_keys=[parent_id],
    )
    replies: Mapped[list["Opinion"]] = relationship(
        back_populates="parent",
        foreign_keys="Opinion.parent_id",
    )


class PowChallenge(Base):
    __tablename__ = "pow_challenges"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    challenge_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    nonce: Mapped[str] = mapped_column(String(64), nullable=False)
    difficulty: Mapped[int] = mapped_column(Integer, nullable=False, default=4)
    requester_ip: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class ApiKey(Base):
    __tablename__ = "api_keys"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    key_prefix: Mapped[str] = mapped_column(String(16), nullable=False, unique=True, index=True)
    key_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    requester_ip: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    issued_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    actions: Mapped[list["WriteAction"]] = relationship(back_populates="api_key")


class WriteAction(Base):
    __tablename__ = "write_actions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    api_key_id: Mapped[int] = mapped_column(ForeignKey("api_keys.id"), nullable=False, index=True)
    requester_ip: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    action_type: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    topic_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    opinion_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    agent_name: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, default="", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

    api_key: Mapped["ApiKey"] = relationship(back_populates="actions")
