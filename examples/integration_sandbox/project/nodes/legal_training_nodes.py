from __future__ import annotations

from vibeflow import NodeContract, NodeInfo


class TrainingInputNode:
    NODE_INFO = NodeInfo("sandbox.training_input", "Training Input", "training", "Reads model, batch, and optimizer objects.", "0.1.0", "io")
    CONTRACT = NodeContract(
        requires=("train.model", "train.batch", "train.optimizer"),
        input_semantics={
            "train.model": ("arbitrary model object",),
            "train.batch": ("arbitrary batch object",),
            "train.optimizer": ("arbitrary optimizer object",),
        },
        examples=({"inputs": {"train.model": {}, "train.batch": {}, "train.optimizer": {}}, "params": {}, "outputs": {}},),
    )

    def run_pure(self, inputs, params):
        return {}


class ForwardLossNode:
    NODE_INFO = NodeInfo("sandbox.forward_loss", "Forward Loss", "training", "Computes a loss from model and batch objects.", "0.1.0", "process")
    CONTRACT = NodeContract(
        requires=("train.model", "train.batch"),
        provides=("train.loss",),
        input_semantics={"train.model": ("model object",), "train.batch": ("batch object",)},
        output_semantics={"train.loss": ("numeric loss",)},
        output_schema={"train.loss": {"type": "number"}},
        examples=({"inputs": {"train.model": {}, "train.batch": {}}, "params": {}, "outputs": {"train.loss": 1}},),
    )

    def run_pure(self, inputs, params):
        model = inputs["train.model"]
        if not hasattr(model, "loss"):
            return {"train.loss": 1}
        return {"train.loss": model.loss(inputs["train.batch"])}


class BackwardGradNode:
    NODE_INFO = NodeInfo("sandbox.backward_grad", "Backward Grad", "training", "Computes a gradient from the loss.", "0.1.0", "process")
    CONTRACT = NodeContract(
        requires=("train.model", "train.loss"),
        provides=("train.grad",),
        input_semantics={"train.model": ("model object",), "train.loss": ("numeric loss",)},
        output_semantics={"train.grad": ("numeric gradient",)},
        output_schema={"train.grad": {"type": "number"}},
        examples=({"inputs": {"train.model": {}, "train.loss": 1}, "params": {}, "outputs": {"train.grad": 0.1}},),
    )

    def run_pure(self, inputs, params):
        model = inputs["train.model"]
        if not hasattr(model, "grad"):
            return {"train.grad": 0.1}
        return {"train.grad": model.grad(inputs["train.loss"])}


class OptimizerStepNode:
    NODE_INFO = NodeInfo("sandbox.optimizer_step", "Optimizer Step", "training", "Mutates model through an optimizer and returns the same objects.", "0.1.0", "process")
    CONTRACT = NodeContract(
        requires=("train.model", "train.optimizer", "train.grad"),
        provides=("train.model_after", "train.optimizer_after", "train.step_report"),
        input_semantics={
            "train.model": ("model object",),
            "train.optimizer": ("optimizer object",),
            "train.grad": ("numeric gradient",),
        },
        output_semantics={
            "train.model_after": ("same model object after step",),
            "train.optimizer_after": ("same optimizer object after step",),
            "train.step_report": ("small JSON-safe training report",),
        },
        output_schema={
            "train.model_after": {"type": "object", "snapshot": "opaque"},
            "train.optimizer_after": {"type": "object", "snapshot": "opaque"},
            "train.step_report": {"type": "object"},
        },
        examples=(
            {
                "inputs": {"train.model": {}, "train.optimizer": {}, "train.grad": 0.1},
                "params": {},
                "outputs": {"train.model_after": {}, "train.optimizer_after": {}, "train.step_report": {"steps": 1}},
            },
        ),
    )

    def run_pure(self, inputs, params):
        model = inputs["train.model"]
        optimizer = inputs["train.optimizer"]
        if not hasattr(optimizer, "step"):
            return {"train.model_after": model, "train.optimizer_after": optimizer, "train.step_report": {"steps": 1}}
        optimizer.step(model, inputs["train.grad"])
        return {
            "train.model_after": model,
            "train.optimizer_after": optimizer,
            "train.step_report": {"steps": optimizer.steps, "weight": model.weight},
        }


