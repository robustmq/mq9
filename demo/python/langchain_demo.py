"""
mq9 Python — LangChain / LangGraph Demo

Demonstrates:
  1. Mq9Toolkit — all 8 tools
  2. LangChain tool_calling agent
  3. LangGraph ReAct agent
  4. Manual tool usage without an LLM

Run:
    pip install langchain-mq9 langchain-openai langgraph
    export OPENAI_API_KEY=...
    python langchain_demo.py
"""

import asyncio
from langchain_mq9 import Mq9Toolkit

SERVER = "nats://demo.robustmq.com:4222"

# ── 1. List available tools ──────────────────────────────────────────────────

toolkit = Mq9Toolkit(server=SERVER)
tools = toolkit.get_tools()
print("Available tools:")
for t in tools:
    print(f"  {t.name}: {t.description[:80]}…")

# ── 2. Manual tool usage (no LLM) ────────────────────────────────────────────

async def manual_demo():
    tools_by_name = {t.name: t for t in tools}

    # Create a mailbox
    address = await tools_by_name["create_mailbox"]._arun(ttl=300)
    print(f"\n[create_mailbox] → {address}")

    # Send a message
    result = await tools_by_name["send_message"]._arun(
        mail_address=address,
        content='{"task": "summarize", "data": "Hello from LangChain"}',
        priority="normal",
    )
    print(f"[send_message] → {result}")

    # Fetch messages
    result = await tools_by_name["fetch_messages"]._arun(
        mail_address=address,
        group_name="langchain",
        num_msgs=5,
    )
    print(f"[fetch_messages] →\n{result}")

    # Parse last msg_id and ACK
    import re
    ids = re.findall(r"msg_id=(\d+)", result)
    if ids:
        ack_result = await tools_by_name["ack_messages"]._arun(
            mail_address=address,
            group_name="langchain",
            msg_id=int(ids[-1]),
        )
        print(f"[ack_messages] → {ack_result}")

    # Register this agent
    reg = await tools_by_name["agent_register"]._arun(
        name="demo.langchain.agent",
        capabilities="Demo agent for testing LangChain mq9 toolkit integration",
        ttl=300,
    )
    print(f"\n[agent_register] → {reg}")

    # Discover by keyword
    disc = await tools_by_name["agent_discover"]._arun(query="demo langchain", limit=5)
    print(f"[agent_discover] → {disc}")

    # Query mailbox (read-only)
    q = await tools_by_name["query_messages"]._arun(mail_address=address)
    print(f"[query_messages] → {q}")

asyncio.run(manual_demo())

# ── 3. LangChain tool_calling agent (requires OPENAI_API_KEY) ────────────────

def langchain_agent_demo():
    import os
    if not os.getenv("OPENAI_API_KEY"):
        print("\n[skip] OPENAI_API_KEY not set — skipping LangChain agent demo")
        return

    from langchain.agents import AgentExecutor, create_tool_calling_agent
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_openai import ChatOpenAI

    llm = ChatOpenAI(model="gpt-4o", temperature=0)
    prompt = ChatPromptTemplate.from_messages([
        ("system", "You are an Agent coordinator with access to the mq9 messaging system."),
        ("human", "{input}"),
        ("placeholder", "{agent_scratchpad}"),
    ])
    agent = create_tool_calling_agent(llm, tools, prompt)
    executor = AgentExecutor(agent=agent, tools=tools, verbose=True)

    result = executor.invoke({
        "input": "Create a mailbox, send 'hello world' to it, fetch the message back, and tell me what you received."
    })
    print("\n[LangChain agent] answer:", result["output"])

langchain_agent_demo()

# ── 4. LangGraph ReAct agent (requires OPENAI_API_KEY) ───────────────────────

async def langgraph_agent_demo():
    import os
    if not os.getenv("OPENAI_API_KEY"):
        print("\n[skip] OPENAI_API_KEY not set — skipping LangGraph agent demo")
        return

    from langgraph.prebuilt import create_react_agent
    from langchain_openai import ChatOpenAI

    llm = ChatOpenAI(model="gpt-4o", temperature=0)
    app = create_react_agent(llm, tools)

    result = await app.ainvoke({
        "messages": [("human", "Discover all registered agents and summarize what you find.")]
    })
    print("\n[LangGraph agent] answer:", result["messages"][-1].content)

asyncio.run(langgraph_agent_demo())
