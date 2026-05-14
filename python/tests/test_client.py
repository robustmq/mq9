"""Tests for mq9.client — all NATS I/O is mocked."""

from __future__ import annotations

import asyncio
import base64
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mq9 import Consumer, Message, Mq9Client, Mq9Error, Priority


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_response(data: dict) -> MagicMock:
    msg = MagicMock()
    msg.data = json.dumps(data).encode()
    return msg


def _make_nc(request_side_effect=None, *, is_closed: bool = False) -> MagicMock:
    nc = MagicMock()
    nc.is_closed = is_closed
    nc.drain = AsyncMock()
    nc.publish = AsyncMock()
    if request_side_effect is not None:
        nc.request = AsyncMock(side_effect=request_side_effect)
    else:
        nc.request = AsyncMock()
    nc.new_inbox = MagicMock(return_value="_INBOX.test")
    nc.subscribe = AsyncMock()
    return nc


def _client(nc: MagicMock) -> Mq9Client:
    client = Mq9Client("nats://localhost:4222")
    client._nc = nc
    return client


# ---------------------------------------------------------------------------
# 1. connect / close / context manager
# ---------------------------------------------------------------------------

async def test_connect_calls_nats_connect() -> None:
    with patch("nats.connect", new_callable=AsyncMock) as mock_connect:
        mock_connect.return_value = _make_nc()
        client = Mq9Client("nats://localhost:4222", reconnect_attempts=3, reconnect_delay=1.0)
        await client.connect()
        mock_connect.assert_called_once_with(
            "nats://localhost:4222",
            max_reconnect_attempts=3,
            reconnect_time_wait=1.0,
        )


async def test_close_calls_drain() -> None:
    nc = _make_nc()
    client = _client(nc)
    await client.close()
    nc.drain.assert_called_once()


async def test_close_skips_drain_when_closed() -> None:
    nc = _make_nc(is_closed=True)
    client = _client(nc)
    await client.close()
    nc.drain.assert_not_called()


async def test_context_manager() -> None:
    with patch("nats.connect", new_callable=AsyncMock) as mock_connect:
        nc = _make_nc()
        mock_connect.return_value = nc
        async with Mq9Client("nats://localhost:4222") as client:
            assert client._nc is nc
        nc.drain.assert_called_once()


# ---------------------------------------------------------------------------
# 2. mailbox_create — with name, without name
# ---------------------------------------------------------------------------

async def test_mailbox_create_with_name() -> None:
    nc = _make_nc()
    nc.request.return_value = _make_response({"error": "", "mail_address": "agent.inbox"})
    client = _client(nc)

    result = await client.mailbox_create(name="agent.inbox", ttl=3600)

    assert result == "agent.inbox"
    call_args = nc.request.call_args
    subject, data = call_args.args[0], call_args.args[1]
    assert subject == "$mq9.AI.MAILBOX.CREATE"
    body = json.loads(data)
    assert body["name"] == "agent.inbox"
    assert body["ttl"] == 3600


async def test_mailbox_create_without_name() -> None:
    nc = _make_nc()
    nc.request.return_value = _make_response({"error": "", "mail_address": "auto.generated.xyz"})
    client = _client(nc)

    result = await client.mailbox_create()

    assert result == "auto.generated.xyz"
    body = json.loads(nc.request.call_args.args[1])
    assert "name" not in body
    assert body["ttl"] == 0


# ---------------------------------------------------------------------------
# 3. mailbox_create — server returns error → raises Mq9Error
# ---------------------------------------------------------------------------

async def test_mailbox_create_server_error_raises() -> None:
    nc = _make_nc()
    nc.request.return_value = _make_response({"error": "quota exceeded"})
    client = _client(nc)

    with pytest.raises(Mq9Error, match="quota exceeded"):
        await client.mailbox_create(name="x")


# ---------------------------------------------------------------------------
# 4 & 5. send — headers and msg_id
# ---------------------------------------------------------------------------

async def test_send_normal_priority_no_header() -> None:
    nc = _make_nc()
    nc.request.return_value = _make_response({"error": "", "msg_id": 7})
    client = _client(nc)

    msg_id = await client.send("task.q", b"hello")

    assert msg_id == 7
    # No headers → plain request, not publish+subscribe
    nc.request.assert_called_once()
    subject = nc.request.call_args.args[0]
    assert subject == "$mq9.AI.MSG.SEND.task.q"


