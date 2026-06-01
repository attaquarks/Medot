"""ORM models for all three schemas.

  core.*      shared infra: tenants, encrypted credentials, conversations,
              messages, long-term semantic memory (pgvector), audit logs
  business.*  Agent 1: clients (CRM), emails, calendar_events, tasks, call_logs
  health.*    Agent 2: profile, meals, weight_logs, exercises, targets

Every row carries a `tenant_id` so a single codebase serves one user per laptop
*and* many users in a hosted deployment with zero schema changes.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from .base import SCHEMA_BUSINESS, SCHEMA_CORE, SCHEMA_HEALTH, Base

EMBED_DIM = 768  # nomic-embed-text / many local embedders


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class _PK:
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True, default="default")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


# ============================== core schema ==================================
class Tenant(_PK, Base):
    __tablename__ = "tenants"
    __table_args__ = {"schema": SCHEMA_CORE}
    name: Mapped[str] = mapped_column(String(255), default="Owner")
    timezone: Mapped[str] = mapped_column(String(64), default="UTC")
    preferences: Mapped[dict] = mapped_column(JSON, default=dict)


class Credential(_PK, Base):
    """OAuth tokens / API keys, ALWAYS stored encrypted (see aia.security.crypto)."""
    __tablename__ = "credentials"
    __table_args__ = {"schema": SCHEMA_CORE}
    provider: Mapped[str] = mapped_column(String(64))         # google, microsoft, twilio...
    account_label: Mapped[str] = mapped_column(String(255), default="")
    encrypted_blob: Mapped[str] = mapped_column(Text)         # envelope-encrypted JSON
    scopes: Mapped[str] = mapped_column(Text, default="")
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Conversation(_PK, Base):
    __tablename__ = "conversations"
    __table_args__ = {"schema": SCHEMA_CORE}
    agent: Mapped[str] = mapped_column(String(32), index=True)   # "business" | "health"
    channel: Mapped[str] = mapped_column(String(32), default="whatsapp")
    peer: Mapped[str] = mapped_column(String(128), index=True)   # WhatsApp id / client


class Message(_PK, Base):
    __tablename__ = "messages"
    __table_args__ = {"schema": SCHEMA_CORE}
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey(f"{SCHEMA_CORE}.conversations.id"), index=True
    )
    role: Mapped[str] = mapped_column(String(16))  # user | assistant | tool | system
    content: Mapped[str] = mapped_column(Text)
    meta: Mapped[dict] = mapped_column(JSON, default=dict)


class LongTermMemory(_PK, Base):
    """Semantic memory. `agent` namespaces rows so agents never read each other."""
    __tablename__ = "long_term_memory"
    __table_args__ = {"schema": SCHEMA_CORE}
    agent: Mapped[str] = mapped_column(String(32), index=True)
    kind: Mapped[str] = mapped_column(String(32), default="fact")  # fact|preference|summary
    content: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBED_DIM))
    meta: Mapped[dict] = mapped_column(JSON, default=dict)


class AuditLog(_PK, Base):
    __tablename__ = "audit_logs"
    __table_args__ = {"schema": SCHEMA_CORE}
    agent: Mapped[str] = mapped_column(String(32))
    action: Mapped[str] = mapped_column(String(128))
    resource: Mapped[str | None] = mapped_column(String(255), nullable=True)
    meta: Mapped[dict] = mapped_column(JSON, default=dict)


# ============================ business schema ================================
class Client(_PK, Base):
    __tablename__ = "clients"
    __table_args__ = {"schema": SCHEMA_BUSINESS}
    name: Mapped[str] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    company: Mapped[str | None] = mapped_column(String(255), nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    preferences: Mapped[dict] = mapped_column(JSON, default=dict)


class Email(_PK, Base):
    __tablename__ = "emails"
    __table_args__ = {"schema": SCHEMA_BUSINESS}
    provider: Mapped[str] = mapped_column(String(32))         # gmail | outlook
    external_id: Mapped[str] = mapped_column(String(255), index=True)
    sender: Mapped[str] = mapped_column(String(255))
    subject: Mapped[str] = mapped_column(Text, default="")
    category: Mapped[str] = mapped_column(String(64), default="uncategorized")
    urgency: Mapped[str] = mapped_column(String(16), default="normal")  # low|normal|high|urgent
    summary: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(32), default="unread")
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CalendarEvent(_PK, Base):
    __tablename__ = "calendar_events"
    __table_args__ = {"schema": SCHEMA_BUSINESS}
    provider: Mapped[str] = mapped_column(String(32))
    external_id: Mapped[str] = mapped_column(String(255), index=True)
    title: Mapped[str] = mapped_column(Text, default="")
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    attendees: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(32), default="confirmed")


class Task(_PK, Base):
    __tablename__ = "tasks"
    __table_args__ = {"schema": SCHEMA_BUSINESS}
    title: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="open")  # open|doing|done
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source: Mapped[str] = mapped_column(String(32), default="manual")  # email|call|whatsapp
    client_id: Mapped[str | None] = mapped_column(String(36), nullable=True)


class CallLog(_PK, Base):
    __tablename__ = "call_logs"
    __table_args__ = {"schema": SCHEMA_BUSINESS}
    direction: Mapped[str] = mapped_column(String(8))  # in | out
    peer: Mapped[str] = mapped_column(String(64))
    duration_sec: Mapped[int] = mapped_column(Integer, default=0)
    transcript: Mapped[str] = mapped_column(Text, default="")
    summary: Mapped[str] = mapped_column(Text, default="")
    escalated: Mapped[bool] = mapped_column(Boolean, default=False)


# ============================= health schema =================================
class HealthProfile(_PK, Base):
    __tablename__ = "health_profile"
    __table_args__ = {"schema": SCHEMA_HEALTH}
    sex: Mapped[str] = mapped_column(String(8), default="unspecified")
    age: Mapped[int] = mapped_column(Integer, default=30)
    height_cm: Mapped[float] = mapped_column(Float, default=170.0)
    weight_kg: Mapped[float] = mapped_column(Float, default=70.0)
    activity_level: Mapped[str] = mapped_column(String(16), default="moderate")
    goal: Mapped[str] = mapped_column(String(16), default="lose")  # lose|maintain|gain
    target_weight_kg: Mapped[float | None] = mapped_column(Float, nullable=True)
    target_calories: Mapped[int | None] = mapped_column(Integer, nullable=True)


class Meal(_PK, Base):
    __tablename__ = "meals"
    __table_args__ = {"schema": SCHEMA_HEALTH}
    logged_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    description: Mapped[str] = mapped_column(Text)
    calories: Mapped[float] = mapped_column(Float, default=0)
    protein_g: Mapped[float] = mapped_column(Float, default=0)
    carbs_g: Mapped[float] = mapped_column(Float, default=0)
    fat_g: Mapped[float] = mapped_column(Float, default=0)
    source: Mapped[str] = mapped_column(String(32), default="estimate")  # usda|nutritionix|estimate


class WeightLog(_PK, Base):
    __tablename__ = "weight_logs"
    __table_args__ = {"schema": SCHEMA_HEALTH}
    logged_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    weight_kg: Mapped[float] = mapped_column(Float)


class Exercise(_PK, Base):
    __tablename__ = "exercises"
    __table_args__ = {"schema": SCHEMA_HEALTH}
    logged_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    kind: Mapped[str] = mapped_column(String(32))  # walking|running|gym|cycling
    duration_min: Mapped[int] = mapped_column(Integer, default=0)
    calories_burned: Mapped[float] = mapped_column(Float, default=0)


class HealthTarget(_PK, Base):
    __tablename__ = "targets"
    __table_args__ = {"schema": SCHEMA_HEALTH}
    day: Mapped[str] = mapped_column(String(10), index=True)  # YYYY-MM-DD
    calorie_target: Mapped[int] = mapped_column(Integer, default=2000)
    protein_target_g: Mapped[int] = mapped_column(Integer, default=120)
