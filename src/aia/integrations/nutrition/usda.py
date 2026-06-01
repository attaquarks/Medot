"""USDA FoodData Central adapter (free API key).

Search the database and map the standard nutrient IDs to our macro fields.
Falls back gracefully to None so the agent can ask the LLM for an estimate.
"""
from __future__ import annotations

import httpx

from ...config import get_settings
from .base import NutritionInfo, NutritionProvider

SEARCH = "https://api.nal.usda.gov/fdc/v1/foods/search"
# USDA nutrient numbers
_KCAL, _PROT, _CARB, _FAT = "208", "203", "205", "204"


class USDAProvider(NutritionProvider):
    async def lookup(self, query: str) -> NutritionInfo | None:
        key = get_settings().usda_api_key
        if not key:
            return None
        async with httpx.AsyncClient(timeout=20) as http:
            r = await http.get(SEARCH, params={"query": query, "api_key": key, "pageSize": 1})
            r.raise_for_status()
            foods = r.json().get("foods", [])
        if not foods:
            return None
        food = foods[0]
        macros = {n.get("nutrientNumber"): n.get("value", 0.0) for n in food.get("foodNutrients", [])}
        return NutritionInfo(
            name=food.get("description", query),
            calories=float(macros.get(_KCAL, 0.0)),
            protein_g=float(macros.get(_PROT, 0.0)),
            carbs_g=float(macros.get(_CARB, 0.0)),
            fat_g=float(macros.get(_FAT, 0.0)),
            serving="100 g",
        )
