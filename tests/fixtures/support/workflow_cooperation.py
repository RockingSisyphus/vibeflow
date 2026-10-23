"""Shared real-project graphs and independent numeric oracle for both Targets."""
from copy import deepcopy
import json
from pathlib import Path
import shutil

from .artifacts import artifact_directory


CASES = [
    {"x": x, "y": y, "case_id": f"case-{index}"}
    for index, (x, y) in enumerate(((2, 7), (5, 1), (0, 0), (-4, 3), (.5, -1.25)))
]
CANCEL_CASE = {**CASES[0], "case_id":"case-cancelled", "stop":True}
FAULTS = {"swap": 3631, "send_x": 196, "skip_local": 376, "early_result": 358}


def reference(name):
    return {"root": "cooperation", "path": f"configs/{name}.jsonc", "entry": "calculate"}


def expected(case):
    x, y = case["x"], case["y"]
    # Expanded independently of the distributed, factored computation.
    return 54*x*x - 36*x*y + 6*y*y + 261*x - 53*y + 204


def verify_rows(rows):
    assert len(rows) == len(CASES), rows
    identities = []
    for case, row in zip(CASES, rows):
        assert row["result"] == expected(case), (case, row)
        assert row["case_id"] == case["case_id"], (case, row)
        ids = row["identities"]
        assert len(set(ids.values())) == 3, ids
        identities.extend(ids.values())
        x, y = case["x"], case["y"]
        u, v = 3*x+y, y-4
        p = (u-2*v)**2 + 5*v
        b, r = 2*p-u, 7*x-3*v
        assert row["stages"] == {"u": u, "v": v, "p": p, "b": b, "r": r,
                                  "q": b-r, "d": b-r+2*v}, row
    assert len(set(identities)) == 3*len(CASES), identities


def verify_cancelled(row):
    assert row["case_id"] == CANCEL_CASE["case_id"] and row["status"] == "cancelled", row
    assert row["cleanup"] == "finished" and len(set(row["identities"].values())) == 3, row
    assert not ({"result", "d", "stages"} & set(row)), row


def graphs(language):
    suffix = "py" if language == "python" else "mjs"
    plugins = [{"source": {"kind": "file", "ref": f"plugins/{package}/{name}.{suffix}"}}
               for package, name in (("workflow_protocol", "protocol"), ("math", "plugin"))]

    def node(key, definition=None, **config):
        value = {"id": key, "definition_id": definition or f"math.{key}",
                 "display_name": key, "description": f"Cooperative formula: {key}"}
        if config:
            value["config"] = config
        return value

    def graph(mode, nodes, wires, inputs=()):
        nodes = [node("start", "math.boundary"), *nodes, node("end", "math.boundary")]
        # Schedule and data are explicit: repeated Send/Receive templates must
        # consume the right round, never an earlier same-typed payload.
        edges = [{"from": a["id"], "to": b["id"], "transfer": False}
                 for a, b in zip(nodes, nodes[1:])]
        edges += [{"from": a, "to": b, "schedule": False} for a, b in wires]
        return {"plugins": deepcopy(plugins), "rulesets": [], "pipeline": {
            "entry_mode": mode, "entries": {"calculate": {"start": "start"}},
            "inputs": [{"key": key, "type": kind, "display_name": key, "required": True}
                       for key, kind in inputs],
            "nodes": nodes, "edges": edges,
            "outputs": [{"type": "math.answer", "as": "computed", "display_name": "Computed value",
                         "cardinality": "exactly_one"}]}}

    normal = graph("async", [node("normal_seed"), node("continuation"),
        node("send_next", "example.send", expected_workflows=[reference("b")]),
        node("wait", "example.wait"), node("finish_a")],
        [("normal_seed",target) for target in ("continuation","send_next","wait","finish_a")] +
        [("continuation","send_next"),("continuation","finish_a"),("wait","finish_a")],
        [("seed","math.seed"),("local","math.local"),("reply","example.message"),("instance","example.instance")])["pipeline"]
    normal.pop("entries")
    normal["outputs"][0]["as"] = "normal_answer"
    a = graph("async", [node("seed"),
        node("call", "example.call", workflow=reference("b"), launch={"kind":"in_process"}),
        node("request"), node("send_request", "example.send", expected_workflows=[reference("b")]),
        node("local"), node("receive_reply", "example.receive", expected_workflows=[reference("b")]),
        node("choose"), node("finish_normal", "math.normal_round"),
        node("ready_to_kill", expected_workflows=[reference("b")]),
        node("kill", "example.kill", workflow=reference("b")), node("cancelled", expected_workflows=[reference("b")])],
        [("seed","request"),("request","send_request"),("call","send_request"),("seed","local"),
         ("seed","choose"),("seed","finish_normal"),("local","finish_normal"),
         ("receive_reply","finish_normal"),("call","finish_normal"),("call","ready_to_kill"),
         ("seed","ready_to_kill"),("call","kill"),("seed","cancelled"),("kill","cancelled")],
        [("x","math.x"),("y","math.y"),("case_id","math.case_id")])
    a["pipeline"]["inputs"].append({"key":"stop", "type":"math.stop", "required":False, "display_name":"Cancel after first reply"})
    a["pipeline"]["edges"] = [edge for edge in a["pipeline"]["edges"]
        if not (edge["from"],edge["to"]) in {("choose","finish_normal"),("finish_normal","ready_to_kill")}]
    a["pipeline"]["edges"] += [
        {"from":"choose","to":"finish_normal","when":"stop_route == false","transfer":False},
        {"from":"choose","to":"ready_to_kill","when":"stop_route == true","transfer":False},
        {"from":"finish_normal","to":"end","transfer":False}]
    a["nodeset_types"] = [{"type_key":"math.normal_round", "display_name":"Normal completion",
        "description":"Send the continuation, wait for B and compute the original formula.", "rulesets":[],
        "requires":[{"type":kind,"cardinality":"exactly_one","display_name":kind}
                    for kind in ("math.seed","math.local","example.message","example.instance")],
        "provides":[{"key":"normal_answer","type":"math.answer","display_name":"Formula result"}], "pipeline":normal}]
    b = graph("async", [
        node("receive_request", "example.receive", expected_workflows=[reference("a")]),
        node("unpack"), node("invoke", "example.invokesync", workflow=reference("c")),
        node("reply"), node("send_reply", "example.send", expected_workflows=[reference("a")]),
        node("second_round", "math.second_round")],
        [("receive_request", "unpack"), ("unpack", "invoke"), ("unpack", "reply"),
         ("invoke", "reply"), ("reply", "send_reply"), ("unpack", "second_round"),
         ("reply", "second_round")])
    second = graph("async", [node("second_seed"),
        node("receive_next", "math.receive_next", expected_workflows=[reference("a")]), node("finish_b")],
        [("second_seed", "finish_b"), ("second_seed", "receive_next"), ("receive_next", "finish_b")],
        [("request", "math.request"), ("reply", "math.reply")])["pipeline"]
    second.pop("entries")
    second["outputs"][0]["as"] = "answer"
    b["nodeset_types"] = [{"type_key": "math.second_round", "display_name": "Second round",
        "description": "Receive A's continuation and compute d=q+2v in the same B instance.", "rulesets": [],
        "requires": [{"type": kind, "cardinality": "exactly_one", "display_name": kind}
                     for kind in ("math.request", "math.reply")],
        "provides": [{"key": "answer", "type": "math.answer", "display_name": "Final B result"}],
        "pipeline": second}]
    c = graph("sync", [node("shift"), node("square"), node("bias")],
              [("shift", "square"), ("square", "bias")], [("request", "math.request")])
    return {"a": a, "b": b, "c": c}


