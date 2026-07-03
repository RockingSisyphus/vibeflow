from __future__ import annotations

from vibeflow import DataProvider, NodeContract, NodeInfo


def _info(type_key):
    return NodeInfo(type_key=type_key, display_name="Bad", category="bad", description="Bad side effect node.", version="0.1.0", flow_kind="process")


def _contract():
    return NodeContract(
        provides=(DataProvider("bad.out", "bad.out"),),
        output_semantics={"bad.out": ("bad output",)},
        output_schema={"bad.out": {"type": "number"}},
    )


class OpenFileNode:
    NODE_INFO = _info("bad.open")
    CONTRACT = _contract()

    def run_pure(self, inputs, params):
        open("x.txt", "w")
        return {"bad.out": 1}


class PathReadTextNode:
    NODE_INFO = _info("bad.path_read")
    CONTRACT = _contract()

    def run_pure(self, inputs, params):
        from pathlib import Path

        Path("x.txt").read_text()
        return {"bad.out": 1}


class OsGetenvNode:
    NODE_INFO = _info("bad.getenv")
    CONTRACT = _contract()

    def run_pure(self, inputs, params):
        import os

        os.getenv("HOME")
        return {"bad.out": 1}


class SubprocessNode:
    NODE_INFO = _info("bad.subprocess")
    CONTRACT = _contract()

    def run_pure(self, inputs, params):
        import subprocess

        subprocess.run(["python", "--version"])
        return {"bad.out": 1}


class SocketNode:
    NODE_INFO = _info("bad.socket")
    CONTRACT = _contract()

    def run_pure(self, inputs, params):
        import socket

        socket.socket()
        return {"bad.out": 1}


class RequestsNode:
    NODE_INFO = _info("bad.requests")
    CONTRACT = _contract()

    def run_pure(self, inputs, params):
        import requests

        requests.get("https://example.com")
        return {"bad.out": 1}


class SqliteNode:
    NODE_INFO = _info("bad.sqlite")
    CONTRACT = _contract()

    def run_pure(self, inputs, params):
        import sqlite3

        sqlite3.connect(":memory:")
        return {"bad.out": 1}


class EvalNode:
    NODE_INFO = _info("bad.eval")
    CONTRACT = _contract()

    def run_pure(self, inputs, params):
        eval("1 + 1")
        return {"bad.out": 1}


class DynamicImportNode:
    NODE_INFO = _info("bad.dynamic_import")
    CONTRACT = _contract()

    def run_pure(self, inputs, params):
        import importlib

        importlib.import_module("math")
        return {"bad.out": 1}
