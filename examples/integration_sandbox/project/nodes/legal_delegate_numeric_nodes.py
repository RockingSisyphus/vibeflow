from __future__ import annotations

from vibeflow import DataProvider, DataRequirement, NodeContract, NodeInfo


def REQ(data_type: str) -> DataRequirement:
    return DataRequirement(type=data_type, cardinality="exactly_one")


def PROV(key: str) -> DataProvider:
    return DataProvider(key=key, type=key)


def VALUE(inputs, data_type: str):
    return inputs[data_type]["value"]


def ENV(data_type: str, value):
    return {"key": data_type, "type": data_type, "value": value, "source_node": "example"}


class NumericArgvNode:
    NODE_INFO = NodeInfo(
        "sandbox.numeric_argv",
        "解析数值 CLI 参数",
        "sandbox",
        "解析让渡的 argv，形成左右输入文件和结果文件路径。",
        "0.1.0",
        "io",
    )
    CONTRACT = NodeContract(
        requires=(REQ("cli.argv"),),
        provides=(PROV("cli.left_path"), PROV("cli.right_path"), PROV("cli.output_path")),
        input_semantics={"cli.argv": ("不含 argv0 和分隔符的原始业务参数。",)},
        output_semantics={
            "cli.left_path": ("--left 指定的左侧数值文件。",),
            "cli.right_path": ("--right 指定的右侧数值文件。",),
            "cli.output_path": ("--output 指定的计算结果文件。",),
        },
        output_schema={
            "cli.left_path": {"type": "string"},
            "cli.right_path": {"type": "string"},
            "cli.output_path": {"type": "string"},
        },
        examples=({
            "inputs": {"cli.argv": ENV("cli.argv", ["--left", "left.txt", "--right", "right.txt", "--output", "sum.txt"])},
            "params": {},
        },),
    )

    def run_pure(self, inputs, params):
        import argparse

        parser = argparse.ArgumentParser(prog="vibeflow-numeric")
        parser.add_argument("--left", required=True)
        parser.add_argument("--right", required=True)
        parser.add_argument("--output", required=True)
        parsed = parser.parse_args(list(VALUE(inputs, "cli.argv")))
        return {
            "cli.left_path": parsed.left,
            "cli.right_path": parsed.right,
            "cli.output_path": parsed.output,
        }


class NumericBuiltinInputNode:
    NODE_INFO = NodeInfo(
        "sandbox.numeric_builtin_input",
        "通过 input 读取数值",
        "sandbox",
        "使用真实 input() 从 stdin 读取一个整数。",
        "0.1.0",
        "io",
    )
    CONTRACT = NodeContract(
        provides=(PROV("number.stdin"),),
        output_semantics={"number.stdin": ("从真实 stdin 读取的整数。",)},
        output_schema={"number.stdin": {"type": "integer"}},
        examples=({"inputs": {}, "params": {}},),
    )

    def run_pure(self, inputs, params):
        return {"number.stdin": int(input())}


class NumericStreamInputNode:
    NODE_INFO = NodeInfo(
        "sandbox.numeric_stream_input",
        "通过 stdin stream 读取数值",
        "sandbox",
        "使用 sys.stdin.readline() 从真实标准输入读取一个整数。",
        "0.1.0",
        "io",
    )
    CONTRACT = NodeContract(
        provides=(PROV("number.stdin"),),
        output_semantics={"number.stdin": ("从真实 stdin stream 读取的整数。",)},
        output_schema={"number.stdin": {"type": "integer"}},
        examples=({"inputs": {}, "params": {}},),
    )

    def run_pure(self, inputs, params):
        import sys

        return {"number.stdin": int(sys.stdin.readline())}


class NumericPathLeftNode:
    NODE_INFO = NodeInfo(
        "sandbox.numeric_path_left",
        "通过 Path 读取左数值",
        "sandbox",
        "使用 Path.read_text 读取左侧整数文件。",
        "0.1.0",
        "document",
    )
    CONTRACT = NodeContract(
        requires=(REQ("cli.left_path"),),
        provides=(PROV("number.left"),),
        input_semantics={"cli.left_path": ("左侧数值文件路径。",)},
        output_semantics={"number.left": ("左侧文件中的整数。",)},
        output_schema={"number.left": {"type": "integer"}},
        examples=({"inputs": {"cli.left_path": ENV("cli.left_path", "left.txt")}, "params": {}},),
    )

    def run_pure(self, inputs, params):
        from pathlib import Path

        text = Path(VALUE(inputs, "cli.left_path")).read_text(encoding="utf-8")
        return {"number.left": int(text)}


