"""
langchain-mq9 — LangGraph ReAct Agent example

A two-node graph: orchestrator creates a mailbox and dispatches a task,
then polls until a result arrives.

Run:
    pip install langchain-mq9 langchain-openai langgraph
    export OPENAI_API_KEY=...
    python langgraph_agent.py
"""

import asyncio
from typing import TypedDict

from langgraph.graph import END, StateGraph
from langchain_mq9 import Mq9Toolkit
from langchain_openai import ChatOpenAI

SERVER = "nats://demo.robustmq.com:4222"

toolkit = Mq9Toolkit(server=SERVER)
tools_by_name = {t.name: t for t in toolkit.get_tools()}


# ── State ────────────────────────────────────────────────────────────────────

class State(TypedDict):
    reply_address: str
    messages: list
    done: bool


# ── Nodes ────────────────────────────────────────────────────────────────────

async def setup(state: State) -> State:
    """Create a reply mailbox and send a task to a worker queue."""
    reply_address = await tools_by_name["create_mailbox"]._arun(ttl=300)
    print(f"[setup] reply mailbox: {reply_address}")

    await tools_by_name["send_message"]._arun(
        mail_address="task.queue",
        content=f'{{"task": "summarize", "reply_to": "{reply_address}"}}',
        priority="normal",
    )
    print(f"[setup] task dispatched to task.queue")
    return {**state, "reply_address": reply_address}


async def poll_reply(state: State) -> State:
    """Fetch the reply mailbox. If messages arrived, we're done."""
    result = await tools_by_name["fetch_messages"]._arun(
        mail_address=state["reply_address"],
        group_name="orchestrator",
        num_msgs=5,
    )
    print(f"[poll] {result}")
    done = "No messages" not in result
    if done:
        last_msg_id = _extract_last_msg_id(result)
        if last_msg_id:
            await tools_by_name["ack_messages"]._arun(
                mail_address=state["reply_address"],
                group_name="orchestrator",
                msg_id=last_msg_id,
            )
    return {**state, "messages": [result], "done": done}


def _extract_last_msg_id(text: str) -> int | None:
    import re
    ids = re.findall(r"msg_id=(\d+)", text)
    return int(ids[-1]) if ids else None


def should_continue(state: State) -> str:
    return END if state["done"] else "poll_reply"


# ── Graph ────────────────────────────────────────────────────────────────────

graph = StateGraph(State)
graph.add_node("setup", setup)
graph.add_node("poll_reply", poll_reply)
graph.set_entry_point("setup")
graph.add_edge("setup", "poll_reply")
graph.add_conditional_edges("poll_reply", should_continue)

app = graph.compile()


if __name__ == "__main__":
    result = asyncio.run(app.ainvoke({
        "reply_address": "",
        "messages": [],
        "done": False,
    }))
    print("\nFinal state:", result["messages"])