def prepare(fixture, work, language, toolchain=None):
    """Use the shipped official Node templates without maintaining test copies."""
    from distribution.build import _copy_coordination_templates
    work = Path(work)
    shutil.copytree(fixture / "project", work / "project")
    (work / "vibeflow_config.jsonc").write_text(json.dumps({
        "roots": [{"id": "cooperation", "path": "project"}]}), encoding="utf-8")
    (work / "project/root_rules.jsonc").write_text('{"rulesets":[]}', encoding="utf-8")
    output = artifact_directory(work)
    _copy_coordination_templates(output / "templates")
    templates = output / "templates/kernel/templates/workflow_nodes"
    suffix = "py" if language == "python" else "mjs"
    shutil.copy2(templates / f"nodes.{suffix}", work / f"project/nodes/nodes.{suffix}")
    plugin = work / "project/plugins/workflow_protocol"
    plugin.mkdir(parents=True)
    shutil.copy2(templates / f"protocol.{suffix}", plugin / f"protocol.{suffix}")
    if language == "javascript":
        shutil.copy2(templates / "interfaces.mjs", plugin / "interfaces.mjs")
        (work / "project/node_modules").symlink_to(Path(toolchain).resolve() / "node_modules", target_is_directory=True)
        shutil.copy2(Path(toolchain) / "package-lock.json", work / "project/package-lock.json")
    configs = work / "project/configs"
    configs.mkdir()
    for name, data in graphs(language).items():
        write_graph(configs, name, data)
    return output


def write_graph(configs, name, data):
    data = deepcopy(data)
    for definition in data.pop("nodeset_types", ()):
        directory = configs / "nodeset_types"
        directory.mkdir(exist_ok=True)
        filename = definition["type_key"].split(".")[-1] + ".jsonc"
        data.setdefault("nodeset_imports", []).append({"path":"nodeset_types/"+filename})
        (directory / filename).write_text(json.dumps(definition, indent=2)+"\n", encoding="utf-8")
    (configs / f"{name}.jsonc").write_text(json.dumps(data, indent=2)+"\n", encoding="utf-8")


def set_fault(work, language, fault):
    data = graphs(language)["a"]
    key = "request" if fault in {"swap", "send_x"} else "continuation" if fault == "skip_local" else "finish_a"
    nodes = data["pipeline"]["nodes"] + [node for definition in data.get("nodeset_types", ())
        for node in definition["pipeline"]["nodes"]]
    next(item for item in nodes if item["id"] == key)["config"] = {"fault": fault}
    write_graph(work / "project/configs", "a", data)