async def test_send_urgent_priority_uses_header() -> None:
    nc = _make_nc()
    nc.request.return_value = _make_response({"error": "", "msg_id": 3})

    # For header path we need to mock subscribe + the inbox future mechanism.
    # We patch _request_with_headers directly to avoid async complexity.
    client = _client(nc)

    async def _fake_request_with_headers(subject, payload, headers):
        assert headers.get("mq9-priority") == "urgent"
        return {"error": "", "msg_id": 3}

    client._request_with_headers = _fake_request_with_headers  # type: ignore[method-assign]

    msg_id = await client.send("task.q", b"hi", priority=Priority.URGENT)
    assert msg_id == 3


async def test_send_with_key_delay_ttl_tags() -> None:
    client = _client(_make_nc())

    captured: dict = {}

    async def _fake_request_with_headers(subject, payload, headers):
        captured.update(headers)
        return {"error": "", "msg_id": 10}

    client._request_with_headers = _fake_request_with_headers  # type: ignore[method-assign]

    msg_id = await client.send(
        "task.q",
        b"data",
        key="dedup-key",
        delay=30,
        ttl=120,
        tags=["a", "b"],
    )

    assert msg_id == 10
    assert captured["mq9-key"] == "dedup-key"
    assert captured["mq9-delay"] == "30"
    assert captured["mq9-ttl"] == "120"
    assert captured["mq9-tags"] == "a,b"


async def test_send_returns_minus_one_for_delayed() -> None:
    nc = _make_nc()
    client = _client(nc)

    async def _fake_request_with_headers(subject, payload, headers):
        return {"error": "", "msg_id": -1}

    client._request_with_headers = _fake_request_with_headers  # type: ignore[method-assign]

    msg_id = await client.send("q", b"x", delay=60)
    assert msg_id == -1


async def test_send_dict_payload_serialized() -> None:
    nc = _make_nc()
    nc.request.return_value = _make_response({"error": "", "msg_id": 1})
    client = _client(nc)

    await client.send("q", {"key": "value"})

    raw = nc.request.call_args.args[1]
    assert json.loads(raw) == {"key": "value"}


# ---------------------------------------------------------------------------
# 6 & 7. fetch
# ---------------------------------------------------------------------------

def _b64(s: str) -> str:
    return base64.b64encode(s.encode()).decode()


async def test_fetch_stateless() -> None:
    raw_messages = [
        {"msg_id": 1, "payload": _b64("hello"), "priority": "normal", "create_time": 1000},
        {"msg_id": 2, "payload": _b64("world"), "priority": "urgent", "create_time": 1001},
    ]
    nc = _make_nc()
    nc.request.return_value = _make_response({"error": "", "messages": raw_messages})
    client = _client(nc)

    messages = await client.fetch("inbox.abc")

    assert len(messages) == 2
    assert messages[0].msg_id == 1
    assert messages[0].payload == b"hello"
    assert messages[0].priority == Priority.NORMAL
    assert messages[1].priority == Priority.URGENT

    body = json.loads(nc.request.call_args.args[1])
    assert "group_name" not in body
    assert body["deliver"] == "latest"


async def test_fetch_stateful_with_group_name() -> None:
    raw_messages = [
        {"msg_id": 5, "payload": _b64("task"), "priority": "critical", "create_time": 9999},
    ]
    nc = _make_nc()
    nc.request.return_value = _make_response({"error": "", "messages": raw_messages})
    client = _client(nc)

    messages = await client.fetch("inbox.abc", group_name="worker-1", deliver="earliest")

    assert messages[0].priority == Priority.CRITICAL
    body = json.loads(nc.request.call_args.args[1])
    assert body["group_name"] == "worker-1"
    assert body["deliver"] == "earliest"


async def test_fetch_empty_messages() -> None:
    nc = _make_nc()
    nc.request.return_value = _make_response({"error": "", "messages": []})
    client = _client(nc)

    messages = await client.fetch("inbox.abc")
    assert messages == []


# ---------------------------------------------------------------------------
# 8. ack
# ---------------------------------------------------------------------------

