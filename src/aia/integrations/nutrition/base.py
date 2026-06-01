from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from ...config import get_settings


@dataclass
class NutritionInfo:
    name: str
    calories: float
    protein_g: float
    carbs_g: float
    fat_g: float
    serving: str = "100 g"


class NutritionProvider(ABC):
    @abstractmethod
    async def lookup(self, query: str) -> NutritionInfo | None:
        """Resolve a free-text food description to macros. The agent handles
        portion math and multi-item meals; this returns per-item facts."""


def get_nutrition_provider(provider: str | None = None) -> NutritionProvider:
    provider = provider or get_settings().nutrition_provider
    if provider == "nutritionix":
        from .nutritionix import NutritionixProvider

        return NutritionixProvider()
    if provider == "openfoodfacts":
        from .openfoodfacts import OpenFoodFactsProvider

        return OpenFoodFactsProvider()
    from .usda import USDAProvider

    return USDAProvider()
