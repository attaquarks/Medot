"""Business Assistant tool catalog.

Each tool is a thin, audited wrapper over an integration provider or the DB.
Handlers receive `ctx: ToolContext` plus the JSON arguments and return a small
JSON-serialisable dict that goes back to the model.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from ...config import get_settings
from ...db.base import session_scope
from ...db.models import Client
from ...integrations.calendar import get_calendar_provider
from ...integrations.email import get_email_provider
from ...integrations.tasks import get_task_provider
from ...integrations.whatsapp import get_whatsapp
from ...logging import get_logger
from ...security.audit import audit
from ..principal import principal_whatsapp
from ..tools import ToolContext, ToolRegistry

log = get_logger("business.tools")
registry = ToolRegistry()


def _dt(s: str) -> datetime:
    """Parse an LLM-supplied ISO datetime; naive times get the configured timezone."""
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo(get_settings().timezone))
    return dt


# --------------------------- calendar ----------------------------------------
@registry.tool("list_events", "List calendar events for a given ISO date.",
               {"type": "object", "properties": {"date": {"type": "string"}}, "required": ["date"]})
async def list_events(*, ctx: ToolContext, date: str) -> dict:
    cal = get_calendar_provider(get_settings().calendar_provider)
    start = _dt(date + "T00:00:00")
    events = await cal.list_events(ctx.tenant_id, start, start + timedelta(days=1))
    return {"events": [{"id": e.get("id"), "title": e.get("summary"),
                        "start": e.get("start"), "end": e.get("end")} for e in events]}


@registry.tool("check_availability", "Find free slots between two ISO dates.",
               {"type": "object", "properties": {
                   "date_range": {"type": "array", "items": {"type": "string"}},
                   "duration_min": {"type": "integer"}}, "required": ["date_range", "duration_min"]})
async def check_availability(*, ctx: ToolContext, date_range: list[str], duration_min: int) -> dict:
    cal = get_calendar_provider(get_settings().calendar_provider)
    start, end = _dt(date_range[0] + "T08:00:00"), _dt(date_range[-1] + "T19:00:00")
    slots = await cal.free_slots(ctx.tenant_id, start, end, duration_min)
    return {"slots": [{"start": s.starts_at.isoformat(), "end": s.ends_at.isoformat()} for s in slots[:6]]}


@registry.tool("create_meeting", "Create a calendar event and invite attendees.",
               {"type": "object", "properties": {
                   "title": {"type": "string"}, "start": {"type": "string"},
                   "end": {"type": "string"}, "attendees": {"type": "array", "items": {"type": "string"}}},
                "required": ["title", "start", "end"]})
async def create_meeting(*, ctx: ToolContext, title: str, start: str, end: str, attendees: list[str] | None = None) -> dict:
    cal = get_calendar_provider(get_settings().calendar_provider)
    eid = await cal.create_event(ctx.tenant_id, title, _dt(start), _dt(end), attendees or [])
    async with session_scope() as s:
        await audit(s, tenant_id=ctx.tenant_id, agent="business", action="create_meeting", resource=eid)
    return {"event_id": eid, "status": "created"}


@registry.tool("reschedule_meeting", "Move an existing event to a new time.",
               {"type": "object", "properties": {
                   "event_id": {"type": "string"}, "new_start": {"type": "string"}, "new_end": {"type": "string"}},
                "required": ["event_id", "new_start", "new_end"]})
async def reschedule_meeting(*, ctx: ToolContext, event_id: str, new_start: str, new_end: str) -> dict:
    cal = get_calendar_provider(get_settings().calendar_provider)
    await cal.update_event(ctx.tenant_id, event_id, start=_dt(new_start), end=_dt(new_end))
    async with session_scope() as s:
        await audit(s, tenant_id=ctx.tenant_id, agent="business", action="reschedule_meeting", resource=event_id)
    return {"event_id": event_id, "status": "rescheduled"}


@registry.tool("cancel_meeting", "Cancel an event by id.",
               {"type": "object", "properties": {"event_id": {"type": "string"}}, "required": ["event_id"]})
async def cancel_meeting(*, ctx: ToolContext, event_id: str) -> dict:
    await get_calendar_provider(get_settings().calendar_provider).cancel_event(ctx.tenant_id, event_id)
    return {"event_id": event_id, "status": "cancelled"}


# ----------------------------- email -----------------------------------------
@registry.tool("inbox_summary", "Summarize recent inbox messages with urgency tags.",
               {"type": "object", "properties": {"max_results": {"type": "integer"}}})
async def inbox_summary(*, ctx: ToolContext, max_results: int = 15) -> dict:
    emails = await get_email_provider(get_settings().email_provider).list_recent(ctx.tenant_id, max_results=max_results)
    return {"count": len(emails),
            "messages": [{"id": e.external_id, "from": e.sender, "subject": e.subject,
                          "snippet": e.snippet} for e in emails]}


@registry.tool("draft_email", "Create (but do NOT send) an email draft.",
               {"type": "object", "properties": {
                   "to": {"type": "string"}, "subject": {"type": "string"}, "body": {"type": "string"}},
                "required": ["to", "subject", "body"]})
async def draft_email(*, ctx: ToolContext, to: str, subject: str, body: str) -> dict:
    did = await get_email_provider(get_settings().email_provider).create_draft(ctx.tenant_id, to, subject, body)
    return {"draft_id": did, "status": "draft_created"}


@registry.tool("send_email", "Send an email. Use only when the user explicitly approved.",
               {"type": "object", "properties": {
                   "to": {"type": "string"}, "subject": {"type": "string"}, "body": {"type": "string"}},
                "required": ["to", "subject", "body"]})
async def send_email(*, ctx: ToolContext, to: str, subject: str, body: str) -> dict:
    mid = await get_email_provider(get_settings().email_provider).send(ctx.tenant_id, to, subject, body)
    async with session_scope() as s:
        await audit(s, tenant_id=ctx.tenant_id, agent="business", action="send_email", resource=to)
    return {"message_id": mid, "status": "sent"}


# ----------------------------- tasks -----------------------------------------
@registry.tool("add_task", "Add a follow-up/task with optional ISO due date.",
               {"type": "object", "properties": {"title": {"type": "string"}, "due_at": {"type": "string"}},
                "required": ["title"]})
async def add_task(*, ctx: ToolContext, title: str, due_at: str | None = None) -> dict:
    tid = await get_task_provider().add(ctx.tenant_id, title, _dt(due_at) if due_at else None)
    return {"task_id": tid, "status": "added"}


@registry.tool("list_tasks", "List open tasks/follow-ups.", {"type": "object", "properties": {}})
async def list_tasks(*, ctx: ToolContext) -> dict:
    return {"tasks": await get_task_provider().list_open(ctx.tenant_id)}


# -------------------------- CRM + escalation ----------------------------------
@registry.tool("remember_client", "Persist a fact/preference about a contact (CRM).",
               {"type": "object", "properties": {"name": {"type": "string"}, "fact": {"type": "string"}},
                "required": ["name", "fact"]})
async def remember_client(*, ctx: ToolContext, name: str, fact: str) -> dict:
    async with session_scope() as s:
        client = Client(tenant_id=ctx.tenant_id, name=name, notes=fact)
        s.add(client)
        await s.flush()
        cid = client.id
    # Also store in semantic memory for recall during future chats.
    from ...memory.long_term import LongTermStore
    await LongTermStore("business").remember(ctx.tenant_id, f"{name}: {fact}", kind="preference")
    return {"client_id": cid, "status": "remembered"}


@registry.tool("escalate", "Notify the principal on WhatsApp about an important matter.",
               {"type": "object", "properties": {"reason": {"type": "string"}, "detail": {"type": "string"}},
                "required": ["reason", "detail"]})
async def escalate(*, ctx: ToolContext, reason: str, detail: str) -> dict:
    msg = f"🔔 Escalation ({reason})\n{detail}\n\n— from {ctx.peer}"
    target = await principal_whatsapp(ctx.tenant_id)
    if not target:
        log.warning("escalation_no_principal", reason=reason)
        return {"status": "skipped", "reason": "no principal WhatsApp configured"}
    await get_whatsapp().send_text(target, msg)
    async with session_scope() as s:
        await audit(s, tenant_id=ctx.tenant_id, agent="business", action="escalate", resource=reason)
    return {"status": "escalated"}
