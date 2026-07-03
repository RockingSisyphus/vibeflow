from __future__ import annotations

from vibeflow import NodeContract, NodeInfo


class SemanticAddPairNode:
    NODE_INFO = NodeInfo(
        type_key="semantic.add_pair",
        display_name="Semantic Add Pair",
        category="semantic",
        description="Adds calc.a and calc.b into calc.sum for arithmetic acceptance flows.",
        version="0.1.0",
        flow_kind="process",
    )
    CONTRACT = NodeContract(
        requires=("calc.a", "calc.b"),
        provides=("calc.sum",),
        input_semantics={"calc.a": ("left numeric addend",), "calc.b": ("right numeric addend",)},
        output_semantics={"calc.sum": ("sum of calc.a and calc.b",)},
        output_schema={"calc.sum": {"type": "number"}},
        examples=({"inputs": {"calc.a": 2, "calc.b": 5}, "params": {}},),
    )

    def run_pure(self, inputs, params):
        return {"calc.sum": inputs["calc.a"] + inputs["calc.b"]}


class SemanticScaleNode:
    NODE_INFO = NodeInfo(
        type_key="semantic.scale",
        display_name="Semantic Scale",
        category="semantic",
        description="Multiplies calc.sum by a configured factor into calc.scaled.",
        version="0.1.0",
        flow_kind="process",
    )
    CONTRACT = NodeContract(
        requires=("calc.sum",),
        provides=("calc.scaled",),
        input_semantics={"calc.sum": ("numeric sum to multiply",)},
        output_semantics={"calc.scaled": ("calc.sum multiplied by factor",)},
        params_schema={"factor": {"type": "number"}},
        output_schema={"calc.scaled": {"type": "number"}},
        examples=({"inputs": {"calc.sum": 7}, "params": {"factor": 3}},),
    )

    def run_pure(self, inputs, params):
        return {"calc.scaled": inputs["calc.sum"] * params.get("factor", 1)}


class SemanticUseScaledNode:
    NODE_INFO = NodeInfo(
        type_key="semantic.use_scaled",
        display_name="Semantic Use Scaled",
        category="semantic",
        description="Promotes calc.scaled to calc.branch so finalization has one stable input key.",
        version="0.1.0",
        flow_kind="process",
    )
    CONTRACT = NodeContract(
        requires=("calc.scaled",),
        provides=("calc.branch",),
        input_semantics={"calc.scaled": ("scaled arithmetic value",)},
        output_semantics={"calc.branch": ("branch value copied from calc.scaled",)},
        output_schema={"calc.branch": {"type": "number"}},
        examples=({"inputs": {"calc.scaled": 21}, "params": {}},),
    )

    def run_pure(self, inputs, params):
        return {"calc.branch": inputs["calc.scaled"]}


class SemanticCompareGtNode:
    NODE_INFO = NodeInfo(
        type_key="semantic.compare_gt",
        display_name="Semantic Compare Greater Than",
        category="semantic",
        description="Compares calc.c and calc.d and emits route.branch for left or right branch selection.",
        version="0.1.0",
        flow_kind="decision",
    )
    CONTRACT = NodeContract(
        requires=("calc.c", "calc.d"),
        provides=("route.branch",),
        input_semantics={"calc.c": ("left comparison value",), "calc.d": ("right comparison value",)},
        output_semantics={"route.branch": ("left when calc.c > calc.d, otherwise right",)},
        output_schema={"route.branch": {"type": "string", "enum": ["left", "right"]}},
        examples=(
            {"inputs": {"calc.c": 9, "calc.d": 4}, "params": {}},
            {"inputs": {"calc.c": 1, "calc.d": 4}, "params": {}},
        ),
    )

    def run_pure(self, inputs, params):
        return {"route.branch": "left" if inputs["calc.c"] > inputs["calc.d"] else "right"}


