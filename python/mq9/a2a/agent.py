"""Mq9A2AAgent — A2A agent that uses mq9 as its transport.

Each agent is both a server (registers and receives tasks) and a client
(discovers and sends tasks to other agents).

Usage::

    agent = Mq9A2AAgent()  # uses public demo broker by default

    @agent.on_message
    async def handle(context, event_queue): ...

    card = AgentCard(name="my-agent", description="...", ...)
    await agent.register(card)   # connects, registers, blocks until unregister()
"""

from __future__ import annotations

import asyncio
import logging

from a2a.server.agent_execution import RequestContext
from a2a.server.events import InMemoryEventQueue
from a2a.types.a2a_pb2 import (
    AgentCard,
    CancelTaskRequest,
    GetTaskRequest,
    ListTasksRequest,
    ListTasksResponse,
    SendMessageRequest,
    Task,
    TaskState,
    TaskStatus,
    TaskStatusUpdateEvent,
)
from google.protobuf import json_format

from mq9.client import Mq9Client, Priority
from ._executor import _FnAgentExecutor, HandlerFn
from ._task_store import Mq9A2ATaskStore

_logger = logging.getLogger(__name__)

# How often the agent sends a heartbeat to keep its registry entry alive (seconds).
_HEARTBEAT_INTERVAL = 30

# mq9 message headers used by the A2A protocol layer.
_HEADER_METHOD   = "mq9-a2a-method"   # which RPC method this message represents
_HEADER_REPLY_TO = "mq9-reply-to"     # callback mailbox address for responses
_HEADER_LAST     = "mq9-a2a-last"     # "true" on the final event in a stream
_HEADER_TYPE     = "mq9-a2a-type"     # protobuf message type name for deserialization
_HEADER_TASK_ID  = "mq9-a2a-task-id"  # task_id for routing reply events back to the caller

# RPC method names carried in _HEADER_METHOD.
# Absence of the header means SendMessage (the default / most common case).
_METHOD_SEND       = "SendMessage"
_METHOD_GET_TASK   = "GetTask"
_METHOD_LIST_TASKS = "ListTasks"
_METHOD_CANCEL     = "CancelTask"

_DEFAULT_TIMEOUT = 60.0
# Public broker for quick testing — no setup required.
_DEFAULT_SERVER  = "nats://demo.robustmq.com:4222"


