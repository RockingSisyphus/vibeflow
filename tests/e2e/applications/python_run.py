"""A small application using source projects or deployable Python bundles."""
import json
import asyncio
import math
from pathlib import Path
import sys


class Batch:
    def __init__(self, items):
        self.items = items


class Model:
    def __init__(self, weight):
        self.weight = weight
    def loss(self, batch):
        return sum(batch.items) * self.weight
    def grad(self, loss):
        return loss / 10


class Optimizer:
    def __init__(self, lr):
        self.lr, self.steps = lr, 0
    def step(self, model, grad):
        model.weight -= self.lr * grad
        self.steps += 1


class Box:
    def __init__(self):self.value=2


class Counter:
    def __init__(self):self.steps=0


mode, path, request_path, run_root = sys.argv[1:]
request = json.loads(Path(request_path).read_text(encoding="utf-8"))
initial = request.get("initial", {})
factory = request.get("initial_factory")
if factory == "training":
    initial = {"train.model":Model(1.0), "train.batch":Batch([2,4]), "train.optimizer":Optimizer(.5)}
elif factory == "batch":
    initial = {"train.batch":Batch([2,4])}
elif factory == "callback":
    initial = {"callback.in":lambda:23}
elif factory == "objects":
    initial = {"object.box":Box(),"object.counter":Counter()}
elif factory == "formula":
    messages=asyncio.Queue()
    messages.put_nowait({"value":request["formula_value"]})
    received,sent=[],[]
    async def receive_port(value):
        received.append(dict(value))
        return await messages.get()
    def send_port(value):
        sent.append(dict(value))
    initial={**initial,"app_session":{"queue":{"receive":receive_port,"send":send_port}}}
options = request.get("runtime_options", {})
def json_value(value):
    if isinstance(value, (set, frozenset)):
        return sorted(value)
    if isinstance(value, (Model, Optimizer, Batch, Box, Counter)):
        return vars(value)
    raise TypeError(f"Unsupported application output: {type(value).__name__}")

try:
    if mode == "bundle":
        sys.path.insert(0, str(Path(path) / "_framework"))
        from vibeflow.tooling.application.python import load_bundle
        bundle=load_bundle(path)
        execute=bundle.run_async if request.get("mode")=="async" else bundle.run
        result = execute(initial, run_root=run_root, runtime_options=options,
            **({"entry":request["entry"]} if request.get("entry") else {}))
    else:
        from vibeflow.tooling.application.python import run_workspace_checked,run_workspace_checked_async
        from vibeflow.tooling.project.workspace_loader import load_workspace_config
        execute=run_workspace_checked_async if request.get("mode")=="async" else run_workspace_checked
        result = execute(path, workspace=load_workspace_config(request["workspace"]),
            initial=initial, run_root=run_root, runtime_options=options,
            **({"entry":request["entry"]} if request.get("entry") else {}))
    if request.get("mode")=="async":result=asyncio.run(result)
    public = result.public_outputs
    if factory == "batch" and "train.metrics" in public:
        public = dict(public)
        metrics = public.pop("train.metrics")
        public["application_metrics"] = {
            "items":sorted(metrics["items"]),
            "items_are_set":isinstance(metrics["items"], set),
            "unstable_is_nan":isinstance(metrics["unstable"], float) and math.isnan(metrics["unstable"]),
            "batch_returned":metrics["batch"] is initial["train.batch"],
            "batch_items":metrics["batch"].items}
    if factory == "training":
        # The caller receives its live business objects through the public API.
        public = dict(public)
        metrics = public.pop("train.metrics")
        public["application_metrics"] = {
            "loss":metrics["loss"],"tags":sorted(metrics["tags"]),
            "tags_are_set":isinstance(metrics["tags"], set),
            "unstable_is_nan":isinstance(metrics["unstable"], float) and math.isnan(metrics["unstable"]),
            "model_returned":metrics["model"] is initial["train.model"]}
        public["application_objects"] = {
            "model_returned":public.pop("train.model_after", None) is initial["train.model"],
            "optimizer_returned":public.pop("train.optimizer_after", None) is initial["train.optimizer"],
            "weight":initial["train.model"].weight,"steps":initial["train.optimizer"].steps}
    if factory == "objects":
        public=dict(public)
        metadata=public.pop("object.metadata")
        public["application_objects"]={"box_returned":public.pop("object.box_after") is initial["object.box"],
            "counter_returned":public.pop("object.counter_after") is initial["object.counter"],
            "nested_box_returned":metadata["box"] is initial["object.box"],
            "tags":sorted(metadata["tags"]),"unstable_is_nan":metadata["unstable"]!=metadata["unstable"],
            "value":initial["object.box"].value,"steps":initial["object.counter"].steps}
    if factory == "formula":
        public={**public,"application_ports":{"received":received,"sent":sent}}
    print("RESULT " + json.dumps({"outputs":public,"run_dir":str(result.run_dir),
        "health":{"status":result.health.status,"warnings":[item.code for item in result.health.warnings],
                  "errors":[item.code for item in result.health.errors]}}, ensure_ascii=False, default=json_value))
except Exception as error:
    print("FAILURE " + json.dumps({"type":type(error).__name__,"message":str(error),
        "code":getattr(error,"code",None)}, ensure_ascii=False))
    raise
