"""AIA — local multi-agent personal assistant (Business + Health) over WhatsApp.

The whole system is one installable package (`aia`) with several entrypoints:
    python -m aia.gateway.main           # inbound router
    python -m aia.agents.business.service # Agent 1 worker
    python -m aia.agents.health.service   # Agent 2 worker
    python -m aia.onboarding.main         # setup wizard

Shared infrastructure (config, db, security, llm, memory, events) lives here and
is reused by both agents, but each agent keeps its own prompts, tools, tables and
memory namespace so they remain fully independent (Requirement #1).
"""

__version__ = "0.1.0"
