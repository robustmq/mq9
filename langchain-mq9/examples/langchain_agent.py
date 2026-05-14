"""
langchain-mq9 — LangChain Agent example

An agent that can create mailboxes, send messages, fetch results, and discover other agents.

Run:
    pip install langchain-mq9 langchain-openai
    export OPENAI_API_KEY=...
    python langchain_agent.py
"""

from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.prompts import ChatPromptTemplate
from langchain_mq9 import Mq9Toolkit
from langchain_openai import ChatOpenAI

SERVER = "nats://demo.robustmq.com:4222"

toolkit = Mq9Toolkit(server=SERVER)
tools = toolkit.get_tools()

llm = ChatOpenAI(model="gpt-4o", temperature=0)

prompt = ChatPromptTemplate.from_messages([
    ("system", (
        "You are an AI Agent coordinator with access to the mq9 messaging system. "
        "You can create mailboxes, send messages to other agents, fetch and process replies, "
        "and discover agents by capability. "
        "Always ACK messages after processing them."
    )),
    ("human", "{input}"),
    ("placeholder", "{agent_scratchpad}"),
])

agent = create_tool_calling_agent(llm, tools, prompt)
executor = AgentExecutor(agent=agent, tools=tools, verbose=True)

if __name__ == "__main__":
    result = executor.invoke({
        "input": (
            "1. Create a mailbox with TTL 300. "
            "2. Send a message to it saying 'hello from langchain'. "
            "3. Fetch the message back. "
            "4. ACK the messages. "
            "5. Tell me what you received."
        )
    })
    print("\nFinal answer:", result["output"])
