"""LangChain tools for the mq9 async Agent mailbox protocol."""

from __future__ import annotations

import asyncio
import json
from typing import Any, Type

from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

from mq9 import Mq9Client, Mq9Error, Priority


# ── Input schemas ────────────────────────────────────────────────────────────


class CreateMailboxInput(BaseModel):
    ttl: int = Field(default=3600, description="Mailbox TTL in seconds. 0 = never expires.")


class SendMessageInput(BaseModel):
    mail_address: str = Field(description="Destination mailbox address.")
    content: str = Field(description="Message content. Will be sent as UTF-8 bytes.")
    priority: str = Field(
        default="normal",
        description="Message priority: 'critical', 'urgent', or 'normal' (default).",
    )


class FetchMessagesInput(BaseModel):
    mail_address: str = Field(description="Mailbox address to fetch messages from.")
    group_name: str = Field(
        default="langchain",
        description="Consumer group name. Broker tracks offset per group — next fetch resumes from last ACK.",
    )
    num_msgs: int = Field(default=10, description="Maximum number of messages to return.")


class AckInput(BaseModel):
    mail_address: str = Field(description="Mailbox address.")
    group_name: str = Field(description="Consumer group name.")
    msg_id: int = Field(description="msg_id of the last processed message in the batch.")


class QueryMessagesInput(BaseModel):
    mail_address: str = Field(description="Mailbox address to query.")
    key: str = Field(default="", description="Filter by dedup key. Empty = no filter.")
    limit: int = Field(default=20, description="Maximum number of messages to return.")


class DeleteMessageInput(BaseModel):
    mail_address: str = Field(description="Mailbox address containing the message.")
    msg_id: int = Field(description="msg_id of the message to delete.")


class AgentRegisterInput(BaseModel):
    name: str = Field(description="Unique agent name (used as mailbox address).")
    capabilities: str = Field(
        description="Natural language description of this agent's capabilities. Used for full-text and semantic search."
    )
    ttl: int = Field(default=3600, description="Mailbox TTL in seconds.")


class AgentDiscoverInput(BaseModel):
    query: str = Field(
        description="What you are looking for. Sent as semantic search if it reads like a sentence, "
                    "otherwise as full-text keyword search. Empty = list all registered agents."
    )
    limit: int = Field(default=10, description="Maximum number of results to return.")


# ── Tools ────────────────────────────────────────────────────────────────────


class CreateMailboxTool(BaseTool):
    """Create a private mq9 mailbox and return its mail_address."""

    name: str = "create_mailbox"
    description: str = (
        "Create a new private mq9 mailbox. Returns a mail_address that acts as the "
        "communication address. Other agents send messages to this address; you fetch "
        "them later with fetch_messages. The mailbox persists messages until TTL expires — "
        "senders do not need to be online when you fetch."
    )
    args_schema: Type[BaseModel] = CreateMailboxInput

    server: str = "nats://localhost:4222"

    def _run(self, ttl: int = 3600, **_: Any) -> str:
        return asyncio.run(self._arun(ttl=ttl))

    async def _arun(self, ttl: int = 3600, **_: Any) -> str:
        async with Mq9Client(self.server) as client:
            address = await client.mailbox_create(ttl=ttl)
        return address


class SendMessageTool(BaseTool):
    """Send a message to a mq9 mailbox."""

    name: str = "send_message"
    description: str = (
        "Send an asynchronous message to another agent via its mq9 mail_address. "
        "The recipient does not need to be online — messages are stored and delivered "
        "when the recipient calls fetch_messages. "
        "Use priority='critical' for abort signals, 'urgent' for time-sensitive tasks, "
        "'normal' (default) for routine messages."
    )
    args_schema: Type[BaseModel] = SendMessageInput

    server: str = "nats://localhost:4222"

    def _run(self, mail_address: str, content: str, priority: str = "normal", **_: Any) -> str:
        return asyncio.run(self._arun(mail_address=mail_address, content=content, priority=priority))

    async def _arun(self, mail_address: str, content: str, priority: str = "normal", **_: Any) -> str:
        try:
            p = Priority(priority)
        except ValueError:
            p = Priority.NORMAL
        async with Mq9Client(self.server) as client:
            msg_id = await client.send(mail_address, content.encode(), priority=p)
        return f"sent to '{mail_address}' priority='{p.value}' msg_id={msg_id}"


