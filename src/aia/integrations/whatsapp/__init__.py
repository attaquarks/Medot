"""WhatsApp transport abstraction.

Two interchangeable adapters behind one `WhatsAppProvider` interface:
  * BaileysProvider  (default) — talks to the Node sidecar that runs Baileys.
       Pairing = scan a QR (like WhatsApp Web). Easiest for non-technical users.
       UNOFFICIAL: against WhatsApp ToS, ban risk — use a secondary number.
  * CloudApiProvider — Meta's official WhatsApp Business Cloud API. Compliant,
       template-message rules, recommended for the client-facing Business agent.

Switch with WHATSAPP_PROVIDER=baileys|cloud. Agents only ever see this interface.
"""
from .base import WhatsAppProvider, get_whatsapp

__all__ = ["WhatsAppProvider", "get_whatsapp"]