async def test_ack_sends_correct_body() -> None:
    nc = _make_nc()
    nc.request.return_value = _make_response({"error": ""})
    client = _client(nc)

    await client.ack("task.q", "worker-1", 42)

    subject = nc.request.call_args.args[0]
    body = json.loads(nc.request.call_args.args[1])
    assert subject == "$mq9.AI.MSG.ACK.task.q"
    assert body == {"group_name": "worker-1", "mail_address": "task.q", "msg_id": 42}


# ---------------------------------------------------------------------------
# 9. consume — happy path
# ---------------------------------------------------------------------------

async def test_consume_happy_path() -> None:
    raw_messages = [
        {"msg_id": 1, "payload": _b64("ping"), "priority": "normal", "create_time": 100},
    ]

    call_count = 0

    async def _fetch_side_effect(subject, data, timeout):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return _make_response({"error": "", "messages": raw_messages})
        # Second call blocks (simulating slow broker) so stop() fires first.
        await asyncio.sleep(10)
        return _make_response({"error": "", "messages": []})

    nc = _make_nc(request_side_effect=_fetch_side_effect)
    # ack also goes through request
    ack_calls: list[dict] = []

    original_side_effect = nc.request.side_effect

    async def _combined(subject, data, timeout=5.0):
        if "ACK" in subject:
            ack_calls.append(json.loads(data))
            return _make_response({"error": ""})
        return await original_side_effect(subject, data, timeout)

    nc.request.side_effect = _combined

    client = _client(nc)

    received: list[Message] = []

    async def handler(msg: Message) -> None:
        received.append(msg)

    consumer = await client.consume("inbox", handler, group_name="g1", auto_ack=True)
    # Allow the loop one iteration.
    await asyncio.sleep(0.05)
    await consumer.stop()

    assert consumer.processed_count >= 1
    assert received[0].payload == b"ping"
    assert any(a["msg_id"] == 1 for a in ack_calls)


# ---------------------------------------------------------------------------
# 10. consume — handler raises: error_handler called, no ack, loop continues
# ---------------------------------------------------------------------------

async def test_consume_handler_exception_calls_error_handler_no_ack() -> None:
    raw_messages = [
        {"msg_id": 7, "payload": _b64("bad"), "priority": "normal", "create_time": 200},
    ]

    fetch_count = 0

    async def _fetch_side_effect(subject, data, timeout=5.0):
        nonlocal fetch_count
        fetch_count += 1
        if fetch_count == 1:
            return _make_response({"error": "", "messages": raw_messages})
        await asyncio.sleep(10)
        return _make_response({"error": "", "messages": []})

    nc = _make_nc(request_side_effect=_fetch_side_effect)

    ack_called = False

    async def _combined(subject, data, timeout=5.0):
        nonlocal ack_called
        if "ACK" in subject:
            ack_called = True
            return _make_response({"error": ""})
        return await nc.request.side_effect(subject, data, timeout)

    nc.request.side_effect = _fetch_side_effect

    client = _client(nc)

    error_records: list[tuple[Message, Exception]] = []

    async def bad_handler(msg: Message) -> None:
        raise ValueError("oops")

    async def error_handler(msg: Message, exc: Exception) -> None:
        error_records.append((msg, exc))

    consumer = await client.consume(
        "inbox",
        bad_handler,
        group_name="g1",
        auto_ack=True,
        error_handler=error_handler,
    )
    await asyncio.sleep(0.05)
    await consumer.stop()

    assert consumer.processed_count == 0
    assert not ack_called
    assert len(error_records) >= 1
    assert isinstance(error_records[0][1], ValueError)


# ---------------------------------------------------------------------------
# 11. consume — stop() stops the loop
# ---------------------------------------------------------------------------

async def test_consume_stop() -> None:
    nc = _make_nc()

    async def _slow_fetch(subject, data, timeout=5.0):
        await asyncio.sleep(10)
        return _make_response({"error": "", "messages": []})

    nc.request.side_effect = _slow_fetch
    client = _client(nc)

    async def handler(msg: Message) -> None:
        pass

    consumer = await client.consume("inbox", handler)
    assert consumer.is_running is True
    await consumer.stop()
    assert consumer.is_running is False


# ---------------------------------------------------------------------------
# 12. query — with/without filters
# ---------------------------------------------------------------------------

