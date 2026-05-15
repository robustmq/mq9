"""Wraps a user handler function as an a2a-sdk AgentExecutor."""

from __future__ import annotations

from typing import Callable, Awaitable

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue


HandlerFn = Callable[[RequestContext, EventQueue], Awaitable[None]]


class _FnAgentExecutor(AgentExecutor):
    """AgentExecutor that delegates to a plain async function."""

    def __init__(self, fn: HandlerFn) -> None:
        self._fn = fn

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        await self._fn(context, event_queue)

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        raise NotImplementedError("cancel not supported")
