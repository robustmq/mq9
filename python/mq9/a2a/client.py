"""Mq9A2AClient — thin alias of Mq9A2AAgent for pure-client scenarios."""

from __future__ import annotations

from .agent import Mq9A2AAgent


class Mq9A2AClient(Mq9A2AAgent):
    """Subclass of Mq9A2AAgent with a simplified constructor for pure-client use."""

    def __init__(self, server: str, *, request_timeout: float = 60.0) -> None:
        super().__init__(server=server, request_timeout=request_timeout)
