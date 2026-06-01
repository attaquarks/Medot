"""Nutrition lookup abstraction (USDA / Nutritionix / OpenFoodFacts)."""
from .base import NutritionInfo, NutritionProvider, get_nutrition_provider

__all__ = ["NutritionInfo", "NutritionProvider", "get_nutrition_provider"]