class NumericPathRightNode:
    NODE_INFO = NodeInfo(
        "sandbox.numeric_path_right",
        "通过 Path 读取右数值",
        "sandbox",
        "使用 Path.read_text 读取右侧整数文件。",
        "0.1.0",
        "document",
    )
    CONTRACT = NodeContract(
        requires=(REQ("cli.right_path"),),
        provides=(PROV("number.right"),),
        input_semantics={"cli.right_path": ("右侧数值文件路径。",)},
        output_semantics={"number.right": ("右侧文件中的整数。",)},
        output_schema={"number.right": {"type": "integer"}},
        examples=({"inputs": {"cli.right_path": ENV("cli.right_path", "right.txt")}, "params": {}},),
    )

    def run_pure(self, inputs, params):
        from pathlib import Path

        text = Path(VALUE(inputs, "cli.right_path")).read_text(encoding="utf-8")
        return {"number.right": int(text)}


class NumericOpenLeftNode:
    NODE_INFO = NodeInfo(
        "sandbox.numeric_open_left",
        "通过 open 读取左数值",
        "sandbox",
        "使用 builtins.open().read() 读取左侧整数文件。",
        "0.1.0",
        "document",
    )
    CONTRACT = NodeContract(
        requires=(REQ("cli.left_path"),),
        provides=(PROV("number.left"),),
        input_semantics={"cli.left_path": ("左侧数值文件路径。",)},
        output_semantics={"number.left": ("左侧文件中的整数。",)},
        output_schema={"number.left": {"type": "integer"}},
        examples=({"inputs": {"cli.left_path": ENV("cli.left_path", "left.txt")}, "params": {}},),
    )

    def run_pure(self, inputs, params):
        import builtins

        with builtins.open(VALUE(inputs, "cli.left_path"), "r", encoding="utf-8") as handle:
            text = handle.read()
        return {"number.left": int(text)}


class NumericOpenRightNode:
    NODE_INFO = NodeInfo(
        "sandbox.numeric_open_right",
        "通过 open 读取右数值",
        "sandbox",
        "使用 builtins.open().readline() 读取右侧整数文件。",
        "0.1.0",
        "document",
    )
    CONTRACT = NodeContract(
        requires=(REQ("cli.right_path"),),
        provides=(PROV("number.right"),),
        input_semantics={"cli.right_path": ("右侧数值文件路径。",)},
        output_semantics={"number.right": ("右侧文件中的整数。",)},
        output_schema={"number.right": {"type": "integer"}},
        examples=({"inputs": {"cli.right_path": ENV("cli.right_path", "right.txt")}, "params": {}},),
    )

    def run_pure(self, inputs, params):
        import builtins

        with builtins.open(VALUE(inputs, "cli.right_path"), "r", encoding="utf-8") as handle:
            text = handle.readline()
        return {"number.right": int(text)}


class NumericSumNode:
    NODE_INFO = NodeInfo(
        "sandbox.numeric_sum",
        "汇总三个数值",
        "sandbox",
        "在 process 节点中对 stdin 与两个文件数值求和。",
        "0.1.0",
        "process",
    )
    CONTRACT = NodeContract(
        requires=(REQ("number.stdin"), REQ("number.left"), REQ("number.right")),
        provides=(PROV("number.total"),),
        input_semantics={
            "number.stdin": ("控制台输入的整数。",),
            "number.left": ("左侧文件中的整数。",),
            "number.right": ("右侧文件中的整数。",),
        },
        output_semantics={"number.total": ("三个输入整数之和。",)},
        output_schema={"number.total": {"type": "integer"}},
        examples=({
            "inputs": {
                "number.stdin": ENV("number.stdin", 7),
                "number.left": ENV("number.left", 11),
                "number.right": ENV("number.right", 13),
            },
            "params": {},
        },),
    )

    def run_pure(self, inputs, params):
        total = VALUE(inputs, "number.stdin") + VALUE(inputs, "number.left")
        return {"number.total": total + VALUE(inputs, "number.right")}