class FetchMessagesTool(BaseTool):
    """Fetch pending messages from a mq9 mailbox (FETCH + ACK pull model)."""

    name: str = "fetch_messages"
    description: str = (
        "Pull pending messages from a mq9 mailbox. Messages are returned in priority order "
        "(critical → urgent → normal). Passing a group_name enables stateful consumption: "
        "the broker records the offset and the next fetch resumes from where you left off. "
        "After processing, call ack_messages to advance the offset. "
        "Use this to check for task results, instructions, or any incoming messages."
    )
    args_schema: Type[BaseModel] = FetchMessagesInput

    server: str = "nats://localhost:4222"

    def _run(self, mail_address: str, group_name: str = "langchain", num_msgs: int = 10, **_: Any) -> str:
        return asyncio.run(self._arun(mail_address=mail_address, group_name=group_name, num_msgs=num_msgs))

    async def _arun(self, mail_address: str, group_name: str = "langchain", num_msgs: int = 10, **_: Any) -> str:
        async with Mq9Client(self.server) as client:
            messages = await client.fetch(
                mail_address,
                group_name=group_name,
                deliver="earliest",
                num_msgs=num_msgs,
            )
        if not messages:
            return f"No messages in '{mail_address}'."

        lines = [f"{len(messages)} message(s) from '{mail_address}' (last msg_id={messages[-1].msg_id}):"]
        for msg in messages:
            try:
                content = json.loads(msg.payload)
            except Exception:
                content = msg.payload.decode(errors="replace")
            lines.append(f"  msg_id={msg.msg_id}  priority={msg.priority.value}  content={content}")
        return "\n".join(lines)


class AckMessagesTool(BaseTool):
    """ACK a batch of messages to advance the consumer group offset."""

    name: str = "ack_messages"
    description: str = (
        "Acknowledge processed messages by passing the msg_id of the last message in the batch. "
        "The broker advances the consumer group offset to this msg_id — the next fetch_messages "
        "call will return only messages after this point. "
        "Always call this after successfully processing a fetch_messages result."
    )
    args_schema: Type[BaseModel] = AckInput

    server: str = "nats://localhost:4222"

    def _run(self, mail_address: str, group_name: str, msg_id: int, **_: Any) -> str:
        return asyncio.run(self._arun(mail_address=mail_address, group_name=group_name, msg_id=msg_id))

    async def _arun(self, mail_address: str, group_name: str, msg_id: int, **_: Any) -> str:
        async with Mq9Client(self.server) as client:
            await client.ack(mail_address, group_name, msg_id)
        return f"ACKed msg_id={msg_id} for group='{group_name}' on '{mail_address}'"


class QueryMessagesTool(BaseTool):
    """Inspect messages in a mailbox without affecting the consumption offset."""

    name: str = "query_messages"
    description: str = (
        "Inspect messages currently stored in a mq9 mailbox without consuming them. "
        "The consumption offset is NOT affected — safe to call at any time for debugging "
        "or state inspection. Optionally filter by dedup key to get the latest message "
        "with that key (e.g. key='status' returns the current task status)."
    )
    args_schema: Type[BaseModel] = QueryMessagesInput

    server: str = "nats://localhost:4222"

    def _run(self, mail_address: str, key: str = "", limit: int = 20, **_: Any) -> str:
        return asyncio.run(self._arun(mail_address=mail_address, key=key, limit=limit))

    async def _arun(self, mail_address: str, key: str = "", limit: int = 20, **_: Any) -> str:
        async with Mq9Client(self.server) as client:
            messages = await client.query(
                mail_address,
                key=key or None,
                limit=limit,
            )
        if not messages:
            return f"No messages in '{mail_address}'."

        lines = [f"{len(messages)} message(s) in '{mail_address}' (read-only, offset unchanged):"]
        for msg in messages:
            try:
                content = json.loads(msg.payload)
            except Exception:
                content = msg.payload.decode(errors="replace")
            lines.append(f"  msg_id={msg.msg_id}  priority={msg.priority.value}  content={content}")
        return "\n".join(lines)


