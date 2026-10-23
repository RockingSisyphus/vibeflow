"""Business arithmetic only; official Nodes own every cross-workflow operation."""
from vibeflow.targets.python.sdk import node




def value(inputs, kind):
    return inputs[kind]["value"]


@node(id="math.boundary", node_type="vibeflow.node", flow_kind="terminal", contract={}, rulesets=[])
class Boundary:
    def run_pure(self, inputs, params):
        return {}


@node(**{'id': 'math.seed', 'node_type': 'vibeflow.node', 'rulesets': ['vibeflow.process'], 'contract': {'requires': [{'type': 'math.x', 'cardinality': 'exactly_one', 'display_name': 'math.x'}, {'type': 'math.y', 'cardinality': 'exactly_one', 'display_name': 'math.y'}, {'type': 'math.case_id', 'cardinality': 'exactly_one', 'display_name': 'math.case_id'}], 'provides': [{'key': 'seed', 'type': 'math.seed', 'display_name': 'seed'}], 'input_semantics': {'math.x': ['Formula input'], 'math.y': ['Formula input'], 'math.case_id': ['Formula input']}, 'output_semantics': {'seed': ['Formula intermediate']}, 'params_schema': {'fault': {'type': 'string'}}, 'params_defaults': {'fault': ''}}})
class Seed:
    def run_pure(self, inputs, params, context):
        x, y = value(inputs, "math.x"), value(inputs, "math.y")
        return {"seed": dict(x=x, y=y, u=3*x+y, v=y-4, case_id=value(inputs, "math.case_id"),
                             a_id=context.workflow.self()["id"])}


@node(**{'id': 'math.request', 'node_type': 'vibeflow.node', 'rulesets': ['vibeflow.process'], 'contract': {'requires': [{'type': 'math.seed', 'cardinality': 'exactly_one', 'display_name': 'math.seed'}], 'provides': [{'key': 'request_payload', 'type': 'example.payload', 'display_name': 'request_payload'}], 'input_semantics': {'math.seed': ['Formula input']}, 'output_semantics': {'request_payload': ['Formula intermediate']}, 'params_schema': {'fault': {'type': 'string'}}, 'params_defaults': {'fault': ''}}})
class Request:
    def run_pure(self, inputs, params):
        seed = value(inputs, "math.seed")
        u, v = seed["u"], seed["v"]
        if params["fault"] == "swap":
            u, v = v, u
        if params["fault"] == "send_x":
            u = seed["x"]
        return {"request_payload": dict(phase="request", u=u, v=v, case_id=seed["case_id"])}


@node(**{'id': 'math.local', 'node_type': 'vibeflow.node', 'rulesets': ['vibeflow.process'], 'contract': {'requires': [{'type': 'math.seed', 'cardinality': 'exactly_one', 'display_name': 'math.seed'}], 'provides': [{'key': 'r', 'type': 'math.local', 'display_name': 'r'}], 'input_semantics': {'math.seed': ['Formula input']}, 'output_semantics': {'r': ['Formula intermediate']}, 'params_schema': {'fault': {'type': 'string'}}, 'params_defaults': {'fault': ''}}})
class Local:
    def run_pure(self, inputs, params):
        seed = value(inputs, "math.seed")
        return {"r": 7*seed["x"] - 3*seed["v"]}


@node(**{'id': 'math.continuation', 'node_type': 'vibeflow.node', 'rulesets': ['vibeflow.process'], 'contract': {'requires': [{'type': 'math.seed', 'cardinality': 'exactly_one', 'display_name': 'math.seed'}, {'type': 'math.local', 'cardinality': 'exactly_one', 'display_name': 'math.local'}, {'type': 'example.message', 'cardinality': 'exactly_one', 'display_name': 'example.message'}, {'type': 'example.instance', 'cardinality': 'exactly_one', 'display_name': 'example.instance'}], 'provides': [{'key': 'next_payload', 'type': 'example.payload', 'display_name': 'next_payload'}, {'key': 'checkpoint', 'type': 'math.checkpoint', 'display_name': 'checkpoint'}], 'input_semantics': {'math.seed': ['Formula input'], 'math.local': ['Formula input'], 'example.message': ['Formula input'], 'example.instance': ['Formula input']}, 'output_semantics': {'next_payload': ['Formula intermediate'], 'checkpoint': ['Formula intermediate']}, 'params_schema': {'fault': {'type': 'string'}}, 'params_defaults': {'fault': ''}}})
class Continuation:
    def run_pure(self, inputs, params):
        seed, message = value(inputs, "math.seed"), value(inputs, "example.message")
        reply, peer = message["payload"], value(inputs, "example.instance")
        assert message["sender"] == peer == reply["b_id"], "reply from wrong B instance"
        assert reply["a_id"] == seed["a_id"] and reply["case_id"] == seed["case_id"], "crossed calculation"
        assert reply["phase"] == "reply", "wrong message round"
        q = reply["b"] - value(inputs, "math.local")
        if params["fault"] == "skip_local":
            q = reply["b"]
        return {"next_payload": dict(phase="continuation", q=q, case_id=seed["case_id"]),
                "checkpoint": dict(reply, q=q)}


