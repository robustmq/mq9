"""Mq9A2AAgent — A2A agent that uses mq9 as its transport.

Each agent is both a server (registers and receives tasks) and a client
(discovers and sends tasks to other agents).

Lifecycle:

  Client mode (send only):
    agent = Mq9A2AAgent(server="nats://...")
    await agent.connect()
    agents = await agent.discover("translator")
    ...
    await agent.close()

  Agent mode (send + receive):
    agent = Mq9A2AAgent(server="nats://...")

    @agent.on_message
    async def handle(context, event_queue): ...

    card = AgentCard(name="my-agent", description="...", ...)
    await agent.connect()
    await agent.register(card)   # blocks until stop() or Ctrl+C
"""

from __future__ import annotations

import asyncio
import logging
from typing import AsyncIterator

from a2a.server.agent_execution import RequestContext
from a2a.server.events import InMemoryEventQueue
from a2a.types.a2a_pb2 import (
    AgentCard,
    CancelTaskRequest,
    GetTaskRequest,
    ListTasksRequest,
    ListTasksResponse,
    SendMessageRequest,
    SendMessageResponse,
    Task,
    TaskArtifactUpdateEvent,
    TaskState,
    TaskStatus,
    TaskStatusUpdateEvent,
    Message,
)
from google.protobuf import json_format

from mq9.client import Mq9Client, Priority
from ._executor import _FnAgentExecutor, HandlerFn
from ._task_store import Mq9A2ATaskStore

_logger = logging.getLogger(__name__)

_HEARTBEAT_INTERVAL = 30

_HEADER_METHOD   = "mq9-a2a-method"
_HEADER_REPLY_TO = "mq9-reply-to"
_HEADER_LAST     = "mq9-a2a-last"
_HEADER_TYPE     = "mq9-a2a-type"

_METHOD_SEND       = "SendMessage"
_METHOD_GET_TASK   = "GetTask"
_METHOD_LIST_TASKS = "ListTasks"
_METHOD_CANCEL     = "CancelTask"

_DEFAULT_TIMEOUT = 60.0

_EVENT_TYPES: dict[str, type] = {
    "TaskStatusUpdateEvent": TaskStatusUpdateEvent,
    "TaskArtifactUpdateEvent": TaskArtifactUpdateEvent,
    "Task": Task,
    "Message": Message,
    "SendMessageResponse": SendMessageResponse,
}


