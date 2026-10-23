"""Bind compiled blocks to the ordinary graph executor."""
from .block_compiler import graph_block
from .scheduler import run_graph

def run_compiled_steps(runtime, state):
    block = graph_block(runtime._plan)
    if block is not None:
        block.callable(runtime, state)
    else:
        run_graph(runtime, state)


async def run_compiled_steps_async(runtime, state):
    from .completion import suspended
    from .scheduler import run_graph_async
    block = graph_block(runtime._plan)
    if block is not None:
        await suspended(block.callable(runtime, state))
    else:
        await run_graph_async(runtime, state)
