"""Pure nutrition / energy-balance math. No I/O, fully unit-tested.

References:
  * BMR: Mifflin-St Jeor (the modern clinical default)
  * TDEE: BMR x activity factor
  * Weight change: ~7700 kcal per kg of body fat
  * Exercise burn: METs x weight(kg) x hours
"""
from __future__ import annotations

from dataclasses import dataclass

ACTIVITY_FACTORS = {
    "sedentary": 1.2,
    "light": 1.375,
    "moderate": 1.55,
    "active": 1.725,
    "very_active": 1.9,
}

# Approximate METs for common activities.
MET = {"walking": 3.5, "running": 9.8, "cycling": 7.5, "gym": 6.0}

KCAL_PER_KG = 7700.0


def bmr_mifflin(sex: str, weight_kg: float, height_cm: float, age: int) -> float:
    base = 10 * weight_kg + 6.25 * height_cm - 5 * age
    if sex.lower().startswith("m"):
        return base + 5
    if sex.lower().startswith("f"):
        return base - 161
    return base - 78  # average when unspecified


def tdee(bmr: float, activity_level: str) -> float:
    return bmr * ACTIVITY_FACTORS.get(activity_level, 1.55)


def calorie_target(tdee_value: float, goal: str, weekly_kg_change: float = 0.5) -> int:
    """Daily target. `goal` in {lose, maintain, gain}. Safe-capped deficit/surplus."""
    daily_delta = (weekly_kg_change * KCAL_PER_KG) / 7.0
    if goal == "lose":
        target = tdee_value - daily_delta
    elif goal == "gain":
        target = tdee_value + daily_delta
    else:
        target = tdee_value
    # Never recommend below a safe floor.
    return int(max(target, 1200))


def calories_burned(activity: str, weight_kg: float, duration_min: int) -> float:
    met = MET.get(activity, 4.0)
    return met * weight_kg * (duration_min / 60.0)


def projected_weeks_to_goal(current_kg: float, target_kg: float, daily_deficit: float) -> float:
    if daily_deficit <= 0 or current_kg <= target_kg:
        return 0.0
    kg_to_lose = current_kg - target_kg
    weekly_loss = (daily_deficit * 7) / KCAL_PER_KG
    return round(kg_to_lose / weekly_loss, 1) if weekly_loss else 0.0


@dataclass
class DayProgress:
    target: int
    consumed: float
    burned: float

    @property
    def remaining(self) -> int:
        return int(self.target - self.consumed + self.burned)

    @property
    def on_track(self) -> bool:
        return self.consumed - self.burned <= self.target * 1.05
