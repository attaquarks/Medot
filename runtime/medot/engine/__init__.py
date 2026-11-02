"""The Medot engine (M4a): Me. answering a turn.

Doc 11 contract: LangGraph orchestrates the turn (StateGraph + SQLite
checkpointer), LangChain is the model/tool interface, Medot owns all
persistence. This first slice has no tools — the agent harness
(`create_agent`) arrives with the tool layer (M4b).
"""
from __future__ import annotations

from .turn import run_turn

__all__ = ["run_turn"]