class DeleteMessageTool(BaseTool):
    """Delete a specific message from a mq9 mailbox."""

    name: str = "delete_message"
    description: str = (
        "Permanently delete a specific message from a mq9 mailbox by its msg_id. "
        "Use query_messages to find the msg_id before deleting. "
        "Deletion is immediate and cannot be undone."
    )
    args_schema: Type[BaseModel] = DeleteMessageInput

    server: str = "nats://localhost:4222"

    def _run(self, mail_address: str, msg_id: int, **_: Any) -> str:
        return asyncio.run(self._arun(mail_address=mail_address, msg_id=msg_id))

    async def _arun(self, mail_address: str, msg_id: int, **_: Any) -> str:
        async with Mq9Client(self.server) as client:
            await client.delete(mail_address, msg_id)
        return f"Deleted msg_id={msg_id} from '{mail_address}'"


class AgentRegisterTool(BaseTool):
    """Register this agent in the mq9 Agent registry."""

    name: str = "agent_register"
    description: str = (
        "Register this agent in the mq9 built-in Agent registry with a capability description. "
        "Other agents can then discover this agent by full-text or semantic search. "
        "Call this at startup. Call agent_unregister at shutdown."
    )
    args_schema: Type[BaseModel] = AgentRegisterInput

    server: str = "nats://localhost:4222"

    def _run(self, name: str, capabilities: str, ttl: int = 3600, **_: Any) -> str:
        return asyncio.run(self._arun(name=name, capabilities=capabilities, ttl=ttl))

    async def _arun(self, name: str, capabilities: str, ttl: int = 3600, **_: Any) -> str:
        async with Mq9Client(self.server) as client:
            address = await client.mailbox_create(name=name, ttl=ttl)
            await client.agent_register({
                "name": name,
                "mailbox": address,
                "payload": capabilities,
            })
        return f"Registered agent '{name}' with mailbox '{address}'"


class AgentDiscoverTool(BaseTool):
    """Discover agents in the mq9 registry by capability."""

    name: str = "agent_discover"
    description: str = (
        "Search the mq9 Agent registry for agents that match a capability description. "
        "Phrase your query as a natural language sentence for semantic vector search "
        "(e.g. 'find an agent that can translate Chinese to English'). "
        "Use keywords for full-text search (e.g. 'translator'). "
        "Leave query empty to list all registered agents. "
        "Returns each agent's name and mailbox address — send tasks directly to the mailbox."
    )
    args_schema: Type[BaseModel] = AgentDiscoverInput

    server: str = "nats://localhost:4222"

    def _run(self, query: str = "", limit: int = 10, **_: Any) -> str:
        return asyncio.run(self._arun(query=query, limit=limit))

    async def _arun(self, query: str = "", limit: int = 10, **_: Any) -> str:
        # Heuristic: sentence-like query → semantic, short keyword → text
        is_semantic = len(query.split()) > 3
        async with Mq9Client(self.server) as client:
            agents = await client.agent_discover(
                semantic=query if is_semantic and query else None,
                text=query if not is_semantic and query else None,
                limit=limit,
            )
        if not agents:
            return "No agents found."

        lines = [f"Found {len(agents)} agent(s):"]
        for a in agents:
            lines.append(f"  name={a.get('name')}  mailbox={a.get('mailbox')}")
            if a.get("payload"):
                lines.append(f"    capabilities: {a['payload'][:120]}")
        return "\n".join(lines)