@node(**{'id': 'math.finish_a', 'node_type': 'vibeflow.node', 'rulesets': ['vibeflow.process'], 'contract': {'requires': [{'type': 'math.seed', 'cardinality': 'exactly_one', 'display_name': 'math.seed'}, {'type': 'math.local', 'cardinality': 'exactly_one', 'display_name': 'math.local'}, {'type': 'math.checkpoint', 'cardinality': 'exactly_one', 'display_name': 'math.checkpoint'}, {'type': 'example.result', 'cardinality': 'exactly_one', 'display_name': 'example.result'}, {'type': 'example.instance', 'cardinality': 'exactly_one', 'display_name': 'example.instance'}], 'provides': [{'key': 'answer', 'type': 'math.answer', 'display_name': 'answer'}], 'input_semantics': {'math.seed': ['Formula input'], 'math.local': ['Formula input'], 'math.checkpoint': ['Formula input'], 'example.result': ['Formula input'], 'example.instance': ['Formula input']}, 'output_semantics': {'answer': ['Formula intermediate']}, 'params_schema': {'fault': {'type': 'string'}}, 'params_defaults': {'fault': ''}}})
class FinishA:
    def run_pure(self, inputs, params):
        seed, checkpoint = value(inputs, "math.seed"), value(inputs, "math.checkpoint")
        terminal = value(inputs, "example.result")
        assert terminal["id"] == value(inputs, "example.instance") and terminal["state"] == "succeeded", terminal
        ended = terminal["outputs"]["computed"]
        assert ended["case_id"] == seed["case_id"] and ended["q"] == checkpoint["q"], "wrong terminal output"
        d = ended["d"]
        result = 3*(checkpoint["b"] if params["fault"] == "early_result" else d) + seed["u"]
        return {"answer": {"result": result, "case_id": seed["case_id"],
            "identities": {"a": seed["a_id"], "b": checkpoint["b_id"], "c": checkpoint["c_id"]},
            "stages": {"u": seed["u"], "v": seed["v"], "p": checkpoint["p"], "b": checkpoint["b"],
                       "r": value(inputs, "math.local"), "q": checkpoint["q"], "d": d}}}


@node(**{'id': 'math.unpack', 'node_type': 'vibeflow.node', 'rulesets': ['vibeflow.process'], 'contract': {'requires': [{'type': 'example.message', 'cardinality': 'exactly_one', 'display_name': 'example.message'}], 'provides': [{'key': 'request', 'type': 'math.request', 'display_name': 'request'}, {'key': 'sync_payload', 'type': 'example.payload', 'display_name': 'sync_payload'}], 'input_semantics': {'example.message': ['Formula input']}, 'output_semantics': {'request': ['Formula intermediate'], 'sync_payload': ['Formula intermediate']}, 'params_schema': {'fault': {'type': 'string'}}, 'params_defaults': {'fault': ''}}})
class Unpack:
    def run_pure(self, inputs, params):
        message = value(inputs, "example.message")
        request = message["payload"]
        assert request["phase"] == "request", "wrong message round"
        request = dict(request, a_id=message["sender"])
        return {"request": request, "sync_payload": {"request": request}}


@node(**{'id': 'math.reply', 'node_type': 'vibeflow.node', 'rulesets': ['vibeflow.process'], 'contract': {'requires': [{'type': 'math.request', 'cardinality': 'exactly_one', 'display_name': 'math.request'}, {'type': 'example.result', 'cardinality': 'exactly_one', 'display_name': 'example.result'}], 'provides': [{'key': 'reply', 'type': 'math.reply', 'display_name': 'reply'}, {'key': 'reply_payload', 'type': 'example.payload', 'display_name': 'reply_payload'}, {'key': 'instance', 'type': 'example.instance', 'display_name': 'instance'}], 'input_semantics': {'math.request': ['Formula input'], 'example.result': ['Formula input']}, 'output_semantics': {'reply': ['Formula intermediate'], 'reply_payload': ['Formula intermediate'], 'instance': ['Formula intermediate']}, 'params_schema': {'fault': {'type': 'string'}}, 'params_defaults': {'fault': ''}}})
class Reply:
    def run_pure(self, inputs, params, context):
        request, computed = value(inputs, "math.request"), value(inputs, "example.result")["computed"]
        assert computed["case_id"] == request["case_id"], "wrong synchronous result"
        reply = dict(phase="reply", case_id=request["case_id"], p=computed["p"], b=2*computed["p"]-request["u"],
                     a_id=request["a_id"], b_id=context.workflow.self()["id"], c_id=computed["c_id"])
        assert len({reply["a_id"], reply["b_id"], reply["c_id"]}) == 3, "shared workflow identity"
        return {"reply": reply, "reply_payload": reply, "instance": request["a_id"]}


