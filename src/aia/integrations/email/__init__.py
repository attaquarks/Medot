"""Email abstraction (Gmail / Microsoft Graph) behind one interface."""
from .base import EmailMessage, EmailProvider, get_email_provider

__all__ = ["EmailMessage", "EmailProvider", "get_email_provider"]
