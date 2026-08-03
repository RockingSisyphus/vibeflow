from __future__ import annotations

from vibeflow.core import DataProvider
from vibeflow.targets.python.project import NodeContract, NodeInfo


def _info(type_key: str) -> NodeInfo:
    return NodeInfo(
        type_key=type_key,
        display_name="Forbidden Global State Effect",
        category="sandbox",
        description="Verifies that global_state does not grant unrelated effects.",
        version="0.1.0",
        flow_kind="global_state",
    )


def _contract() -> NodeContract:
    return NodeContract(
        provides=(DataProvider("bad.out", "bad.out", "Bad Out"),),
        output_semantics={"bad.out": ("Unreachable output for an invalid node.",)},
        output_schema={"bad.out": {"type": "integer"}},
    )


class GlobalStateFileNode:
    NODE_INFO = _info("bad.global_state.file")
    CONTRACT = _contract()

    def run_pure(self, inputs, params):
        del inputs, params
        with open("forbidden.txt", "w", encoding="utf-8") as handle:
            handle.write("forbidden")
        return {"bad.out": 1}


class GlobalStateEnvironmentNode:
    NODE_INFO = _info("bad.global_state.environment")
    CONTRACT = _contract()

    def run_pure(self, inputs, params):
        del inputs, params
        import os

        return {"bad.out": int(bool(os.getenv("FORBIDDEN")))}


class GlobalStateNetworkNode:
    NODE_INFO = _info("bad.global_state.network")
    CONTRACT = _contract()

    def run_pure(self, inputs, params):
        del inputs, params
        import socket

        return {"bad.out": int(socket.gethostname() == "")}


class GlobalStateSubprocessNode:
    NODE_INFO = _info("bad.global_state.subprocess")
    CONTRACT = _contract()

    def run_pure(self, inputs, params):
        del inputs, params
        import subprocess

        subprocess.run(("true",), check=True)
        return {"bad.out": 1}


class GlobalStateThreadNode:
    NODE_INFO = _info("bad.global_state.thread")
    CONTRACT = _contract()

    def run_pure(self, inputs, params):
        del inputs, params
        import threading

        worker = threading.Thread(target=lambda: None)
        worker.start()
        worker.join()
        return {"bad.out": 1}


class GlobalStateEvalNode:
    NODE_INFO = _info("bad.global_state.eval")
    CONTRACT = _contract()

    def run_pure(self, inputs, params):
        del inputs, params
        return {"bad.out": eval("1")}


class GlobalStateDynamicImportNode:
    NODE_INFO = _info("bad.global_state.dynamic_import")
    CONTRACT = _contract()

    def run_pure(self, inputs, params):
        del inputs, params
        module = __import__("math")
        return {"bad.out": int(module.sqrt(1))}


class GlobalStateFfiNode:
    NODE_INFO = _info("bad.global_state.ffi")
    CONTRACT = _contract()

    def run_pure(self, inputs, params):
        del inputs, params
        import ctypes

        return {"bad.out": int(ctypes.sizeof(ctypes.c_int))}


class GlobalStateCffiNode:
    NODE_INFO = _info("bad.global_state.cffi")
    CONTRACT = _contract()

    def run_pure(self, inputs, params):
        del inputs, params
        import cffi

        return {"bad.out": int(cffi.FFI() is not None)}
