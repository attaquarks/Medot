"""Health & Diet Coach tool catalog."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from ...db.base import session_scope
from ...db.models import Exercise, HealthProfile, Meal, WeightLog
from ...integrations.nutrition import get_nutrition_provider
from ...llm.router import get_router
from ...logging import get_logger
from ..tools import ToolContext, ToolRegistry
from . import nutrition as nut

log = get_logger("health.tools")
registry = ToolRegistry()


async def _profile(tenant_id: str) -> HealthProfile:
    async with session_scope() as s:
        row = (await s.execute(
            select(HealthProfile).where(HealthProfile.tenant_id == tenant_id)
        )).scalars().first()
        if not row:
            row = HealthProfile(tenant_id=tenant_id)
            s.add(row)
            await s.flush()
        # detach-safe snapshot
        return HealthProfile(
            tenant_id=row.tenant_id, sex=row.sex, age=row.age, height_cm=row.height_cm,
            weight_kg=row.weight_kg, activity_level=row.activity_level, goal=row.goal,
            target_weight_kg=row.target_weight_kg, target_calories=row.target_calories,
        )


def _today_bounds() -> tuple[datetime, datetime]:
    now = datetime.now(timezone.utc)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return start, start + timedelta(days=1)


async def _estimate_macros(description: str) -> dict:
    """Provider lookup first; fall back to an LLM estimate (still useful offline-ish)."""
    info = await get_nutrition_provider().lookup(description)
    if info:
        return {"calories": info.calories, "protein_g": info.protein_g,
                "carbs_g": info.carbs_g, "fat_g": info.fat_g, "source": "db"}
    prompt = (
        "Estimate total calories and macros (grams) for this meal. "
        'Reply ONLY as JSON: {"calories":int,"protein_g":int,"carbs_g":int,"fat_g":int}.\n'
        f"Meal: {description}"
    )
    raw = await get_router().complete([{"role": "user", "content": prompt}], complexity="auto")
    try:
        data = json.loads(raw[raw.find("{"): raw.rfind("}") + 1])
        data["source"] = "estimate"
        return data
    except Exception:
        return {"calories": 0, "protein_g": 0, "carbs_g": 0, "fat_g": 0, "source": "unknown"}


@registry.tool("log_meal", "Log a meal from a natural-language description; estimates kcal + macros.",
               {"type": "object", "properties": {"description": {"type": "string"}},
                "required": ["description"]})
async def log_meal(*, ctx: ToolContext, description: str) -> dict:
    m = await _estimate_macros(description)
    async with session_scope() as s:
        s.add(Meal(tenant_id=ctx.tenant_id, description=description,
                   calories=m["calories"], protein_g=m["protein_g"],
                   carbs_g=m["carbs_g"], fat_g=m["fat_g"], source=m["source"]))
    status = await daily_status(ctx=ctx)
    return {"logged": m, "today": status}


@registry.tool("log_weight", "Record a body-weight measurement in kg.",
               {"type": "object", "properties": {"weight_kg": {"type": "number"}},
                "required": ["weight_kg"]})
async def log_weight(*, ctx: ToolContext, weight_kg: float) -> dict:
    async with session_scope() as s:
        s.add(WeightLog(tenant_id=ctx.tenant_id, weight_kg=weight_kg))
    return {"status": "logged", "weight_kg": weight_kg}


@registry.tool("log_exercise", "Log a workout; estimates calories burned.",
               {"type": "object", "properties": {
                   "kind": {"type": "string", "enum": ["walking", "running", "cycling", "gym"]},
                   "duration_min": {"type": "integer"}}, "required": ["kind", "duration_min"]})
async def log_exercise(*, ctx: ToolContext, kind: str, duration_min: int) -> dict:
    prof = await _profile(ctx.tenant_id)
    burned = nut.calories_burned(kind, prof.weight_kg, duration_min)
    async with session_scope() as s:
        s.add(Exercise(tenant_id=ctx.tenant_id, kind=kind,
                       duration_min=duration_min, calories_burned=burned))
    return {"status": "logged", "calories_burned": round(burned)}


@registry.tool("daily_status", "Today's calories consumed, burned, and remaining vs target.",
               {"type": "object", "properties": {}})
async def daily_status(*, ctx: ToolContext) -> dict:
    prof = await _profile(ctx.tenant_id)
    target = prof.target_calories or nut.calorie_target(
        nut.tdee(nut.bmr_mifflin(prof.sex, prof.weight_kg, prof.height_cm, prof.age), prof.activity_level),
        prof.goal,
    )
    start, end = _today_bounds()
    async with session_scope() as s:
        meals = (await s.execute(select(Meal).where(
            Meal.tenant_id == ctx.tenant_id, Meal.logged_at >= start, Meal.logged_at < end))).scalars().all()
        ex = (await s.execute(select(Exercise).where(
            Exercise.tenant_id == ctx.tenant_id, Exercise.logged_at >= start, Exercise.logged_at < end))).scalars().all()
    consumed = sum(m.calories for m in meals)
    burned = sum(e.calories_burned for e in ex)
    prog = nut.DayProgress(target=target, consumed=consumed, burned=burned)
    return {"target": target, "consumed": round(consumed), "burned": round(burned),
            "remaining": prog.remaining, "protein_g": round(sum(m.protein_g for m in meals)),
            "on_track": prog.on_track}


@registry.tool("set_goal", "Set weight goal & recompute the daily calorie target.",
               {"type": "object", "properties": {
                   "goal": {"type": "string", "enum": ["lose", "maintain", "gain"]},
                   "target_weight_kg": {"type": "number"},
                   "weekly_kg_change": {"type": "number"}}, "required": ["goal"]})
async def set_goal(*, ctx: ToolContext, goal: str, target_weight_kg: float | None = None,
                   weekly_kg_change: float = 0.5) -> dict:
    async with session_scope() as s:
        row = (await s.execute(select(HealthProfile).where(
            HealthProfile.tenant_id == ctx.tenant_id))).scalars().first()
        if not row:
            row = HealthProfile(tenant_id=ctx.tenant_id)
            s.add(row)
        row.goal = goal
        if target_weight_kg:
            row.target_weight_kg = target_weight_kg
        tdee_v = nut.tdee(nut.bmr_mifflin(row.sex, row.weight_kg, row.height_cm, row.age), row.activity_level)
        row.target_calories = nut.calorie_target(tdee_v, goal, weekly_kg_change)
        target = row.target_calories
    return {"status": "updated", "daily_calorie_target": target}


@registry.tool("weekly_report", "Summarize the last 7 days: avg calories, weight trend, workouts.",
               {"type": "object", "properties": {}})
async def weekly_report(*, ctx: ToolContext) -> dict:
    since = datetime.now(timezone.utc) - timedelta(days=7)
    async with session_scope() as s:
        meals = (await s.execute(select(Meal).where(
            Meal.tenant_id == ctx.tenant_id, Meal.logged_at >= since))).scalars().all()
        weights = (await s.execute(select(WeightLog).where(
            WeightLog.tenant_id == ctx.tenant_id, WeightLog.logged_at >= since)
            .order_by(WeightLog.logged_at))).scalars().all()
        workouts = (await s.execute(select(Exercise).where(
            Exercise.tenant_id == ctx.tenant_id, Exercise.logged_at >= since))).scalars().all()
    avg_cal = round(sum(m.calories for m in meals) / 7) if meals else 0
    trend = round(weights[-1].weight_kg - weights[0].weight_kg, 1) if len(weights) >= 2 else 0.0
    return {"avg_daily_calories": avg_cal, "weight_change_kg": trend,
            "workouts": len(workouts), "meals_logged": len(meals)}