class Mq9A2AAgent:
    """
    A2A agent over mq9 — acts as both server and client.

    Usage (agent mode)::

        agent = Mq9A2AAgent(server="nats://demo.robustmq.com:4222")

        @agent.on_message
        async def handle(context: RequestContext, event_queue: EventQueue) -> None:
            ...

        card = AgentCard(name="translator", description="...", version="1.0.0")
        await agent.connect()
        await agent.register(card)   # blocks until stop() or Ctrl+C

    Usage (client mode)::

        async with Mq9A2AAgent(server="nats://demo.robustmq.com:4222") as agent:
            agents = await agent.discover("translator")
            async for event in await agent.send_message(agents[0], request):
                ...
    """

    def __init__(
        self,
        *,
        server: str,
        mailbox_ttl: int = 0,
        request_timeout: float = _DEFAULT_TIMEOUT,
    ) -> None:
        self._server = server
        self._mailbox_ttl = mailbox_ttl
        self._timeout = request_timeout

        self._executor: _FnAgentExecutor | None = None
        self._mq9: Mq9Client | None = None
        self._mailbox: str | None = None
        self._agent_name: str | None = None
        self._task_store: Mq9A2ATaskStore | None = None
        self._running = False
        self._consumer = None
        self._heartbeat_task: asyncio.Task | None = None

    def on_message(self, fn: HandlerFn) -> HandlerFn:
        """Decorator: register the async message handler."""
        self._executor = _FnAgentExecutor(fn)
        return fn

    # ------------------------------------------------------------------ connection

    async def connect(self) -> None:
        """Connect to the broker. Required before any operation."""
        self._mq9 = Mq9Client(self._server)
        await self._mq9.connect()

    async def close(self) -> None:
        """Disconnect from the broker."""
        if self._mq9:
            await self._mq9.close()

    async def __aenter__(self) -> "Mq9A2AAgent":
        await self.connect()
        return self

    async def __aexit__(self, *_args) -> None:
        await self.close()

    # ------------------------------------------------------------------ agent registration

    async def register(self, agent_card: AgentCard) -> None:
        """
        Register as an A2A agent and start serving incoming tasks.

        Creates the agent mailbox and task-store mailbox, registers the
        AgentCard in the mq9 registry, starts the heartbeat loop, then
        blocks until stop() is called or a KeyboardInterrupt is received.

        Call connect() before calling register().
        """
        mq9 = self._mq9_or_raise()
        name = agent_card.name
        self._agent_name = name

        self._mailbox = await mq9.mailbox_create(name=name, ttl=self._mailbox_ttl)
        _logger.info("[mq9.a2a] mailbox=%s", self._mailbox)

        tasks_mailbox = f"{name}.tasks"
        try:
            await mq9.mailbox_create(name=tasks_mailbox, ttl=self._mailbox_ttl)
        except Exception:
            pass  # already exists
        self._task_store = Mq9A2ATaskStore(mq9, tasks_mailbox)
        self._task_store.mark_ready()

        await mq9.agent_register({
            "name": name,
            "mailbox": self._mailbox,
            "payload": agent_card.description,
            "agent_card": json_format.MessageToDict(agent_card),
        })
        _logger.info("[mq9.a2a] registered agent=%s", name)

        self._heartbeat_task = asyncio.ensure_future(self._heartbeat_loop())
        self._consumer = await mq9.consume(
            self._mailbox,
            self._dispatch,
            group_name=f"{name}.workers",
            deliver="earliest",
            auto_ack=True,
        )

        self._running = True
        _logger.info("[mq9.a2a] running — waiting for tasks…")
        try:
            while self._running:
                await asyncio.sleep(1)
        except (KeyboardInterrupt, asyncio.CancelledError):
            pass
        finally:
            await self.stop()

    async def stop(self) -> None:
        """Gracefully unregister and disconnect."""
        self._running = False
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except (asyncio.CancelledError, Exception):
                pass
        if self._consumer:
            await self._consumer.stop()
        if self._mq9 and self._mailbox:
            try:
                await self._mq9.agent_unregister(self._mailbox)
            except Exception:
                pass
            await self._mq9.close()

    # ------------------------------------------------------------------ discovery

    async def discover(
        self,
        query: str | None = None,
        *,
        semantic: bool = True,
        limit: int = 10,
    ) -> list[dict]:
        """
        Discover other agents from the mq9 registry.

        Pass a natural-language query for semantic search, or None to list all.
        Returns list of agent info dicts (keys: name, mailbox, agent_card, …).
        """
        mq9 = self._mq9_or_raise()
        if query is None:
            return await mq9.agent_discover(limit=limit)
        if semantic:
            return await mq9.agent_discover(semantic=query, limit=limit)
        return await mq9.agent_discover(text=query, limit=limit)

    # ------------------------------------------------------------------ outbound task ops

    async def send_message(
        self,
        agent: dict | str,
        request: SendMessageRequest,
        *,
        timeout: float | None = None,
    ) -> AsyncIterator:
        """
        Send an A2A SendMessageRequest to another agent and stream back events.

        agent: agent info dict from discover() (needs 'mailbox' key) or raw
               mailbox address string.

        Returns an async iterator that yields A2A event objects
        (Task, TaskStatusUpdateEvent, TaskArtifactUpdateEvent).
        """
        mq9 = self._mq9_or_raise()
        mailbox = _mailbox_of(agent)
        t = timeout or self._timeout
        callback = await mq9.mailbox_create(ttl=int(t) + 10)
        payload = json_format.MessageToJson(request).encode()
        await mq9._request_with_headers(
            f"$mq9.AI.MSG.SEND.{mailbox}", payload, {_HEADER_REPLY_TO: callback}
        )
        return self._stream_events(mq9, callback, t)

    async def get_task(self, agent: dict | str, task_id: str) -> Task | None:
        """Retrieve current state of a task by ID."""
        mq9 = self._mq9_or_raise()
        mailbox = _mailbox_of(agent)
        callback = await mq9.mailbox_create(ttl=30)
        payload = json_format.MessageToJson(GetTaskRequest(task_id=task_id)).encode()
        await mq9._request_with_headers(
            f"$mq9.AI.MSG.SEND.{mailbox}", payload,
            {_HEADER_METHOD: _METHOD_GET_TASK, _HEADER_REPLY_TO: callback},
        )
        msgs = await mq9.fetch(callback, deliver="earliest", num_msgs=1, max_wait_ms=5000)
        if not msgs:
            return None
        try:
            return json_format.Parse(msgs[0].payload, Task())
        except Exception:
            return None

    async def list_tasks(
        self, agent: dict | str, *, page_size: int = 100
    ) -> list[Task]:
        """List all tasks stored by an agent."""
        mq9 = self._mq9_or_raise()
        mailbox = _mailbox_of(agent)
        callback = await mq9.mailbox_create(ttl=30)
        payload = json_format.MessageToJson(
            ListTasksRequest(page_size=page_size)
        ).encode()
        await mq9._request_with_headers(
            f"$mq9.AI.MSG.SEND.{mailbox}", payload,
            {_HEADER_METHOD: _METHOD_LIST_TASKS, _HEADER_REPLY_TO: callback},
        )
        msgs = await mq9.fetch(callback, deliver="earliest", num_msgs=1, max_wait_ms=5000)
        if not msgs:
            return []
        try:
            resp = json_format.Parse(msgs[0].payload, ListTasksResponse())
            return list(resp.tasks)
        except Exception:
            return []

    async def cancel_task(
        self, agent: dict | str, task_id: str
    ) -> Task | None:
        """Request cancellation of a running task (sent at critical priority)."""
        mq9 = self._mq9_or_raise()
        mailbox = _mailbox_of(agent)
        callback = await mq9.mailbox_create(ttl=30)
        payload = json_format.MessageToJson(
            CancelTaskRequest(task_id=task_id)
        ).encode()
        await mq9._request_with_headers(
            f"$mq9.AI.MSG.SEND.{mailbox}", payload,
            {_HEADER_METHOD: _METHOD_CANCEL, _HEADER_REPLY_TO: callback},
        )
        msgs = await mq9.fetch(callback, deliver="earliest", num_msgs=1, max_wait_ms=5000)
        if not msgs:
            return None
        try:
            return json_format.Parse(msgs[0].payload, Task())
        except Exception:
            return None

    # ------------------------------------------------------------------ dispatch (server side)

    async def _dispatch(self, msg) -> None:
        headers = msg.headers or {}
        method = headers.get(_HEADER_METHOD, _METHOD_SEND)
        reply_to = headers.get(_HEADER_REPLY_TO)

        try:
            if method == _METHOD_GET_TASK:
                await self._handle_get_task(msg.payload, reply_to)
            elif method == _METHOD_LIST_TASKS:
                await self._handle_list_tasks(msg.payload, reply_to)
            elif method == _METHOD_CANCEL:
                await self._handle_cancel_task(msg.payload, reply_to)
            else:
                await self._handle_send_message(msg, reply_to)
        except Exception as exc:
            _logger.error("[mq9.a2a] dispatch error method=%s: %s", method, exc)

    async def _handle_send_message(self, msg, reply_to: str | None) -> None:
        if self._executor is None:
            _logger.warning("[mq9.a2a] no handler registered, dropping msg_id=%s", msg.msg_id)
            return
        try:
            request = json_format.Parse(msg.payload, SendMessageRequest())
        except Exception as exc:
            _logger.error("[mq9.a2a] bad SendMessageRequest: %s", exc)
            return

        event_queue = _ForwardingEventQueue(mq9_client=self._mq9, reply_to=reply_to)
        context = RequestContext(
            request=request,
            task_id=None,
            context_id=None,
            task_store=self._task_store,
        )
        try:
            await self._executor.execute(context, event_queue)
        except Exception as exc:
            _logger.error("[mq9.a2a] executor error msg_id=%s: %s", msg.msg_id, exc)
            if reply_to:
                await _send_event(
                    self._mq9, reply_to,
                    TaskStatusUpdateEvent(status=TaskStatus(state=TaskState.TASK_STATE_FAILED)),
                    last=True,
                )
        finally:
            await event_queue.flush_last()

    async def _handle_get_task(self, payload: bytes, reply_to: str | None) -> None:
        if not reply_to or not self._task_store:
            return
        try:
            req = json_format.Parse(payload, GetTaskRequest())
            task = await self._task_store.get(req.task_id)
            await self._mq9.send(reply_to, json_format.MessageToJson(task if task else Task()).encode())
        except Exception as exc:
            _logger.warning("[mq9.a2a] GetTask error: %s", exc)

    async def _handle_list_tasks(self, payload: bytes, reply_to: str | None) -> None:
        if not reply_to or not self._task_store:
            return
        try:
            req = json_format.Parse(payload, ListTasksRequest())
            resp = await self._task_store.list(req)
            await self._mq9.send(reply_to, json_format.MessageToJson(resp).encode())
        except Exception as exc:
            _logger.warning("[mq9.a2a] ListTasks error: %s", exc)

    async def _handle_cancel_task(self, payload: bytes, reply_to: str | None) -> None:
        if not self._task_store:
            return
        try:
            req = json_format.Parse(payload, CancelTaskRequest())
            task = await self._task_store.get(req.task_id)
            if task:
                task.status.CopyFrom(TaskStatus(state=TaskState.TASK_STATE_CANCELED))
                await self._task_store.save(task)
            if self._mailbox:
                await _send_event(
                    self._mq9, self._mailbox,
                    TaskStatusUpdateEvent(
                        task_id=req.task_id,
                        status=TaskStatus(state=TaskState.TASK_STATE_CANCELED),
                    ),
                    last=False, priority=Priority.CRITICAL,
                )
            if reply_to and task:
                await self._mq9.send(reply_to, json_format.MessageToJson(task).encode())
        except Exception as exc:
            _logger.warning("[mq9.a2a] CancelTask error: %s", exc)

    # ------------------------------------------------------------------ internals

    async def _heartbeat_loop(self) -> None:
        while True:
            await asyncio.sleep(_HEARTBEAT_INTERVAL)
            try:
                if self._mq9 and self._mailbox and self._agent_name:
                    await self._mq9.agent_report({
                        "name": self._agent_name,
                        "mailbox": self._mailbox,
                        "report_info": (
                            f"running, processed="
                            f"{self._consumer.processed_count if self._consumer else 0}"
                        ),
                    })
            except Exception as exc:
                _logger.warning("[mq9.a2a] heartbeat error: %s", exc)

    async def _stream_events(
        self, mq9: Mq9Client, callback: str, timeout: float
    ) -> AsyncIterator:
        deadline = asyncio.get_event_loop().time() + timeout
        while True:
            remaining = deadline - asyncio.get_event_loop().time()
            if remaining <= 0:
                _logger.warning("[mq9.a2a] stream timeout on %s", callback)
                return
            msgs = await mq9.fetch(
                callback,
                deliver="earliest",
                num_msgs=20,
                max_wait_ms=min(int(remaining * 1000), 2000),
            )
            for msg in msgs:
                headers = msg.headers or {}
                event_cls = _EVENT_TYPES.get(headers.get(_HEADER_TYPE, ""))
                if event_cls:
                    try:
                        yield json_format.Parse(msg.payload, event_cls())
                    except Exception as exc:
                        _logger.warning("[mq9.a2a] parse event error: %s", exc)
                if headers.get(_HEADER_LAST) == "true":
                    return

    def _mq9_or_raise(self) -> Mq9Client:
        if self._mq9 is None:
            raise RuntimeError("Not connected. Call connect() first.")
        return self._mq9


