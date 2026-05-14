"""mq9 client implementation."""

from __future__ import annotations

import asyncio
import base64
import json
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Awaitable, Callable

import nats
import nats.aio.client

_SUBJECT_PREFIX = "$mq9.AI"
_SUBJECT_MAILBOX_CREATE = f"{_SUBJECT_PREFIX}.MAILBOX.CREATE"
_SUBJECT_MSG_SEND = f"{_SUBJECT_PREFIX}.MSG.SEND.{{mail_address}}"
_SUBJECT_MSG_FETCH = f"{_SUBJECT_PREFIX}.MSG.FETCH.{{mail_address}}"
_SUBJECT_MSG_ACK = f"{_SUBJECT_PREFIX}.MSG.ACK.{{mail_address}}"
_SUBJECT_MSG_QUERY = f"{_SUBJECT_PREFIX}.MSG.QUERY.{{mail_address}}"
_SUBJECT_MSG_DELETE = f"{_SUBJECT_PREFIX}.MSG.DELETE.{{mail_address}}.{{msg_id}}"
_SUBJECT_AGENT_REGISTER = f"{_SUBJECT_PREFIX}.AGENT.REGISTER"
_SUBJECT_AGENT_UNREGISTER = f"{_SUBJECT_PREFIX}.AGENT.UNREGISTER"
_SUBJECT_AGENT_REPORT = f"{_SUBJECT_PREFIX}.AGENT.REPORT"
_SUBJECT_AGENT_DISCOVER = f"{_SUBJECT_PREFIX}.AGENT.DISCOVER"

_logger = logging.getLogger(__name__)


class Priority(str, Enum):
    NORMAL = "normal"
    URGENT = "urgent"
    CRITICAL = "critical"


@dataclass
class Message:
    msg_id: int
    payload: bytes
    priority: Priority
    create_time: int


class Consumer:
    """Handle to a background consume loop."""

    def __init__(self, task: asyncio.Task) -> None:
        self._task = task
        self.is_running: bool = True
        self.processed_count: int = 0

    async def stop(self) -> None:
        self._task.cancel()
        try:
            await self._task
        except (asyncio.CancelledError, Exception):
            pass
        self.is_running = False


class Mq9Error(Exception):
    pass


def _encode(obj: dict | str | bytes) -> bytes:
    if isinstance(obj, bytes):
        return obj
    if isinstance(obj, str):
        return obj.encode()
    return json.dumps(obj).encode()


def _decode_response(data: bytes) -> dict:
    resp = json.loads(data)
    if resp.get("error"):
        raise Mq9Error(resp["error"])
    return resp


def _parse_messages(raw: list[dict]) -> list[Message]:
    messages: list[Message] = []
    for item in raw:
        payload = base64.b64decode(item["payload"]) if isinstance(item["payload"], str) else item["payload"]
        messages.append(
            Message(
                msg_id=item["msg_id"],
                payload=payload,
                priority=Priority(item.get("priority", Priority.NORMAL)),
                create_time=item["create_time"],
            )
        )
    return messages