class TrainingMetricsNode:
    NODE_INFO = NodeInfo("sandbox.training_metrics", "Training Metrics", "training", "Emits non-JSON metrics without snapshotting values.", "0.1.0", "process")
    CONTRACT = NodeContract(
        requires=("train.model_after", "train.loss"),
        provides=("train.metrics",),
        input_semantics={"train.model_after": ("model object",), "train.loss": ("numeric loss",)},
        output_semantics={"train.metrics": ("metrics object containing non-JSON values",)},
        output_schema={"train.metrics": {"type": "object", "snapshot": "opaque"}},
        examples=(
            {
                "inputs": {"train.model_after": {}, "train.loss": 1},
                "params": {},
                "outputs": {"train.metrics": {"loss": 1, "tags": ["train"]}},
            },
        ),
    )

    def run_pure(self, inputs, params):
        model = inputs["train.model_after"]
        if not hasattr(model, "weight"):
            return {"train.metrics": {"loss": inputs["train.loss"], "tags": ["train"]}}
        return {
            "train.metrics": {
                "loss": inputs["train.loss"],
                "tags": {"sandbox", "train"},
                "unstable": float("nan"),
                "model": model,
            }
        }


class BatchMetricsNode:
    NODE_INFO = NodeInfo("sandbox.batch_metrics", "Batch Metrics", "training", "Emits metrics directly from a non-JSON batch object.", "0.1.0", "process")
    CONTRACT = NodeContract(
        requires=("train.batch",),
        provides=("train.metrics",),
        input_semantics={"train.batch": ("batch object",)},
        output_semantics={"train.metrics": ("non-JSON metrics",)},
        output_schema={"train.metrics": {"type": "object", "snapshot": "opaque"}},
        examples=({"inputs": {"train.batch": {}}, "params": {}, "outputs": {"train.metrics": {"size": 1}}},),
    )

    def run_pure(self, inputs, params):
        batch = inputs["train.batch"]
        if isinstance(batch, dict):
            return {"train.metrics": {"size": 1}}
        items = batch.items if hasattr(batch, "items") and not isinstance(batch, dict) else [1]
        return {"train.metrics": {"items": set(items), "unstable": float("nan"), "batch": batch}}


class SnapshotUnsafeMetricsNode:
    NODE_INFO = NodeInfo("sandbox.snapshot_unsafe_metrics", "Snapshot Unsafe Metrics", "training", "Emits non-JSON metrics without opaque snapshot opt-out.", "0.1.0", "process")
    CONTRACT = NodeContract(
        requires=("train.batch",),
        provides=("train.metrics",),
        input_semantics={"train.batch": ("batch object",)},
        output_semantics={"train.metrics": ("non-JSON metrics",)},
        output_schema={"train.metrics": {"type": "object"}},
        examples=({"inputs": {"train.batch": {}}, "params": {}, "outputs": {"train.metrics": {"size": 1}}},),
    )

    def run_pure(self, inputs, params):
        batch = inputs["train.batch"]
        items = batch.items if hasattr(batch, "items") and not isinstance(batch, dict) else [1]
        return {"train.metrics": {"items": set(items), "unstable": float("nan")}}


class TrainingMetricsEndNode:
    NODE_INFO = NodeInfo("sandbox.training_metrics_end", "Training Metrics End", "training", "Ends after training metrics are available.", "0.1.0", "terminal")
    CONTRACT = NodeContract(
        requires=("train.metrics",),
        input_semantics={"train.metrics": ("training metrics",)},
        examples=({"inputs": {"train.metrics": {"loss": 1}}, "params": {}, "outputs": {}},),
    )

    def run_pure(self, inputs, params):
        return {}