@node(**{'id': 'math.finish_b', 'node_type': 'vibeflow.node', 'rulesets': ['vibeflow.process'], 'contract': {'requires': [{'type': 'math.request', 'cardinality': 'exactly_one', 'display_name': 'math.request'}, {'type': 'math.reply', 'cardinality': 'exactly_one', 'display_name': 'math.reply'}, {'type': 'example.message', 'cardinality': 'exactly_one', 'display_name': 'example.message'}], 'provides': [{'key': 'answer', 'type': 'math.answer', 'display_name': 'answer'}], 'input_semantics': {'math.request': ['Formula input'], 'math.reply': ['Formula input'], 'example.message': ['Formula input']}, 'output_semantics': {'answer': ['Formula intermediate']}, 'params_schema': {'fault': {'type': 'string'}}, 'params_defaults': {'fault': ''}}})
class FinishB:
    def run_pure(self, inputs, params):
        request, reply, message = (value(inputs, key) for key in ("math.request", "math.reply", "example.message"))
        continuation = message["payload"]
        assert message["sender"] == reply["a_id"] and continuation["case_id"] == request["case_id"], "crossed continuation"
        assert continuation["phase"] == "continuation", "wrong message round"
        return {"answer": dict(case_id=request["case_id"], q=continuation["q"], d=continuation["q"]+2*request["v"])}


@node(id="math.second_seed", node_type="vibeflow.node", rulesets=["vibeflow.process"], contract={
    "requires": [{"type": "math.request", "cardinality": "exactly_one", "display_name": "Request"},
                 {"type": "math.reply", "cardinality": "exactly_one", "display_name": "Reply"}],
    "provides": [{"key": "request_forward", "type": "math.request", "display_name": "Request"},
                 {"key": "reply_forward", "type": "math.reply", "display_name": "Reply"}],
    "input_semantics": {"math.request": ["First round input"], "math.reply": ["First round result"]},
    "output_semantics": {"request_forward": ["Retained input"], "reply_forward": ["Retained result"]}})
class SecondSeed:
    def run_pure(self, inputs, params):
        return {"request_forward": value(inputs, "math.request"), "reply_forward": value(inputs, "math.reply")}


@node(**{'id': 'math.shift', 'node_type': 'vibeflow.node', 'rulesets': ['vibeflow.process'], 'contract': {'requires': [{'type': 'math.request', 'cardinality': 'exactly_one', 'display_name': 'math.request'}], 'provides': [{'key': 'shift', 'type': 'math.shift', 'display_name': 'shift'}], 'input_semantics': {'math.request': ['Formula input']}, 'output_semantics': {'shift': ['Formula intermediate']}, 'params_schema': {'fault': {'type': 'string'}}, 'params_defaults': {'fault': ''}}})
class Shift:
    def run_pure(self, inputs, params, context):
        request = value(inputs, "math.request")
        return {"shift": dict(request, t=request["u"]-2*request["v"], c_id=context.workflow.self()["id"])}


@node(**{'id': 'math.square', 'node_type': 'vibeflow.node', 'rulesets': ['vibeflow.process'], 'contract': {'requires': [{'type': 'math.shift', 'cardinality': 'exactly_one', 'display_name': 'math.shift'}], 'provides': [{'key': 'square', 'type': 'math.square', 'display_name': 'square'}], 'input_semantics': {'math.shift': ['Formula input']}, 'output_semantics': {'square': ['Formula intermediate']}, 'params_schema': {'fault': {'type': 'string'}}, 'params_defaults': {'fault': ''}}})
class Square:
    def run_pure(self, inputs, params):
        shifted = value(inputs, "math.shift")
        return {"square": dict(shifted, s=shifted["t"]**2)}


@node(**{'id': 'math.bias', 'node_type': 'vibeflow.node', 'rulesets': ['vibeflow.process'], 'contract': {'requires': [{'type': 'math.square', 'cardinality': 'exactly_one', 'display_name': 'math.square'}], 'provides': [{'key': 'answer', 'type': 'math.answer', 'display_name': 'answer'}], 'input_semantics': {'math.square': ['Formula input']}, 'output_semantics': {'answer': ['Formula intermediate']}, 'params_schema': {'fault': {'type': 'string'}}, 'params_defaults': {'fault': ''}}})
class Bias:
    def run_pure(self, inputs, params):
        squared = value(inputs, "math.square")
        return {"answer": dict(p=squared["s"]+5*squared["v"], case_id=squared["case_id"], c_id=squared["c_id"])}