# ── ForwardingEventQueue ───────────────────────────────────────────────────────

class _ForwardingEventQueue(InMemoryEventQueue):
    def __init__(self, mq9_client: Mq9Client, reply_to: str | None) -> None:
        super().__init__()
        self._mq9 = mq9_client
        self._reply_to = reply_to
        self._closed = False

    async def enqueue_event(self, event) -> None:
        await super().enqueue_event(event)
        if self._reply_to and self._mq9:
            await _send_event(self._mq9, self._reply_to, event, last=False)

    async def flush_last(self) -> None:
        if self._reply_to and self._mq9 and not self._closed:
            self._closed = True
            await _send_event(
                self._mq9, self._reply_to,
                TaskStatusUpdateEvent(status=TaskStatus(state=TaskState.TASK_STATE_COMPLETED)),
                last=True,
            )


# ── helpers ────────────────────────────────────────────────────────────────────

def _mailbox_of(agent: dict | str) -> str:
    mailbox = agent if isinstance(agent, str) else agent.get("mailbox", "")
    if not mailbox:
        raise ValueError("agent must be a mailbox string or dict with 'mailbox' key")
    return mailbox


async def _send_event(
    mq9: Mq9Client,
    reply_to: str,
    event,
    *,
    last: bool,
    priority: Priority = Priority.NORMAL,
) -> None:
    payload = json_format.MessageToJson(event).encode()
    headers: dict[str, str] = {_HEADER_TYPE: type(event).__name__}
    if last:
        headers[_HEADER_LAST] = "true"
    if priority != Priority.NORMAL:
        headers["mq9-priority"] = priority.value
    try:
        await mq9._request_with_headers(
            f"$mq9.AI.MSG.SEND.{reply_to}", payload, headers
        )
    except Exception as exc:
        _logger.warning("[mq9.a2a] send event to %s failed: %s", reply_to, exc)
