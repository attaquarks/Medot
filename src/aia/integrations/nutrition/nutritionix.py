"""Nutritionix natural-language adapter (stub).

POST /v2/natural/nutrients with {"query": "2 eggs and toast"} returns parsed
per-item macros — a great fit for this agent. Add NUTRITIONIX_APP_ID/API_KEY.
"""
from __future__ import annotations

import httpx

from ...config import get_settings
from .base import NutritionInfo, NutritionProvider

URL = "https://trackapi.nutritionix.com/v2/natural/nutrients"


class NutritionixProvider(NutritionProvider):
    async def lookup(self, query: str) -> NutritionInfo | None:
        s = get_settings()
        if not (s.nutritionix_app_id and s.nutritionix_api_key):
            return None
        headers = {"x-app-id": s.nutritionix_app_id, "x-app-key": s.nutritionix_api_key}
        async with httpx.AsyncClient(timeout=20) as http:
            r = await http.post(URL, json={"query": query}, headers=headers)
            r.raise_for_status()
            foods = r.json().get("foods", [])
        if not foods:
            return None
        # Aggregate multi-item queries into one NutritionInfo.
        total = {"cal": 0.0, "p": 0.0, "c": 0.0, "f": 0.0}
        for f in foods:
            total["cal"] += f.get("nf_calories", 0) or 0
            total["p"] += f.get("nf_protein", 0) or 0
            total["c"] += f.get("nf_total_carbohydrate", 0) or 0
            total["f"] += f.get("nf_total_fat", 0) or 0
        return NutritionInfo(query, total["cal"], total["p"], total["c"], total["f"], serving="as described")
