from __future__ import annotations

from vibeflow import DataProvider, DataRequirement, NodeContract, NodeInfo


def REQ(data_type: str, cardinality: str = "exactly_one") -> DataRequirement:
    return DataRequirement(type=data_type, cardinality=cardinality)


def PROV(key: str, data_type: str | None = None) -> DataProvider:
    return DataProvider(key=key, type=data_type or key)


def VALUE(inputs, data_type: str):
    return inputs[data_type]["value"]


def ENV(data_type: str, value):
    return {"key": data_type, "type": data_type, "value": value, "source_node": "example"}


class DelegateArgvNode:
    NODE_INFO = NodeInfo(
        "sandbox.delegate_argv",
        "解析受让的 CLI 参数",
        "sandbox",
        "使用普通 argparse 解析 VibeFlow 原样注入的 cli.argv。",
        "0.1.0",
        "io",
    )
    CONTRACT = NodeContract(
        requires=(REQ("cli.argv"),),
        provides=(PROV("cli.input_path"), PROV("cli.verbose")),
        input_semantics={"cli.argv": ("不含 argv0 和 -- 分隔符的业务命令行参数。",)},
        output_semantics={
            "cli.input_path": ("业务 --input 参数指定的文件路径。",),
            "cli.verbose": ("是否启用详细业务输出。",),
        },
        output_schema={
            "cli.input_path": {"type": "string"},
            "cli.verbose": {"type": "boolean"},
        },
        examples=({"inputs": {"cli.argv": ENV("cli.argv", ["--input", "data.yaml", "--verbose"])}, "params": {}},),
    )

    def run_pure(self, inputs, params):
        import argparse

        parser = argparse.ArgumentParser(prog="vibeflow-sandbox")
        parser.add_argument("--input", required=True)
        parser.add_argument("--verbose", action="store_true")
        parsed = parser.parse_args(list(VALUE(inputs, "cli.argv")))
        return {"cli.input_path": parsed.input, "cli.verbose": parsed.verbose}


class DelegateDocumentNode:
    NODE_INFO = NodeInfo(
        "sandbox.delegate_document",
        "读取 CLI 文档输入",
        "sandbox",
        "由 document 节点执行真实文件读取并形成业务文档内容。",
        "0.1.0",
        "document",
    )
    CONTRACT = NodeContract(
        requires=(REQ("cli.input_path"),),
        provides=(PROV("document.message"),),
        input_semantics={"cli.input_path": ("需要读取的业务输入文件路径。",)},
        output_semantics={"document.message": ("从输入文档提取的 message 字符串。",)},
        output_schema={"document.message": {"type": "string"}},
        examples=({"inputs": {"cli.input_path": ENV("cli.input_path", "data.yaml")}, "params": {}},),
    )

    def run_pure(self, inputs, params):
        import json
        from pathlib import Path

        payload = json.loads(Path(VALUE(inputs, "cli.input_path")).read_text(encoding="utf-8"))
        return {"document.message": str(payload["message"])}


class DelegateBusinessNode:
    NODE_INFO = NodeInfo(
        "sandbox.delegate_business",
        "处理 CLI 业务",
        "sandbox",
        "在普通 process 节点中处理由 document 节点读取的内容。",
        "0.1.0",
        "process",
    )
    CONTRACT = NodeContract(
        requires=(REQ("document.message"),),
        provides=(PROV("business.message"),),
        input_semantics={"document.message": ("输入文档中的原始消息。",)},
        output_semantics={"business.message": ("完成核心业务处理的消息。",)},
        output_schema={"business.message": {"type": "string"}},
        examples=({"inputs": {"document.message": ENV("document.message", "hello")}, "params": {}},),
    )

    def run_pure(self, inputs, params):
        return {"business.message": f"processed:{VALUE(inputs, 'document.message')}"}


class DelegateOutputNode:
    NODE_INFO = NodeInfo(
        "sandbox.delegate_output",
        "写出 CLI 结果",
        "sandbox",
        "把业务结果写入真实 stdout/stderr，并形成保留的 cli.exit_code。",
        "0.1.0",
        "io",
    )
    CONTRACT = NodeContract(
        requires=(REQ("business.message"), REQ("cli.verbose")),
        provides=(PROV("cli.exit_code"),),
        input_semantics={
            "business.message": ("需要输出的最终业务消息。",),
            "cli.verbose": ("是否向 stderr 输出详细信息。",),
        },
        output_semantics={"cli.exit_code": ("进程应返回的业务退出码。",)},
        output_schema={"cli.exit_code": {"type": "integer", "minimum": 0, "maximum": 255}},
        examples=({
            "inputs": {
                "business.message": ENV("business.message", "processed:hello"),
                "cli.verbose": ENV("cli.verbose", True),
            },
            "params": {},
        },),
    )

    def run_pure(self, inputs, params):
        import sys

        print(VALUE(inputs, "business.message"))
        if VALUE(inputs, "cli.verbose"):
            print("verbose:delegate-cli", file=sys.stderr)
        return {"cli.exit_code": 0}


class DelegateEndNode:
    NODE_INFO = NodeInfo(
        "sandbox.delegate_end",
        "CLI 流程结束",
        "sandbox",
        "消费 cli.exit_code 并结束让渡 CLI graph。",
        "0.1.0",
        "terminal",
    )
    CONTRACT = NodeContract(
        requires=(REQ("cli.exit_code"),),
        input_semantics={"cli.exit_code": ("已经形成的业务退出码。",)},
        examples=({"inputs": {"cli.exit_code": ENV("cli.exit_code", 0)}, "params": {}},),
    )

    def run_pure(self, inputs, params):
        return {}
