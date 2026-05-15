"""Mq9Toolkit — bundles all mq9 tools for LangChain / LangGraph Agents."""

from __future__ import annotations

from typing import List

from langchain_core.tools import BaseTool
from langchain_core.tools.base import BaseToolkit

from .tools import (
    AckMessagesTool,
    AgentDiscoverTool,
    AgentRegisterTool,
    CreateMailboxTool,
    DeleteMessageTool,
    FetchMessagesTool,
    QueryMessagesTool,
    SendMessageTool,
)


class Mq9Toolkit(BaseToolkit):
    """Toolkit that gives a LangChain / LangGraph Agent full access to mq9.

    Tools included:
      - create_mailbox    — create a private mailbox
      - send_message      — send a message with priority
      - fetch_messages    — pull messages (FETCH + ACK model)
      - ack_messages      — advance consumer group offset after processing
      - query_messages    — inspect mailbox without consuming (read-only)
      - delete_message    — delete a specific message
      - agent_register    — register this agent in the mq9 registry
      - agent_discover    — find other agents by capability (text or semantic)

    Usage::

        toolkit = Mq9Toolkit(server="nats://demo.robustmq.com:4222")
        tools = toolkit.get_tools()

        # LangChain
        agent = create_tool_calling_agent(llm, tools, prompt)
        executor = AgentExecutor(agent=agent, tools=tools)

        # LangGraph
        from langgraph.prebuilt import create_react_agent
        app = create_react_agent(llm, tools)
    """

    server: str = "nats://localhost:4222"

    def get_tools(self) -> List[BaseTool]:
        return [
            CreateMailboxTool(server=self.server),
            SendMessageTool(server=self.server),
            FetchMessagesTool(server=self.server),
            AckMessagesTool(server=self.server),
            QueryMessagesTool(server=self.server),
            DeleteMessageTool(server=self.server),
            AgentRegisterTool(server=self.server),
            AgentDiscoverTool(server=self.server),
        ]
