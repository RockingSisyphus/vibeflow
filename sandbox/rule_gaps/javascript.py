"""Real JS public-interface gap cases, preserving red expectations.

The current-only gap runner selects a kernel before calling run_cases. Normal
and negative cases use actual commands, workers, records and business execution.
"""
from __future__ import annotations
from tests.fixtures.support.plugins import resource as resource_ref

import importlib.util
import json
from pathlib import Path
import sys
from typing import Any


def _support():
    path = Path(__file__).with_name("javascript_support.py")
    spec = importlib.util.spec_from_file_location("vibeflow_js_gap_support", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _row(case_id: str, title: str, family: str, expected: dict[str, Any], actual: dict[str, Any], notes: str = "") -> dict[str, Any]:
    return {"id":"js.gaps."+case_id, "title":title, "family":family, "classification":"new_feature",
            "expected":expected, "actual":actual, "notes":notes}


def _result_states(payload: Any) -> dict[str, str]:
    if isinstance(payload, dict):
        results = payload.get("results", {})
        if isinstance(results, dict) and "provider" in results and "checker" in results:
            return {"provider_state":results["provider"]["state"], "consumer_state":results["checker"]["state"]}
        for value in payload.values():
            result = _result_states(value)
            if result:
                return result
    elif isinstance(payload, list):
        for value in payload:
            result = _result_states(value)
            if result:
                return result
    return {}


def _check_states(s, project, payload):
    states = _result_states(payload)
    if states:
        return states
    # A failing formal CLI currently publishes diagnostics rather than the
    # complete execution report. Verify states through the actual public Target
    # entrance with the same JSONC scope, not reconstructed/fake handler inputs.
    from vibeflow.targets.javascript.quality.rules import run_javascript_rules
    from vibeflow.tooling.project.descriptor_loader import load_workflow_catalogs
    from vibeflow.tooling.project.graph_config import parse_graph_config
    graph = parse_graph_config(s.read_json(project.config), project_root=project.project)
    catalogs = load_workflow_catalogs(project.project,workflow_config=project.config)
    report = run_javascript_rules(graph, catalogs, project_root=project.project, package_root=project.project, target="node")
    s.write_json(project.root / "target-state-report.json", report.to_dict())
    return {**_result_states(report.to_dict()), "state_probe":"public_target_api"}


def _record_cases(s, work: Path, tools: Path | None) -> list[dict[str, Any]]:
    values = (
        ("array", "[3]", [3]), ("empty", "[]", []), ("null", "null", None),
        ("object", '{nested:{count:3},values:[true,"value",null]}', {"nested":{"count":3},"values":[True,"value",None]}),
        ("async", "[3]", [3]), ("map", 'new Map([["answer",3]])', None),
        ("date", 'new Date("2026-01-01T00:00:00Z")', None), ("undefined", "undefined", None),
        ("nan", "NaN", None), ("infinity", "Infinity", None), ("bigint", "3n", None),
        ("cycle", "(()=>{const value={};value.self=value;return value;})()", None),
    )
    rows = []
    for name, expression, received in values:
        project = s.new_project(work, "record-"+name, tools)
        source = ('export '+('async ' if name=="async" else '')+'function check(){return {records:{value:{type_id:"'+s.VALUE_TYPE+'",value:'+expression+'}}};}\n')
        s.select_provider_and_consumer(project, source)
        actual, payload = s.command(project, "validate", "--json")
        actual["metrics"].update(_check_states(s,project,payload))
        valid = name in {"array", "empty", "null", "object", "async"}
        metrics = {"exit_code":0 if valid else 1, "consumer_executions":1 if valid else 0,
                   "provider_state":"completed" if valid else "failed", "consumer_state":"completed" if valid else "unavailable"}
        if valid:
            metrics["received"] = received
        expected = {"should_accept":valid, "metrics":metrics}
        if not valid:
            expected.update(codes=["RULE.EXECUTION", "RULE.INPUT.UNAVAILABLE"], located_codes=["RULE.EXECUTION"])
        rows.append(_row("records."+name, "真实 TS typed record 输出 "+name, "javascript.records.portability", expected, actual,
            "资料值违反公开 JsonValue 时必须失败，不能改写成合法空值再执行 consumer。" if not valid else "Consumer 实际收到该值；空值与 async handler 是合法对照。"))
    return rows


def _source_cases(s, work: Path, tools: Path | None) -> list[dict[str, Any]]:
    rows = []
    for kind in ("static", "dynamic", "require"):
        project = s.new_project(work, "source-"+kind, tools)
        helper = s.add_helper(project, kind)
        source = '''import {appendFileSync} from "node:fs";
export function check(context, inputs, params) {
  const file=context.facts.source_files[0], helper=HELPER;
  const edge=context.sources.imports(file).find(source=>source.resolved_path===helper);
  const proof={handler:"source-api", snapshot_has_helper:context.facts.sources.some(source=>source.path===helper),
    imports_has_helper:Boolean(edge), import_edge:edge??null,
    import_path:edge?.path??null, import_specifier:edge?.specifier??null,
    import_resolved_path:edge?.resolved_path??null, import_line:edge?.line??null,
    import_column:edge?.column??null, import_column_positive:Number.isInteger(edge?.column)&&edge.column>0,
    reachable_has_helper:context.sources.reachable(file).includes(helper),
    helper_owners:context.sources.ownership(helper).node_types,
    helper_declared:context.sources.ownership(helper).declared.map(owner=>owner.id)};
  appendFileSync(params.marker,JSON.stringify(proof)+"\\n");
  return {records:{value:{type_id:"gaps.value.v1",value:proof}}};
}
'''.replace("HELPER", json.dumps(str(helper)))
        s.select_provider_and_consumer(project, source)
        actual, _ = s.command(project, "validate", "--json")
        proof = next((item for item in project.events() if item.get("handler")=="source-api"), {})
        actual["metrics"].update({key:value for key,value in proof.items() if key!="handler"})
        source_path = project.project / "nodes" / ("calculation.js" if kind=="require" else "calculation.ts")
        # Derive the line from the written fixture text, independently of the
        # returned AST node kind (statement or import/require expression).
        import_line = next(index for index, line in enumerate(source_path.read_text().splitlines(), 1)
                           if '"./helper.js"' in line)
        expected = {"should_accept":True, "metrics":{"exit_code":0, "consumer_executions":1, "snapshot_has_helper":True,
                    "imports_has_helper":True, "import_path":str(source_path), "import_specifier":"./helper.js",
                    "import_resolved_path":str(helper), "import_line":import_line, "import_column_positive":True,
                    "reachable_has_helper":True, "helper_owners":["example.calculate"], "helper_declared":["gaps.helper"]}}
        if kind=="static":
            expected["metrics"]["import_column"] = 1
        rows.append(_row("sources."+kind, "Source API 实际 "+kind+" 导入与 helper 归属", "javascript.sources.graph", expected, actual,
            "同一实际 helper 必须同时出现在 Target snapshot、公开导入边、可达集合和 Node 归属中；边的文件、specifier 与实际源码行号须一致。动态调用列只要求正值，避免把表达式/语句的选择当成契约。声明归属单独断言。"))
    project = s.new_project(work, "source-missing-query", tools)
    missing = project.project / "nodes/missing.ts"
    s.select_provider_and_consumer(project, 'export function check(context){context.sources.text('+json.dumps(str(missing))+');return {records:{value:{type_id:"gaps.value.v1",value:[]}}};}\n')
    actual, payload = s.command(project, "validate", "--json")
    actual["metrics"].update(_check_states(s,project,payload))
    rows.append(_row("sources.missing", "Source API 查询不存在的文件不能提供虚假资料", "javascript.sources.availability",
        {"should_accept":False,"codes":["RULE.EXECUTION","RULE.INPUT.UNAVAILABLE"],"located_codes":["RULE.EXECUTION"],
         "metrics":{"exit_code":1,"consumer_executions":0,"provider_state":"failed","consumer_state":"unavailable"}}, actual))
    return rows


def _platform_cases(s, work: Path, tools: Path | None) -> list[dict[str, Any]]:
    rows = []
    for split in (False, True):
        label = "split" if split else "shared"
        project = s.new_project(work, "platform-"+label, tools)
        s.select_provider_and_consumer(project, 'export function check(){return {records:{value:{type_id:"gaps.value.v1",value:[3]}}};}\n')
        if split:
            descriptor = resource_ref(project.project, 'rule', 'example.number_provider')
            data = s.read_json(descriptor)
            data["implementations"] = []
            for target in ("node", "browser"):
                source = project.project / ("rules/provider-"+target+".ts")
                source.write_text('export function check(){return {records:{value:{type_id:"gaps.value.v1",value:[3]}}};}\n')
                data["implementations"].append({"language":"typescript",
                    "source":{"kind":"file","ref":source.relative_to(project.project).as_posix(),"export":"check"}})
            s.write_json(descriptor, data)
        for command in ("validate", "quality-check", "review"):
            before = len(project.events())
            options = ("--output", str(project.root / "review.svg")) if command=="review" else ("--json",)
            actual, _ = s.command(project, command, *options)
            actual["metrics"]["new_consumer_executions"] = len(project.events())-before
            actual["metrics"]["consumer_executed"] = actual["metrics"]["new_consumer_executions"] > 0
            if command=="review":
                svg = project.root / "review.svg"
                actual["metrics"]["published_svg"] = svg.is_file() and "<svg" in svg.read_text()
            expected = ({"should_accept":False,"codes":["DESCRIPTOR.INVALID"],"metrics":{"exit_code":1,"consumer_executed":False},"message_contains":"duplicate execution families"} if split else {"should_accept":True,"metrics":{"exit_code":0,"consumer_executed":True}})
            expected["metrics"]["consumer_executed"] = not split
            if command=="review":
                expected["metrics"]["published_svg"] = not split
            title = "重复 JS 执行族在正式 "+command+" 加载前被拒绝" if split else "共享 Rule 实现通过正式 "+command
            rows.append(_row("platform."+label+"."+command, title,
                "javascript.rule.platform_selection", expected, actual,
                "迁移：Rule 不再按业务平台选实现。共享实现正常加载；重复 JS 执行族在加载前明确拒绝。"))
        for target in ("node", "browser"):
            actual, payload = s.command(project,"build","--target",target,"--profile","single-esm","--out-dir",str(project.root/("dist-"+target)),label="build-"+target)
            actual["metrics"].update(s.execute_business(project,payload))
            title = "重复 JS 执行族阻止 "+target+" 构建" if split else "共享 Rule 实现构建 "+target+" 产物并执行业务"
            rows.append(_row("platform."+label+".build-"+target, title,
                "javascript.rule.platform_selection", ({"should_accept":False,"codes":["DESCRIPTOR.INVALID"],"metrics":{"exit_code":1,"business_executed":False}} if split else {"should_accept":True,"metrics":{"exit_code":0,"business_executed":True,"runtime_exit_code":0,"business_result":7}}), actual,
                "浏览器目标产物在 Node 中执行其无宿主依赖的数值入口；不声称进行了真实浏览器验收。"))
    return rows


def _sdk_cases(s, work: Path, tools: Path | None) -> list[dict[str, Any]]:
    rows = []
    project = s.new_project(work,"bundle-native-normal",tools)
    s.sdk_native_resources(project)
    actual, payload = s.command(project,"build","--target","node","--profile","single-esm","--out-dir",str(project.root/"dist"))
    if actual["metrics"]["exit_code"]==0:
        actual["metrics"].update(s.loaded_native_groups(project))
    actual["metrics"].update(s.execute_business(project,payload,host=True))
    rows.append(_row("bundle.native.normal", "SDK 所有原生资源真实 build/run 与生命周期", "javascript.bundle.native_resources",
        {"should_accept":True,"metrics":{"exit_code":0,"native_groups_loaded":True,"sdk_only":True,"business_executed":True,
         "runtime_exit_code":0,"business_result":7,"import_events":[],
         "lifecycle":["host:create","host:start","plugin:create","plugin:beforeRun","capability:offset","plugin:afterRun","plugin:dispose","host:stop"]}}, actual,
         "BaseLib、DataSchema、Capability、Host、Runtime Plugin 全部由同一 SDK 插件贡献，使用统一装配。"))
    for group in s.NATIVE_GROUPS:
        for failure in ("dangling", "conflict"):
            project = s.new_project(work,"bundle-"+group+"-"+failure,tools)
            paths = s.sdk_native_resources(project)
            original = paths[group]
            from tests.fixtures.support.plugins import write_plugin
            changed = project.project / "additional_plugin.ts"
            config = s.read_json(project.config)
            if failure=="conflict":
                data = s.read_json(original)
                if group=="data_schemas":
                    data["schema"]["minimum"] = 0
                elif group=="capabilities":
                    data["operations"]["offset"]["completion"] = "suspend"
                else:
                    data["description"] = "A conflicting contribution."
                selection = write_plugin(project.project, [data], target="javascript", filename=changed.name, plugin_id="gaps.additional")
            else:
                selection = {"source": {"kind":"file", "ref":changed.name, "export":"plugin"}}
            config["plugins"].append(selection)
            s.write_json(project.config, config)
            actual, _ = s.command(project,"build","--target","node","--profile","single-esm","--out-dir",str(project.root/"dist"))
            actual["metrics"].update(business_executed=False,build_published=(project.root/"dist").exists())
            origin_path = str(project.project / "code_plugin.ts")
            reason = [origin_path, '"origins"', '"previous"', '"current"'] if failure == "conflict" else [changed.name]
            rows.append(_row("bundle."+group+"."+failure, "Bundle "+group+" 的 "+failure+" 必须正式拒绝",
                "javascript.bundle.native_resources", {"should_accept":False,"codes":["DESCRIPTOR.CONFLICT" if failure=="conflict" else "PLUGIN.DECLARATION.LOAD"],
                 "message_contains":reason,"metrics":{"exit_code":1,"build_published":False,"business_executed":False}},actual,
                 "SDK migration: fixed code contributions replace bundle files; conflicts retain both actual declaration origins, and a missing direct import fails trusted plugin bootstrap."))
    return rows


def run_cases(work_root: Path, variant: str = "current", toolchain_root: Path | None = None) -> list[dict[str, Any]]:
    if variant!="current":
        raise ValueError("new Rule/API gaps have no legacy compatibility adapter; run the current kernel")
    work_root.mkdir(parents=True,exist_ok=True)
    support = _support()
    return [*_record_cases(support,work_root,toolchain_root), *_source_cases(support,work_root,toolchain_root),
            *_platform_cases(support,work_root,toolchain_root), *_sdk_cases(support,work_root,toolchain_root)]
