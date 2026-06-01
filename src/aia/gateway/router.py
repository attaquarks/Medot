"""Decide which agent should handle an inbound WhatsApp message.

Strategy (cheap → smart):
  1. Explicit per-number mapping: the WhatsApp sidecar can be configured so a
     dedicated number/line is always "business" or "health" (best for clients).
  2. Slash command: a message starting with /biz or /health forces routing.
  3. Keyword heuristic: obvious health words -> health, else business.
  4. (Optional) LLM fallback classifier for ambiguous personal messages.

For a single-number personal install, business is the safe default; the health
coach is opt-in via /health or health keywords. Document this in onboarding.
"""
from __future__ import annotations

from ..llm.router import get_router

HEALTH_WORDS = (
    "calorie", "calories", "meal", "ate", "eat", "breakfast", "lunch", "dinner",
    "snack", "weight", "kg", "protein", "workout", "run", "walk", "gym", "cycling",
    "diet", "macro", "steps",
)


async def route(text: str, *, number_tag: str | None = None, use_llm: bool = False) -> str:
    """Return 'business' or 'health'."""
    if number_tag in ("business", "health"):
        return number_tag

    stripped = text.strip().lower()
    if stripped.startswith("/health"):
        return "health"
    if stripped.startswith("/biz") or stripped.startswith("/business"):
        return "business"

    if any(w in stripped for w in HEALTH_WORDS):
        return "health"

    if use_llm:
        verdict = await get_router().complete(
            [{"role": "user", "content":
              f"Classify this message as exactly 'business' or 'health':\n{text}"}],
            complexity="auto",
        )
        return "health" if "health" in verdict.lower() else "business"

    return "business"