class Mq9Client:
    """Async client for the mq9 NATS-based Agent messaging broker."""

    def __init__(
        self,
        server: str,
        *,
        request_timeout: float = 5.0,
        reconnect_attempts: int = 5,
        reconnect_delay: float = 2.0,
    ) -> None:
        self._server = server
        self._request_timeout = request_timeout
        self._reconnect_attempts = reconnect_attempts
        self._reconnect_delay = reconnect_delay
        self._nc: nats.aio.client.Client | None = None

    async def connect(self) -> None:
        self._nc = await nats.connect(
            self._server,
            max_reconnect_attempts=self._reconnect_attempts,
            reconnect_time_wait=self._reconnect_delay,
        )

    async def close(self) -> None:
        if self._nc and not self._nc.is_closed:
            await self._nc.drain()

    async def __aenter__(self) -> "Mq9Client":
        await self.connect()
        return self

    async def __aexit__(self, *args) -> None:
        await self.close()

    def _nc_or_raise(self) -> nats.aio.client.Client:
        if self._nc is None:
            raise Mq9Error("Client is not connected. Call connect() first.")
        return self._nc

    async def _request(self, subject: str, payload: bytes) -> dict:
        nc = self._nc_or_raise()
        msg = await nc.request(subject, payload, timeout=self._request_timeout)
        return _decode_response(msg.data)

    async def _request_with_headers(self, subject: str, payload: bytes, headers: dict[str, str]) -> dict:
        nc = self._nc_or_raise()
        # nats-py publish with headers; use request pattern via reply inbox
        reply_inbox = nc.new_inbox()
        future: asyncio.Future[nats.aio.client.Msg] = asyncio.get_event_loop().create_future()

        async def _handler(msg: nats.aio.client.Msg) -> None:
            if not future.done():
                future.set_result(msg)

        sub = await nc.subscribe(reply_inbox, cb=_handler)
        try:
            await nc.publish(subject, payload, reply=reply_inbox, headers=headers)
            msg = await asyncio.wait_for(future, timeout=self._request_timeout)
        finally:
            await sub.unsubscribe()
        return _decode_response(msg.data)

    # ------------------------------------------------------------------ Mailbox

    async def mailbox_create(self, *, name: str | None = None, ttl: int = 0) -> str:
        body: dict = {"ttl": ttl}
        if name is not None:
            body["name"] = name
        resp = await self._request(_SUBJECT_MAILBOX_CREATE, _encode(body))
        return resp["mail_address"]

    # ------------------------------------------------------------------ Messaging

    async def send(
        self,
        mail_address: str,
        payload: bytes | str | dict,
        *,
        priority: Priority = Priority.NORMAL,
        key: str | None = None,
        delay: int | None = None,
        ttl: int | None = None,
        tags: list[str] | None = None,
    ) -> int:
        subject = _SUBJECT_MSG_SEND.format(mail_address=mail_address)
        data = _encode(payload)
        headers: dict[str, str] = {}
        # Only include priority header when not NORMAL, but spec says all optional —
        # include it always for clarity so receivers always know the priority.
        if priority != Priority.NORMAL:
            headers["mq9-priority"] = priority.value
        if key is not None:
            headers["mq9-key"] = key
        if delay is not None:
            headers["mq9-delay"] = str(delay)
        if ttl is not None:
            headers["mq9-ttl"] = str(ttl)
        if tags:
            headers["mq9-tags"] = ",".join(tags)

        if headers:
            resp = await self._request_with_headers(subject, data, headers)
        else:
            resp = await self._request(subject, data)
        return resp["msg_id"]

    async def fetch(
        self,
        mail_address: str,
        *,
        group_name: str | None = None,
        deliver: str = "latest",
        from_time: int | None = None,
        from_id: int | None = None,
        force_deliver: bool = False,
        num_msgs: int = 100,
        max_wait_ms: int = 500,
    ) -> list[Message]:
        subject = _SUBJECT_MSG_FETCH.format(mail_address=mail_address)
        body: dict = {
            "deliver": deliver,
            "force_deliver": force_deliver,
            "config": {
                "num_msgs": num_msgs,
                "max_wait_ms": max_wait_ms,
            },
        }
        if group_name is not None:
            body["group_name"] = group_name
        if from_time is not None:
            body["from_time"] = from_time
        if from_id is not None:
            body["from_id"] = from_id
        resp = await self._request(subject, _encode(body))
        return _parse_messages(resp.get("messages") or [])

    async def ack(self, mail_address: str, group_name: str, msg_id: int) -> None:
        subject = _SUBJECT_MSG_ACK.format(mail_address=mail_address)
        body = {
            "group_name": group_name,
            "mail_address": mail_address,
            "msg_id": msg_id,
        }
        await self._request(subject, _encode(body))

    async def consume(
        self,
        mail_address: str,
        handler: Callable[[Message], Awaitable[None]],
        *,
        group_name: str | None = None,
        deliver: str = "latest",
        num_msgs: int = 10,
        max_wait_ms: int = 500,
        auto_ack: bool = True,
        error_handler: Callable[[Message, Exception], Awaitable[None]] | None = None,
    ) -> Consumer:
        consumer: Consumer

        async def _loop() -> None:
            while True:
                try:
                    messages = await self.fetch(
                        mail_address,
                        group_name=group_name,
                        deliver=deliver,
                        num_msgs=num_msgs,
                        max_wait_ms=max_wait_ms,
                    )
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    _logger.error("mq9 fetch error: %s", exc)
                    await asyncio.sleep(1)
                    continue

                for msg in messages:
                    try:
                        await handler(msg)
                        if auto_ack and group_name is not None:
                            await self.ack(mail_address, group_name, msg.msg_id)
                        consumer.processed_count += 1
                    except asyncio.CancelledError:
                        raise
                    except Exception as exc:
                        if error_handler is not None:
                            try:
                                await error_handler(msg, exc)
                            except Exception:
                                pass
                        else:
                            _logger.error("mq9 handler error for msg_id=%s: %s", msg.msg_id, exc)

        task = asyncio.ensure_future(_loop())
        consumer = Consumer(task)
        return consumer

    async def query(
        self,
        mail_address: str,
        *,
        key: str | None = None,
        limit: int | None = None,
        since: int | None = None,
    ) -> list[Message]:
        subject = _SUBJECT_MSG_QUERY.format(mail_address=mail_address)
        body: dict = {}
        if key is not None:
            body["key"] = key
        if limit is not None:
            body["limit"] = limit
        if since is not None:
            body["since"] = since
        resp = await self._request(subject, _encode(body))
        return _parse_messages(resp.get("messages") or [])

    async def delete(self, mail_address: str, msg_id: int) -> None:
        subject = _SUBJECT_MSG_DELETE.format(mail_address=mail_address, msg_id=msg_id)
        await self._request(subject, b'""')

    # ------------------------------------------------------------------ Agent management

    async def agent_register(self, agent_card: dict) -> None:
        await self._request(_SUBJECT_AGENT_REGISTER, _encode(agent_card))

    async def agent_unregister(self, mailbox: str) -> None:
        await self._request(_SUBJECT_AGENT_UNREGISTER, _encode({"mailbox": mailbox}))

    async def agent_report(self, report: dict) -> None:
        await self._request(_SUBJECT_AGENT_REPORT, _encode(report))

    async def agent_discover(
        self,
        *,
        text: str | None = None,
        semantic: str | None = None,
        limit: int = 20,
        page: int = 1,
    ) -> list[dict]:
        body: dict = {"limit": limit, "page": page}
        if text is not None:
            body["text"] = text
        if semantic is not None:
            body["semantic"] = semantic
        resp = await self._request(_SUBJECT_AGENT_DISCOVER, _encode(body))
        return resp.get("agents") or []
