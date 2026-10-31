import asyncio
import logging

logging.basicConfig(level=logging.INFO)

from langchain_core.messages import HumanMessage

from graph import nodes

URL = "https://www.w3schools.com/js/default.asp"

# 1) فقط ابزار Tavily
tools = nodes.get_web_tools()
print("tools:", [t.name for t in tools])
extract = [t for t in tools if "extract" in t.name][0]
out = asyncio.run(extract.ainvoke({"urls": [URL]}))
print("extract chars:", len(out))
print(out[:300].replace("\n", " "))


# 2) agent با ابزارها
async def main():
    agent = nodes.get_tool_agent("test-thread")
    result = await agent.agent.ainvoke(
        {"messages": [HumanMessage(f"Read {URL} and summarize it in 3 short lines.")]},
        config={"recursion_limit": 12},
    )
    print("TRACE:", nodes.build_tool_trace(result["messages"])[:800])
    print("ANSWER:", nodes.message_text(result["messages"][-1]))


asyncio.run(main())