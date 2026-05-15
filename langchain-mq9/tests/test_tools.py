"""Unit tests for langchain-mq9 tools (Mq9Client mocked)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from langchain_mq9 import (
    AckMessagesTool,
    AgentDiscoverTool,
    AgentRegisterTool,
    CreateMailboxTool,
    DeleteMessageTool,
    FetchMessagesTool,
    Mq9Toolkit,
    QueryMessagesTool,
    SendMessageTool,
)
from mq9 import Message, Priority

SERVER = "nats://localhost:4222"


def make_message(msg_id: int, payload: bytes, priority: Priority = Priority.NORMAL) -> Message:
    from dataclasses import dataclass
    msg = MagicMock(spec=Message)
    msg.msg_id = msg_id
    msg.payload = payload
    msg.priority = priority
    msg.create_time = 1700000000
    return msg


def mock_client(
    mailbox_return="test.mailbox",
    send_return=1,
    fetch_return=None,
    query_return=None,
    agents_return=None,
):
    client = AsyncMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    client.mailbox_create = AsyncMock(return_value=mailbox_return)
    client.send = AsyncMock(return_value=send_return)
    client.fetch = AsyncMock(return_value=fetch_return or [])
    client.ack = AsyncMock(return_value=None)
    client.query = AsyncMock(return_value=query_return or [])
    client.delete = AsyncMock(return_value=None)
    client.agent_register = AsyncMock(return_value=None)
    client.agent_unregister = AsyncMock(return_value=None)
    client.agent_report = AsyncMock(return_value=None)
    client.agent_discover = AsyncMock(return_value=agents_return or [])
    return client


# ── CreateMailboxTool ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_mailbox():
    client = mock_client(mailbox_return="my.mailbox")
    with patch("langchain_mq9.tools.Mq9Client", return_value=client):
        tool = CreateMailboxTool(server=SERVER)
        result = await tool._arun(ttl=3600)
    assert result == "my.mailbox"
    client.mailbox_create.assert_awaited_once_with(ttl=3600)


# ── SendMessageTool ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_send_message_normal():
    client = mock_client(send_return=42)
    with patch("langchain_mq9.tools.Mq9Client", return_value=client):
        tool = SendMessageTool(server=SERVER)
        result = await tool._arun(mail_address="agent.inbox", content="hello", priority="normal")
    assert "msg_id=42" in result
    assert "normal" in result

@pytest.mark.asyncio
async def test_send_message_urgent():
    client = mock_client(send_return=7)
    with patch("langchain_mq9.tools.Mq9Client", return_value=client):
        tool = SendMessageTool(server=SERVER)
        result = await tool._arun(mail_address="agent.inbox", content="alert", priority="urgent")
    assert "urgent" in result
    client.send.assert_awaited_once_with("agent.inbox", b"alert", priority=Priority.URGENT)

@pytest.mark.asyncio
async def test_send_message_invalid_priority_falls_back_to_normal():
    client = mock_client(send_return=1)
    with patch("langchain_mq9.tools.Mq9Client", return_value=client):
        tool = SendMessageTool(server=SERVER)
        result = await tool._arun(mail_address="agent.inbox", content="x", priority="unknown")
    assert "normal" in result


# ── FetchMessagesTool ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_fetch_messages_empty():
    client = mock_client(fetch_return=[])
    with patch("langchain_mq9.tools.Mq9Client", return_value=client):
        tool = FetchMessagesTool(server=SERVER)
        result = await tool._arun(mail_address="my.box", group_name="workers")
    assert "No messages" in result

@pytest.mark.asyncio
async def test_fetch_messages_returns_list():
    msgs = [
        make_message(1, b'{"task":1}', Priority.CRITICAL),
        make_message(2, b'{"task":2}', Priority.NORMAL),
    ]
    client = mock_client(fetch_return=msgs)
    with patch("langchain_mq9.tools.Mq9Client", return_value=client):
        tool = FetchMessagesTool(server=SERVER)
        result = await tool._arun(mail_address="my.box", group_name="workers", num_msgs=10)
    assert "2 message(s)" in result
    assert "msg_id=1" in result
    assert "critical" in result


# ── AckMessagesTool ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_ack_messages():
    client = mock_client()
    with patch("langchain_mq9.tools.Mq9Client", return_value=client):
        tool = AckMessagesTool(server=SERVER)
        result = await tool._arun(mail_address="my.box", group_name="workers", msg_id=5)
    assert "msg_id=5" in result
    client.ack.assert_awaited_once_with("my.box", "workers", 5)


# ── QueryMessagesTool ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_query_messages_no_results():
    client = mock_client(query_return=[])
    with patch("langchain_mq9.tools.Mq9Client", return_value=client):
        tool = QueryMessagesTool(server=SERVER)
        result = await tool._arun(mail_address="my.box")
    assert "No messages" in result

@pytest.mark.asyncio
async def test_query_messages_with_key():
    msgs = [make_message(3, b'{"status":"done"}')]
    client = mock_client(query_return=msgs)
    with patch("langchain_mq9.tools.Mq9Client", return_value=client):
        tool = QueryMessagesTool(server=SERVER)
        result = await tool._arun(mail_address="my.box", key="status")
    assert "1 message(s)" in result
    assert "offset unchanged" in result
    client.query.assert_awaited_once_with("my.box", key="status", limit=20)


# ── DeleteMessageTool ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_delete_message():
    client = mock_client()
    with patch("langchain_mq9.tools.Mq9Client", return_value=client):
        tool = DeleteMessageTool(server=SERVER)
        result = await tool._arun(mail_address="my.box", msg_id=9)
    assert "msg_id=9" in result
    client.delete.assert_awaited_once_with("my.box", 9)


# ── AgentRegisterTool ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_agent_register():
    client = mock_client(mailbox_return="agent.translator")
    with patch("langchain_mq9.tools.Mq9Client", return_value=client):
        tool = AgentRegisterTool(server=SERVER)
        result = await tool._arun(
            name="agent.translator",
            capabilities="Multilingual translation EN/ZH/JA",
            ttl=3600,
        )
    assert "agent.translator" in result
    client.agent_register.assert_awaited_once()


# ── AgentDiscoverTool ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_agent_discover_no_results():
    client = mock_client(agents_return=[])
    with patch("langchain_mq9.tools.Mq9Client", return_value=client):
        tool = AgentDiscoverTool(server=SERVER)
        result = await tool._arun(query="translator")
    assert "No agents" in result

@pytest.mark.asyncio
async def test_agent_discover_keyword():
    agents = [{"name": "agent.translator", "mailbox": "agent.translator", "payload": "Translate EN/ZH"}]
    client = mock_client(agents_return=agents)
    with patch("langchain_mq9.tools.Mq9Client", return_value=client):
        tool = AgentDiscoverTool(server=SERVER)
        result = await tool._arun(query="translator", limit=5)
    assert "agent.translator" in result
    # Short query → full-text search
    client.agent_discover.assert_awaited_once_with(semantic=None, text="translator", limit=5)

@pytest.mark.asyncio
async def test_agent_discover_semantic():
    agents = [{"name": "agent.translator", "mailbox": "agent.translator", "payload": "Translate EN/ZH"}]
    client = mock_client(agents_return=agents)
    with patch("langchain_mq9.tools.Mq9Client", return_value=client):
        tool = AgentDiscoverTool(server=SERVER)
        result = await tool._arun(query="find an agent that can translate Chinese to English", limit=5)
    assert "agent.translator" in result
    # Long sentence → semantic search
    call_kwargs = client.agent_discover.call_args.kwargs
    assert call_kwargs["semantic"] is not None
    assert call_kwargs["text"] is None

@pytest.mark.asyncio
async def test_agent_discover_empty_query_lists_all():
    agents = [
        {"name": "agent.a", "mailbox": "agent.a", "payload": "..."},
        {"name": "agent.b", "mailbox": "agent.b", "payload": "..."},
    ]
    client = mock_client(agents_return=agents)
    with patch("langchain_mq9.tools.Mq9Client", return_value=client):
        tool = AgentDiscoverTool(server=SERVER)
        result = await tool._arun(query="")
    assert "2 agent(s)" in result
    client.agent_discover.assert_awaited_once_with(semantic=None, text=None, limit=10)


# ── Mq9Toolkit ───────────────────────────────────────────────────────────────

def test_toolkit_returns_all_tools():
    toolkit = Mq9Toolkit(server=SERVER)
    tools = toolkit.get_tools()
    names = {t.name for t in tools}
    assert names == {
        "create_mailbox",
        "send_message",
        "fetch_messages",
        "ack_messages",
        "query_messages",
        "delete_message",
        "agent_register",
        "agent_discover",
    }

def test_toolkit_propagates_server():
    toolkit = Mq9Toolkit(server="nats://myserver:4222")
    for tool in toolkit.get_tools():
        assert tool.server == "nats://myserver:4222"
