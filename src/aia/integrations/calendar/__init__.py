"""Calendar abstraction (Google Calendar / Microsoft Graph)."""
from .base import CalendarProvider, CalendarSlot, get_calendar_provider

__all__ = ["CalendarProvider", "CalendarSlot", "get_calendar_provider"]