class SemanticLeftAdjustNode:
    NODE_INFO = NodeInfo(
        type_key="semantic.left_adjust",
        display_name="Semantic Left Adjust",
        category="semantic",
        description="Adds a configured bonus to calc.scaled after the left decision branch is selected.",
        version="0.1.0",
        flow_kind="process",
    )
    CONTRACT = NodeContract(
        requires=("calc.scaled",),
        provides=("calc.left_branch",),
        input_semantics={"calc.scaled": ("scaled arithmetic value selected for the left branch",)},
        output_semantics={"calc.left_branch": ("left branch value after adding bonus",)},
        params_schema={"bonus": {"type": "number"}},
        output_schema={"calc.left_branch": {"type": "number"}},
        examples=({"inputs": {"calc.scaled": 21}, "params": {"bonus": 10}},),
    )

    def run_pure(self, inputs, params):
        return {"calc.left_branch": inputs["calc.scaled"] + params.get("bonus", 0)}


class SemanticRightAdjustNode:
    NODE_INFO = NodeInfo(
        type_key="semantic.right_adjust",
        display_name="Semantic Right Adjust",
        category="semantic",
        description="Subtracts a configured penalty from calc.scaled after the right decision branch is selected.",
        version="0.1.0",
        flow_kind="process",
    )
    CONTRACT = NodeContract(
        requires=("calc.scaled",),
        provides=("calc.right_branch",),
        input_semantics={"calc.scaled": ("scaled arithmetic value selected for the right branch",)},
        output_semantics={"calc.right_branch": ("right branch value after subtracting penalty",)},
        params_schema={"penalty": {"type": "number"}},
        output_schema={"calc.right_branch": {"type": "number"}},
        examples=({"inputs": {"calc.scaled": 21}, "params": {"penalty": 6}},),
    )

    def run_pure(self, inputs, params):
        return {"calc.right_branch": inputs["calc.scaled"] - params.get("penalty", 0)}


class SemanticFinalizeNode:
    NODE_INFO = NodeInfo(
        type_key="semantic.finalize",
        display_name="Semantic Finalize",
        category="semantic",
        description="Adds a configured offset to calc.branch into calc.final.",
        version="0.1.0",
        flow_kind="process",
    )
    CONTRACT = NodeContract(
        requires=("calc.branch",),
        provides=("calc.final",),
        input_semantics={"calc.branch": ("branch or promoted scaled value to finalize",)},
        output_semantics={"calc.final": ("calc.branch plus offset",)},
        params_schema={"offset": {"type": "number"}},
        output_schema={"calc.final": {"type": "number"}},
        examples=({"inputs": {"calc.branch": 31}, "params": {"offset": 1}},),
    )

    def run_pure(self, inputs, params):
        return {"calc.final": inputs["calc.branch"] + params.get("offset", 0)}


class SemanticIncrementUntilNode:
    NODE_INFO = NodeInfo(
        type_key="semantic.increment_until",
        display_name="Semantic Increment Until",
        category="semantic",
        description="Adds a configured step to loop.current into loop.next.",
        version="0.1.0",
        flow_kind="process",
    )
    CONTRACT = NodeContract(
        requires=("loop.current",),
        provides=("loop.next",),
        input_semantics={"loop.current": ("current loop value before increment",)},
        output_semantics={"loop.next": ("loop.current plus step",)},
        params_schema={"step": {"type": "number"}},
        output_schema={"loop.next": {"type": "number"}},
        examples=({"inputs": {"loop.current": 1}, "params": {"step": 2}},),
    )

    def run_pure(self, inputs, params):
        return {"loop.next": inputs["loop.current"] + params.get("step", 1)}


class SemanticLoopDoneNode:
    NODE_INFO = NodeInfo(
        type_key="semantic.loop_done",
        display_name="Semantic Loop Done",
        category="semantic",
        description="Compares loop.next with target and emits loop.done for loop routing.",
        version="0.1.0",
        flow_kind="decision",
    )
    CONTRACT = NodeContract(
        requires=("loop.next",),
        provides=("loop.done",),
        input_semantics={"loop.next": ("candidate loop value after increment",)},
        output_semantics={"loop.done": ("true when loop.next is greater than or equal to target",)},
        params_schema={"target": {"type": "number"}},
        output_schema={"loop.done": {"type": "boolean"}},
        examples=(
            {"inputs": {"loop.next": 5}, "params": {"target": 7}},
            {"inputs": {"loop.next": 7}, "params": {"target": 7}},
        ),
    )

    def run_pure(self, inputs, params):
        return {"loop.done": inputs["loop.next"] >= params.get("target", 0)}