async def test_query_with_filters() -> None:
    raw_messages = [
        {"msg_id": 3, "payload": _b64("q"), "priority": "normal", "create_time": 500},
    ]
    nc = _make_nc()
    nc.request.return_value = _make_response({"error": "", "messages": raw_messages})
    client = _client(nc)

    messages = await client.query("inbox", key="status", limit=5, since=400)

    assert len(messages) == 1
    body = json.loads(nc.request.call_args.args[1])
    assert body == {"key": "status", "limit": 5, "since": 400}
    assert nc.request.call_args.args[0] == "$mq9.AI.MSG.QUERY.inbox"


async def test_query_without_filters() -> None:
    nc = _make_nc()
    nc.request.return_value = _make_response({"error": "", "messages": []})
    client = _client(nc)

    messages = await client.query("inbox")

    assert messages == []
    body = json.loads(nc.request.call_args.args[1])
    assert body == {}


# ---------------------------------------------------------------------------
# 13. delete
# ---------------------------------------------------------------------------

async def test_delete_correct_subject() -> None:
    nc = _make_nc()
    nc.request.return_value = _make_response({"error": "", "deleted": True})
    client = _client(nc)

    await client.delete("task.q", 99)

    subject = nc.request.call_args.args[0]
    assert subject == "$mq9.AI.MSG.DELETE.task.q.99"


# ---------------------------------------------------------------------------
# 14. agent_register
# ---------------------------------------------------------------------------

async def test_agent_register_passes_agent_card() -> None:
    nc = _make_nc()
    nc.request.return_value = _make_response({"error": ""})
    client = _client(nc)

    card = {"mailbox": "agent.payments", "name": "PaymentAgent", "version": "1.0"}
    await client.agent_register(card)

    subject = nc.request.call_args.args[0]
    body = json.loads(nc.request.call_args.args[1])
    assert subject == "$mq9.AI.AGENT.REGISTER"
    assert body == card


# ---------------------------------------------------------------------------
# 15. agent_unregister / agent_report
# ---------------------------------------------------------------------------

async def test_agent_unregister() -> None:
    nc = _make_nc()
    nc.request.return_value = _make_response({"error": ""})
    client = _client(nc)

    await client.agent_unregister("agent.payments")

    subject = nc.request.call_args.args[0]
    body = json.loads(nc.request.call_args.args[1])
    assert subject == "$mq9.AI.AGENT.UNREGISTER"
    assert body["mailbox"] == "agent.payments"


async def test_agent_report() -> None:
    nc = _make_nc()
    nc.request.return_value = _make_response({"error": ""})
    client = _client(nc)

    report = {"mailbox": "agent.payments", "status": "healthy", "load": 0.3}
    await client.agent_report(report)

    subject = nc.request.call_args.args[0]
    body = json.loads(nc.request.call_args.args[1])
    assert subject == "$mq9.AI.AGENT.REPORT"
    assert body == report


# ---------------------------------------------------------------------------
# 16. agent_discover
# ---------------------------------------------------------------------------

async def test_agent_discover_with_text() -> None:
    agents = [{"mailbox": "agent.pay", "name": "PayAgent"}]
    nc = _make_nc()
    nc.request.return_value = _make_response({"error": "", "agents": agents})
    client = _client(nc)

    result = await client.agent_discover(text="payment")

    assert result == agents
    body = json.loads(nc.request.call_args.args[1])
    assert body["text"] == "payment"
    assert body["limit"] == 20
    assert body["page"] == 1


async def test_agent_discover_with_semantic() -> None:
    nc = _make_nc()
    nc.request.return_value = _make_response({"error": "", "agents": []})
    client = _client(nc)

    result = await client.agent_discover(semantic="process payment refund", limit=5, page=2)

    assert result == []
    body = json.loads(nc.request.call_args.args[1])
    assert body["semantic"] == "process payment refund"
    assert body["limit"] == 5
    assert body["page"] == 2


async def test_agent_discover_empty() -> None:
    nc = _make_nc()
    nc.request.return_value = _make_response({"error": "", "agents": []})
    client = _client(nc)

    result = await client.agent_discover()

    assert result == []
    body = json.loads(nc.request.call_args.args[1])
    assert "text" not in body
    assert "semantic" not in body
