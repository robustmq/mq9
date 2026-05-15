"""Mq9A2AClient — thin alias of Mq9A2AAgent for pure-client scenarios.

For most use cases, use Mq9A2AAgent directly — it handles both sending and
receiving.  This class is provided for backends that only send tasks and never
register as agents (e.g. web servers, orchestrators).

It is equivalent to:

    agent = Mq9A2AAgent(name="...", server="...")
    await agent.connect()          # instead of agent.run()
    ...
    await agent.close()
"""

from __future__ import annotations

from .agent import Mq9A2AAgent


class Mq9A2AClient(Mq9A2AAgent):
    """
    Pure-client wrapper: discover agents and send tasks without registering.

    Usage::

        async with Mq9A2AClient(server="nats://demo.robustmq.com:4222") as client:
            agents = await client.discover("translation agent")
            async for event in await client.send_message(agents[0], request):
                print(event)

    All methods (discover, send_message, get_task, list_tasks, cancel_task)
    are inherited from Mq9A2AAgent.  The context manager calls connect()/close()
    instead of run()/stop(), so no mailbox is created and nothing is registered.
    """

    def __init__(self, server: str, *, request_timeout: float = 60.0) -> None:
        super().__init__(server=server, request_timeout=request_timeout)
