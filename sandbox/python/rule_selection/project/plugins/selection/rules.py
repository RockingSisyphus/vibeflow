from vibeflow.targets.python.sdk import rule

@rule(id="selection.analyze", level="graph", scope="call", params_schema={"label":{"type":"string"}}, params_defaults={"label":""}, outputs={"coverage":"selection.coverage"})
def analyze(context, inputs, params):
    value = {"label":params["label"], "phase":context.phase, "entry":list(context.subject["call_path"]),
        "graphs":[{"path":list(item["call_path"]), "nodes":[node.id for node in item["graph"].nodes]} for item in context.require("graphs")],
        "background_nodes":[node.id for node in context.require("global_graph").nodes]}
    return {"records":{"coverage":{"type_id":"selection.coverage", "value":value}}}

@rule(id="selection.graph_check", level="graph", scope="call", inputs={"coverage":"selection.coverage"})
def graph_check(context, inputs, params):
    return {"findings":[{"rule_id":"SELECTION.GRAPH", "severity":"warning", "object_type":"workflow",
        "object_id":"selection", "message":"Graph responsibility proof", "details":dict(inputs["coverage"].value)}]}

@rule(id="selection.local_check", scope="call")
def local_check(context, inputs, params):
    return {"findings":[{"rule_id":"SELECTION.LOCAL", "severity":"warning", "object_type":"node",
        "object_id":"selection.node", "message":"Local selection proof", "details":{
        "phase":context.phase, "path":list(context.subject["call_path"]),
        "forbidden":[key for key in ("graph","global_graph","node_catalog","catalogs") if key in context.facts]}}]}
