"""OpenFoodFacts adapter (stub, no key required).

Good for packaged/barcode products: GET /cgi/search.pl?search_terms=...&json=1
then read product.nutriments. Conforms to NutritionProvider.
"""
from __future__ import annotations

import httpx

from .base import NutritionInfo, NutritionProvider

SEARCH = "https://world.openfoodfacts.org/cgi/search.pl"


class OpenFoodFactsProvider(NutritionProvider):
    async def lookup(self, query: str) -> NutritionInfo | None:
        async with httpx.AsyncClient(timeout=20) as http:
            r = await http.get(
                SEARCH,
                params={"search_terms": query, "search_simple": 1, "json": 1, "page_size": 1},
            )
            r.raise_for_status()
            products = r.json().get("products", [])
        if not products:
            return None
        n = products[0].get("nutriments", {})
        return NutritionInfo(
            name=products[0].get("product_name", query),
            calories=float(n.get("energy-kcal_100g", 0) or 0),
            protein_g=float(n.get("proteins_100g", 0) or 0),
            carbs_g=float(n.get("carbohydrates_100g", 0) or 0),
            fat_g=float(n.get("fat_100g", 0) or 0),
            serving="100 g",
        )