class Mq9A2AAgent:
    """A2A agent over mq9 — registers, receives tasks, and sends tasks to others."""

    def __init__(
        self,
        *,
        server: str = _DEFAULT_SERVER,
        request_timeout: float = _DEFAULT_TIMEOUT,
    ) -> None:
        self._server = server
        self._timeout = request_timeout

        self._executor: _FnAgentExecutor | None = None
        self._mq9: Mq9Client | None = None
        self._mailbox: str | None = None        # main inbox address, set after create_mailbox()
        self._agent_name: str | None = None
        self._agent_card: AgentCard | None = None
        self._task_store: Mq9A2ATaskStore | None = None
        self._consumer = None
        self._heartbeat_task: asyncio.Task | None = None

        # consumer options — set via @on_message(group_name=...) decorator
        self._group_name: str | None = None
        self._deliver: str = "earliest"
        self._num_msgs: int = 10
        self._max_wait_ms: int = 500

    def on_message(
        self,
        fn: HandlerFn | None = None,
        *,
        group_name: str | None = None,
        deliver: str = "earliest",
        num_msgs: int = 10,
        max_wait_ms: int = 500,
    ):
        """Decorator: register the async message handler.

        Can be used plain or with consumer options::

            @agent.on_message
            async def handle(context, event_queue): ...

            @agent.on_message(group_name="my-group", num_msgs=20)
            async def handle(context, event_queue): ...
        """
        def _register(f: HandlerFn) -> HandlerFn:
            self._executor = _FnAgentExecutor(f)
            self._group_name = group_name
            self._deliver = deliver
            self._num_msgs = num_msgs
            self._max_wait_ms = max_wait_ms
            return f

        if fn is not None:
            # used as @agent.on_message without call — fn is the decorated function
            return _register(fn)
        # used as @agent.on_message(...) with arguments — return the actual decorator
        return _register

    # ------------------------------------------------------------------ lifecycle

    async def connect(self) -> None:
        """Connect to the broker."""
        self._mq9 = Mq9Client(self._server)
        await self._mq9.connect()

    async def close(self) -> None:
        """Disconnect from the broker."""
        if self._mq9:
            await self._mq9.close()

    async def create_mailbox(self, name: str, *, ttl: int = 0) -> str:
        """Create a mailbox with the given name and start the consumer.

        Call connect() first. Returns the mailbox address immediately.
        The mailbox can receive messages right away — no need to register
        in the discovery registry unless you want to be discoverable.

        Call register(agent_card) afterwards to publish identity to the registry.
        """
        mq9 = self._mq9_or_raise()
        self._agent_name = name

        # Create the main inbox. The name becomes the stable mailbox address
        # that other agents use to send tasks to this agent.
        self._mailbox = await mq9.mailbox_create(name=name, ttl=ttl)
        _logger.info("[mq9.a2a] mailbox=%s", self._mailbox)

        # Create a separate mailbox for task persistence. Storing tasks under
        # "{name}.tasks" with key-based deduplication lets the agent recover its last-known
        # task states after a restart without reprocessing the entire inbox.
        tasks_mailbox = f"{name}.tasks"
        try:
            await mq9.mailbox_create(name=tasks_mailbox, ttl=ttl)
        except Exception:
            pass  # already exists on restart — that's fine
        self._task_store = Mq9A2ATaskStore(mq9, tasks_mailbox)
        self._task_store.mark_ready()

        # Start consuming the main inbox. auto_ack=True so messages are acknowledged
        # immediately on receipt; the handler is responsible for durability via
        # the task store, not via the consumer offset.
        group = self._group_name or f"{name}.workers"
        self._consumer = await mq9.consume(
            self._mailbox,
            self._dispatch,
            group_name=group,
            deliver=self._deliver,
            num_msgs=self._num_msgs,
            max_wait_ms=self._max_wait_ms,
            auto_ack=True,
        )

        _logger.info("[mq9.a2a] mailbox ready — %s", self._mailbox)
        return self._mailbox

    async def register(self, agent_card: AgentCard) -> None:
        """Publish agent identity to the registry so others can discover it.

        Call create_mailbox() first. Once registered, the agent appears in
        discover() results. A heartbeat loop runs in the background to keep
        the registry entry alive.
        """
        mq9 = self._mq9_or_raise()
        if not self._mailbox:
            raise RuntimeError("Call create_mailbox() before register().")

        self._agent_card = agent_card

        # Publish agent identity to the registry so other agents can discover
        # this one by name or semantic description via agent.discover().
        await mq9.agent_register({
            "name": self._agent_name,
            "mailbox": self._mailbox,
            "payload": agent_card.description,
            "agent_card": json_format.MessageToDict(agent_card),
        })
        _logger.info("[mq9.a2a] registered agent=%s", self._agent_name)

        # Heartbeat loop keeps the registry entry alive; registry entries expire
        # if not refreshed, so we report periodically even with no traffic.
        self._heartbeat_task = asyncio.ensure_future(self._heartbeat_loop())

    async def unregister(self) -> None:
        """Remove this agent from the registry.

        Other agents will no longer discover it, but the connection stays open
        and the consumer keeps running so queued messages can still be processed.
        Call close() when ready to fully stop.
        """
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except (asyncio.CancelledError, Exception):
                pass
        if self._mq9 and self._mailbox:
            try:
                await self._mq9.agent_unregister(self._mailbox)
            except Exception:
                pass

    async def close(self) -> None:
        """Stop consuming messages and disconnect from the broker."""
        if self._consumer:
            await self._consumer.stop()
        if self._mq9:
            await self._mq9.close()

    # ------------------------------------------------------------------ discovery

    async def discover(
        self,
        query: str | None = None,
        *,
        semantic: bool = True,
        limit: int = 10,
    ) -> list[dict]:
        """Discover other agents from the mq9 registry.

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
        mail_address: dict | str,
        request: SendMessageRequest,
        *,
        reply_to: str | None = None,
    ) -> int:
        """Send an A2A SendMessageRequest to another agent.

        mail_address: agent info dict from discover() (needs 'mailbox' key) or
                      raw mailbox address string.
        reply_to: your own mailbox address. The executing agent streams result
                  events back here. Each event carries a task_id (generated by
                  the executor) readable as context.task_id in @on_message.

        Returns msg_id assigned by the broker, confirming the message was queued.
        """
        mq9 = self._mq9_or_raise()
        mailbox = _mailbox_of(mail_address)
        payload = json_format.MessageToJson(request).encode()
        if reply_to:
            resp = await mq9._request_with_headers(
                f"$mq9.AI.MSG.SEND.{mailbox}",
                payload,
                {_HEADER_REPLY_TO: reply_to},
            )
            return resp.get("msg_id", 0)
        return await mq9.send(mailbox, payload)

    async def get_task(self, mail_address: dict | str, task_id: str) -> Task | None:
        """Retrieve current state of a task stored on another agent."""
        mq9 = self._mq9_or_raise()
        mailbox = _mailbox_of(mail_address)
        # Create a temporary one-shot mailbox to receive the reply.
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
        self, mail_address: dict | str, *, page_size: int = 100
    ) -> list[Task]:
        """List all tasks stored by another agent."""
        mq9 = self._mq9_or_raise()
        mailbox = _mailbox_of(mail_address)
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
        self, mail_address: dict | str, task_id: str
    ) -> Task | None:
        """Request cancellation of a running task on another agent."""
        mq9 = self._mq9_or_raise()
        mailbox = _mailbox_of(mail_address)
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
        """Route an incoming mq9 message to the correct handler by method header."""
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
        """Execute the user's @on_message handler and forward events to reply_to."""
        if self._executor is None:
            _logger.warning("[mq9.a2a] no handler registered, dropping msg_id=%s", msg.msg_id)
            return
        try:
            request = json_format.Parse(msg.payload, SendMessageRequest())
        except Exception as exc:
            _logger.error("[mq9.a2a] bad SendMessageRequest: %s", exc)
            return

        # Read the task_id the sender stamped on this request so every reply
        # event carries it back — the sender's _dispatch uses it to route replies
        # to the correct pending queue rather than the @on_message handler.
        task_id = (msg.headers or {}).get(_HEADER_TASK_ID)
        event_queue = _ForwardingEventQueue(mq9_client=self._mq9, reply_to=reply_to, task_id=task_id)
        context = RequestContext(
            request=request,
            task_id=task_id,        # handler can read context.task_id for status/artifact events
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
            # Always send the terminal "last" marker so the sender knows the
            # stream is complete, even if the handler completed without errors.
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
            # Deliver a CANCELED status update to the agent's own inbox so any
            # in-progress handler can detect cancellation and stop early.
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

    def _mq9_or_raise(self) -> Mq9Client:
        if self._mq9 is None:
            raise RuntimeError("Not connected — call connect() first.")
        return self._mq9


# ── ForwardingEventQueue ───────────────────────────────────────────────────────

class _ForwardingEventQueue(InMemoryEventQueue):
    """Event queue that forwards each event to a reply-to mailbox as it is enqueued.

    Each forwarded event carries the original task_id in its header so the
    receiver's _dispatch can route it to the correct pending queue rather than
    the @on_message handler.
    """

    def __init__(self, mq9_client: Mq9Client, reply_to: str | None, task_id: str | None = None) -> None:
        super().__init__()
        self._mq9 = mq9_client
        self._reply_to = reply_to
        self._task_id = task_id
        self._closed = False  # guard against double flush_last

    async def enqueue_event(self, event) -> None:
        await super().enqueue_event(event)
        if self._reply_to and self._mq9:
            await _send_event(self._mq9, self._reply_to, event, last=False, task_id=self._task_id)

    async def flush_last(self) -> None:
        """Send the terminal marker so the receiver knows the stream is done."""
        if self._reply_to and self._mq9 and not self._closed:
            self._closed = True
            await _send_event(
                self._mq9, self._reply_to,
                TaskStatusUpdateEvent(status=TaskStatus(state=TaskState.TASK_STATE_COMPLETED)),
                last=True,
                task_id=self._task_id,
            )


# ── helpers ────────────────────────────────────────────────────────────────────

def _mailbox_of(agent: dict | str) -> str:
    """Extract the mailbox address from an agent dict or pass through a string."""
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
    task_id: str | None = None,
    priority: Priority = Priority.NORMAL,
) -> None:
    """Serialize a protobuf event and deliver it to reply_to with A2A headers."""
    payload = json_format.MessageToJson(event).encode()
    headers: dict[str, str] = {_HEADER_TYPE: type(event).__name__}
    if last:
        headers[_HEADER_LAST] = "true"
    if task_id:
        # Stamp task_id so the receiver's _dispatch routes this event to the
        # correct pending queue instead of the @on_message handler.
        headers[_HEADER_TASK_ID] = task_id
    if priority != Priority.NORMAL:
        headers["mq9-priority"] = priority.value
    try:
        await mq9._request_with_headers(
            f"$mq9.AI.MSG.SEND.{reply_to}", payload, headers
        )
    except Exception as exc:
        _logger.warning("[mq9.a2a] send event to %s failed: %s", reply_to, exc)