class NumericPathWriterNode:
    NODE_INFO = NodeInfo(
        "sandbox.numeric_path_writer",
        "通过 Path 写入结果",
        "sandbox",
        "使用 Path.write_text 将 number.total 写入 cli.output_path，并提供 document.output_written。",
        "0.1.0",
        "document",
    )
    CONTRACT = NodeContract(
        requires=(REQ("cli.output_path"), REQ("number.total")),
        provides=(PROV("document.output_written"),),
        input_semantics={
            "cli.output_path": ("需要写入的结果文件路径。",),
            "number.total": ("需要持久化的求和结果。",),
        },
        output_semantics={"document.output_written": ("已成功写入的结果文件路径。",)},
        output_schema={"document.output_written": {"type": "string"}},
        examples=({
            "inputs": {
                "cli.output_path": ENV("cli.output_path", "sum.txt"),
                "number.total": ENV("number.total", 31),
            },
            "params": {},
        },),
    )

    def run_pure(self, inputs, params):
        from pathlib import Path

        output_path = VALUE(inputs, "cli.output_path")
        Path(output_path).write_text(f"{VALUE(inputs, 'number.total')}\n", encoding="utf-8")
        return {"document.output_written": output_path}


class NumericOpenWriterNode:
    NODE_INFO = NodeInfo(
        "sandbox.numeric_open_writer",
        "通过 open 写入结果",
        "sandbox",
        "使用 builtins.open().write() 将 number.total 写入 cli.output_path，并提供 document.output_written。",
        "0.1.0",
        "document",
    )
    CONTRACT = NodeContract(
        requires=(REQ("cli.output_path"), REQ("number.total")),
        provides=(PROV("document.output_written"),),
        input_semantics={
            "cli.output_path": ("需要写入的结果文件路径。",),
            "number.total": ("需要持久化的求和结果。",),
        },
        output_semantics={"document.output_written": ("已成功写入的结果文件路径。",)},
        output_schema={"document.output_written": {"type": "string"}},
        examples=({
            "inputs": {
                "cli.output_path": ENV("cli.output_path", "sum.txt"),
                "number.total": ENV("number.total", 41),
            },
            "params": {},
        },),
    )

    def run_pure(self, inputs, params):
        import builtins

        output_path = VALUE(inputs, "cli.output_path")
        with builtins.open(output_path, "w", encoding="utf-8") as handle:
            handle.write(f"{VALUE(inputs, 'number.total')}\n")
        return {"document.output_written": output_path}


class NumericPrintOutputNode:
    NODE_INFO = NodeInfo(
        "sandbox.numeric_print_output",
        "通过 print 写出结果",
        "sandbox",
        "在 document.output_written 后通过 print 写 number.total，并提供 cli.exit_code。",
        "0.1.0",
        "io",
    )
    CONTRACT = NodeContract(
        requires=(REQ("number.total"), REQ("document.output_written")),
        provides=(PROV("cli.exit_code"),),
        input_semantics={
            "number.total": ("需要显示的最终求和结果。",),
            "document.output_written": ("用于保证文件写入已完成的路径回执。",),
        },
        output_semantics={"cli.exit_code": ("成功时返回的业务退出码。",)},
        output_schema={"cli.exit_code": {"type": "integer", "minimum": 0, "maximum": 255}},
        examples=({
            "inputs": {
                "number.total": ENV("number.total", 31),
                "document.output_written": ENV("document.output_written", "sum.txt"),
            },
            "params": {},
        },),
    )

    def run_pure(self, inputs, params):
        import sys

        print(f"sum={VALUE(inputs, 'number.total')}")
        sys.stderr.write("writer=pathlib\n")
        return {"cli.exit_code": 0}


class NumericStreamOutputNode:
    NODE_INFO = NodeInfo(
        "sandbox.numeric_stream_output",
        "通过 stream 写出结果",
        "sandbox",
        "在 document.output_written 后通过 sys streams 写 number.total，并提供 cli.exit_code。",
        "0.1.0",
        "io",
    )
    CONTRACT = NodeContract(
        requires=(REQ("number.total"), REQ("document.output_written")),
        provides=(PROV("cli.exit_code"),),
        input_semantics={
            "number.total": ("需要显示的最终求和结果。",),
            "document.output_written": ("用于保证文件写入已完成的路径回执。",),
        },
        output_semantics={"cli.exit_code": ("成功时返回的业务退出码。",)},
        output_schema={"cli.exit_code": {"type": "integer", "minimum": 0, "maximum": 255}},
        examples=({
            "inputs": {
                "number.total": ENV("number.total", 41),
                "document.output_written": ENV("document.output_written", "sum.txt"),
            },
            "params": {},
        },),
    )

    def run_pure(self, inputs, params):
        import sys

        sys.stdout.write(f"sum={VALUE(inputs, 'number.total')}\n")
        sys.stderr.write("writer=open\n")
        return {"cli.exit_code": 0}
