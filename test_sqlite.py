import sqlite3
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.sqlite import SqliteSaver
import asyncio

def node(state):
    return state

builder = StateGraph(dict)
builder.add_node("n", node)
builder.set_entry_point("n")

conn = sqlite3.connect("memoria/bds/checkpoints.db", check_same_thread=False)
saver = SqliteSaver(conn)
graph = builder.compile(checkpointer=saver)

async def test():
    config = {"configurable": {"thread_id": "1"}}
    async for e in graph.astream({"x": 1}, config):
        print(e)
    print("Success")

asyncio.run(test())