class SemanticCopyNextNode:
    NODE_INFO = NodeInfo(
        type_key="semantic.copy_next",
        display_name="Semantic Copy Next",
        category="semantic",
        description="Copies loop.next back into loop.current for the next loop iteration.",
        version="0.1.0",
        flow_kind="process",
    )
    CONTRACT = NodeContract(
        requires=("loop.next",),
        provides=("loop.current",),
        input_semantics={"loop.next": ("latest loop value to reuse",)},
        output_semantics={"loop.current": ("next loop iteration input",)},
        output_schema={"loop.current": {"type": "number"}},
        examples=({"inputs": {"loop.next": 3}, "params": {}},),
    )

    def run_pure(self, inputs, params):
        return {"loop.current": inputs["loop.next"]}


class SemanticScaledEndNode:
    NODE_INFO = NodeInfo(
        type_key="semantic.scaled_end",
        display_name="Semantic Scaled End",
        category="semantic",
        description="Terminates a nested semantic flow after calc.scaled is available.",
        version="0.1.0",
        flow_kind="terminal",
    )
    CONTRACT = NodeContract(
        requires=("calc.scaled",),
        input_semantics={"calc.scaled": ("scaled arithmetic output",)},
        examples=({"inputs": {"calc.scaled": 20}, "params": {}},),
    )

    def run_pure(self, inputs, params):
        return {}


class SemanticFinalEndNode:
    NODE_INFO = NodeInfo(
        type_key="semantic.final_end",
        display_name="Semantic Final End",
        category="semantic",
        description="Terminates a semantic flow after calc.final is available.",
        version="0.1.0",
        flow_kind="terminal",
    )
    CONTRACT = NodeContract(
        requires=("calc.final",),
        input_semantics={"calc.final": ("final arithmetic acceptance output",)},
        examples=({"inputs": {"calc.final": 17}, "params": {}},),
    )

    def run_pure(self, inputs, params):
        return {}


class SemanticLeftBranchEndNode:
    NODE_INFO = NodeInfo(
        type_key="semantic.left_branch_end",
        display_name="Semantic Left Branch End",
        category="semantic",
        description="Terminates a semantic branch flow after calc.left_branch is available.",
        version="0.1.0",
        flow_kind="terminal",
    )
    CONTRACT = NodeContract(
        requires=("calc.left_branch",),
        input_semantics={"calc.left_branch": ("final left branch arithmetic output",)},
        examples=({"inputs": {"calc.left_branch": 31}, "params": {}},),
    )

    def run_pure(self, inputs, params):
        return {}


class SemanticRightBranchEndNode:
    NODE_INFO = NodeInfo(
        type_key="semantic.right_branch_end",
        display_name="Semantic Right Branch End",
        category="semantic",
        description="Terminates a semantic branch flow after calc.right_branch is available.",
        version="0.1.0",
        flow_kind="terminal",
    )
    CONTRACT = NodeContract(
        requires=("calc.right_branch",),
        input_semantics={"calc.right_branch": ("final right branch arithmetic output",)},
        examples=({"inputs": {"calc.right_branch": 15}, "params": {}},),
    )

    def run_pure(self, inputs, params):
        return {}


class SemanticLoopEndNode:
    NODE_INFO = NodeInfo(
        type_key="semantic.loop_end",
        display_name="Semantic Loop End",
        category="semantic",
        description="Terminates a semantic loop after loop.next reaches the target.",
        version="0.1.0",
        flow_kind="terminal",
    )
    CONTRACT = NodeContract(
        requires=("loop.next",),
        input_semantics={"loop.next": ("final loop value",)},
        examples=({"inputs": {"loop.next": 7}, "params": {}},),
    )

    def run_pure(self, inputs, params):
        return {}
