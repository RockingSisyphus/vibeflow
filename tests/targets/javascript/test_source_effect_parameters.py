"""Selected SDK Rules drive the same parameters through native JS analysis."""

import json

import pytest

from tests.fixtures.support.plugins import resource
from tests.targets.javascript.test_domain_rules import domain_project
from vibeflow.core.flow import GraphConfig, NodeSpec
from vibeflow.core.rules import RuleContext
from vibeflow.targets.javascript.build.driver_session import DriverScope
from vibeflow.targets.javascript.build.analysis_service import JavascriptAnalysis
from vibeflow.targets.javascript.rules.plugin import javascript_rule_bindings
from vibeflow.targets.javascript.build.project_resources import target_neutral_import_policy
from vibeflow.targets.javascript.quality.rules import run_javascript_rules
from vibeflow.tooling.project.descriptor_loader import load_workflow_catalogs


def _review(project, *, hosts=frozenset()):
    catalogs = load_workflow_catalogs(project, project_config=project / "vibeflow_project.jsonc",
                                     workflow_config=project / "configs/model.jsonc")
    policy, _ = target_neutral_import_policy(catalogs=catalogs, project_root=project,
                                             allowed_external=set(), node_ids=frozenset({"example.transform"}), host_extension_ids=hosts)
    return run_javascript_rules(GraphConfig(nodes=(NodeSpec("transform", "example.transform"),), rulesets=()),
                                catalogs, project_root=project, package_root=project, target="node", import_policy=policy)


def _select(project, params, body, *, entrypoint="static"):
    source = project / "nodes/transform.ts"
    source.write_text('export function run() {' + body + ' return {output:7}; }\n')
    node = resource(project, "node", "example.transform")
    descriptor = json.loads(node.read_text())
    descriptor["rulesets"] = ["test.effect_parameters"]
    node.write_text(json.dumps(descriptor))
    calls = [{"id":"effects", "rule_id":"vibeflow.no_side_effects", "params":params},
             {"id":"imports", "rule_id":"vibeflow.import_side_effects", "params":params}]
    resource(project, "ruleset", "test.effect_parameters").write_text(json.dumps({
        "kind":"ruleset", "id":"test.effect_parameters", "calls":calls,
        "entrypoints":{"import":[] if entrypoint == "effects_only" else ["imports"],
                       "static":[] if entrypoint == "import_only" else ["effects"], "run":[]}}))
    return source


@pytest.mark.parametrize("scope,denied", [
    ("none", {"console", "fetch"}), ("terminal", {"fetch"}), ("python_io", set()),
    ("global_state", {"console", "fetch"}), ("trusted", {"console", "fetch"}),
])
def test_sdk_scope_selects_effect_categories_with_real_node_identity(domain_project, scope, denied, monkeypatch):
    workspace, project = domain_project
    params = {"effect_scope":scope, "policy":{}}
    source = _select(project, params, 'console.log("hello"); void fetch("https://example.invalid");')
    import vibeflow.targets.javascript.build.analysis_service as service
    original = service.run_rule_check_driver
    requests = []
    def record(request, **kwargs):
        requests.append(request)
        return original(request, **kwargs)
    monkeypatch.setattr(service, "run_rule_check_driver", record)
    report = _review(project)
    found = [item for item in report.findings if item.definition_id == "vibeflow.no_side_effects" and item.source_location.get("path") == str(source)]
    assert len(found) == len(denied), found
    assert all(any(name in item.message for name in denied) for item in found)
    assert all(item.details["source_owner"]["kind"] == "node" and item.message.startswith("node '") for item in found)
    selected = [item for item in requests if item.get("ruleSubjectId") == "example.transform" and "host_io" in item.get("ruleTopics", ())]
    assert selected and all(item["ruleParams"] == params for item in selected)
    assert all("ownership" not in item.get("ruleTopics", ()) for item in requests)
    assert all("effectScope" not in item.details["source_owner"] for item in found)


@pytest.mark.parametrize("scope", ["none", "terminal", "python_io", "global_state", "trusted"])
def test_builtin_prototype_mutation_stays_forbidden_for_every_scope(domain_project, scope):
    workspace, project = domain_project
    _select(project, {"effect_scope":scope, "policy":{}}, '(Array.prototype as any).evil = () => 1;')
    report = _review(project)
    assert any(item.definition_id == "vibeflow.no_side_effects" and item.code == "VF_MODULE_STATE" for item in report.findings)


@pytest.mark.parametrize("slot", ['"probeAdapter"', 'key'])
@pytest.mark.parametrize("scope,denied", [("python_io", False), ("none", True), ("terminal", True)])
def test_host_slot_read_and_local_alias_follow_effect_scope(domain_project, slot, scope, denied):
    _, project = domain_project
    _select(project, {"effect_scope": scope, "policy": {}},
            'const key = String(7); const candidate = (globalThis as Record<string, unknown>)['
            + slot + ']; const alias = candidate; void alias;')
    report = _review(project)
    assert bool([item for item in report.findings if item.code == "VF_BASE_LIB_HOST_IO"]) == denied


@pytest.mark.parametrize("body", [
    'const candidate = globalThis.process; candidate.exit(0);',
    'const key = String(7); const candidate = (globalThis as any)[key]; candidate.prototype.evil = 1;',
])
def test_host_slot_permission_keeps_process_and_prototype_protections(domain_project, body):
    _, project = domain_project
    _select(project, {"effect_scope": "python_io", "policy": {}}, body)
    assert any(item.code in {"VF_BASE_LIB_HOST_IO", "VF_MODULE_STATE"} for item in _review(project).findings)


@pytest.mark.parametrize("policy,denied", [
    ({"imports":{"banned_roots":["fs"]}}, True),
    ({"imports":{"banned_roots":["node:fs"], "allowed_roots":["fs"]}}, False),
    ({"imports":{"allowed_modules":["fs"], "banned_modules":["fs/promises"]}}, True),
    ({"imports":{"banned_modules":["fs"], "allowed_roots":["fs"]}}, True),
])
@pytest.mark.parametrize("entrypoint", ["effects_only", "import_only"])
def test_import_policy_is_consumed_by_effects_and_import_rules(domain_project, policy, denied, entrypoint):
    workspace, project = domain_project
    source = _select(project, {"effect_scope":"python_io", "policy":policy}, 'void readFile;', entrypoint=entrypoint)
    source.write_text('import {readFile} from "node:fs/promises";\n' + source.read_text())
    report = _review(project)
    executions = [item for item in report.results["example.transform"] if item.plan.invocations]
    assert executions
    for execution in executions:
        assert bool([item for item in execution.findings if item.code == "VF_IMPORT_POLICY"]) == denied


@pytest.mark.parametrize("params,detail", [
    ({"effect_scope":"invented", "policy":{}}, "effect_scope"),
    ({"effect_scope":"none", "policy":{"audit_marker":True}}, "audit_marker"),
    ({"effect_scope":"none", "policy":{"node_source":{"max_lines":1}}}, "node_source"),
    ({"effect_scope":"none", "policy":{"imports":{"banned_roots":"fs"}}}, "banned_roots"),
])
def test_sdk_invalid_or_inapplicable_parameters_fail_visibly(domain_project, params, detail):
    workspace, project = domain_project
    _select(project, params, "")
    report = _review(project)
    assert any(item.code == "RULE.EXECUTION" and detail in item.message for item in report.findings)


@pytest.mark.parametrize("scope,denied", [("none", True), ("global_state", False)])
def test_sdk_global_state_allows_literal_module_state_and_its_mutation(domain_project, scope, denied):
    workspace, project = domain_project
    source = _select(project, {"effect_scope":scope,"policy":{}}, 'cache.value += 1;')
    source.write_text('const cache = {value:0};\n' + source.read_text())
    report = _review(project)
    assert bool([item for item in report.findings if item.definition_id in {"vibeflow.no_side_effects", "vibeflow.import_side_effects"}
                 and item.source_location.get("path") == str(source)]) == denied


@pytest.mark.parametrize("kind", ["node", "base_lib", "plugin", "host_extension"])
def test_same_effect_parameters_apply_to_each_real_resource_owner(domain_project, kind):
    _, project = domain_project
    source = project / "nodes/transform.ts"
    cache = JavascriptAnalysis()
    context = RuleContext(subject={"kind":kind,"id":"test.subject"},target="javascript",facts={
        "source_files":[str(source)],"sources":[{"path":str(source),"text":'export function run(){console.log("hello");void fetch("https://example.invalid");return {};}'}],
        "analysis_cache":cache,"package_root":str(project),
        "import_policy":{"owners":[{"path":str(source),"kind":kind,"id":"test.subject","export":"run"}]}})
    check = javascript_rule_bindings()["vibeflow.no_side_effects"]
    with DriverScope():
        denied = check(context, {}, {"effect_scope":"terminal","policy":{}}).findings
        assert len(denied) == 1 and "fetch" in denied[0].message
        assert denied[0].details["source_owner"]["kind"] == kind
        assert not check(context, {}, {"effect_scope":"python_io","policy":{}}).findings


@pytest.mark.parametrize("scope,denied", [("none", True), ("terminal", True), ("python_io", False), ("global_state", True), ("trusted", True)])
def test_native_clock_and_random_permissions_remain_bounded(domain_project, scope, denied):
    workspace, project = domain_project
    _select(project, {"effect_scope":scope,"policy":{}}, 'void Date.now(); void Math.random();')
    report = _review(project)
    assert bool([item for item in report.findings if item.definition_id == "vibeflow.no_side_effects"
                 and item.code == "VF_BASE_LIB_HOST_IO"]) is False


def test_scoped_npm_package_policy_uses_the_full_package_root(domain_project):
    _, project = domain_project
    source = project / "nodes/transform.ts"
    context = RuleContext(subject={"kind":"node","type_key":"example.transform"},target="javascript",facts={
        "source_files":[str(source)],"sources":[{"path":str(source),"text":'import {value} from "@scope/pkg/sub"; export function run(){return value;}'}],
        "analysis_cache":JavascriptAnalysis(),"package_root":str(project),
        "import_policy":{"owners":[{"path":str(source),"kind":"node","id":"example.transform","export":"run"}],"allowedExternalPackages":["@scope/pkg"]}})
    check = javascript_rule_bindings()["vibeflow.import_side_effects"]
    with DriverScope():
        assert check(context, {}, {"effect_scope":"none","policy":{"imports":{"banned_roots":["@scope/pkg"]}}}).findings
        assert not check(context, {}, {"effect_scope":"none","policy":{"imports":{"banned_roots":["@scope/pkg"],"allowed_modules":["@scope/pkg/sub"]}}}).findings


@pytest.mark.parametrize("declaration,body", [
    ("", 'const p = process; p.exit(1);'),
    ('import {exit as quit} from "node:process";\n', 'quit(1);'),
    ("", 'globalThis.process.kill(1);'),
])
def test_io_permission_does_not_allow_hard_process_effects_through_aliases(domain_project, declaration, body):
    _, project = domain_project
    source = _select(project, {"effect_scope":"python_io","policy":{}}, body)
    source.write_text(declaration + source.read_text())
    report = _review(project)
    assert any(item.definition_id == "vibeflow.no_side_effects" and item.code == "VF_BASE_LIB_HOST_IO"
               and "process." in item.message for item in report.findings)


def test_shared_driver_cache_does_not_share_effect_or_policy_decisions(domain_project):
    _, project = domain_project
    source = project / "nodes/transform.ts"
    text = 'import {readFile} from "node:fs"; export function run(){console.log("hello");void readFile;return {};}'
    cache = JavascriptAnalysis()
    context = RuleContext(subject={"kind":"node", "type_key":"example.transform"}, target="javascript", facts={
        "source_files":[str(source)], "sources":[{"path":str(source),"text":text}],
        "analysis_cache":cache, "package_root":str(project),
        "import_policy":{"owners":[{"path":str(source),"kind":"node","id":"example.transform","export":"run"}]}})
    check = javascript_rule_bindings()["vibeflow.no_side_effects"]
    with DriverScope():
        for params, denied in [
            ({"effect_scope":"terminal","policy":{}}, True),
            ({"effect_scope":"python_io","policy":{}}, False),
            ({"effect_scope":"terminal","policy":{}}, True),
            ({"effect_scope":"python_io","policy":{"imports":{"banned_roots":["fs"]}}}, True),
            ({"effect_scope":"python_io","policy":{}}, False),
        ]:
            assert bool(check(context, {}, params).findings) == denied
    assert len(cache.checks) == 3


@pytest.mark.parametrize("namespace", ["globalThis", "window", "self"])
@pytest.mark.parametrize("scope,denied", [("none", True), ("terminal", True), ("trusted", True),
                                         ("python_io", False), ("global_state", False)])
def test_static_native_resource_slots_follow_the_effect_scope(domain_project, namespace, scope, denied):
    _, project = domain_project
    _select(project, {"effect_scope":scope,"policy":{}}, f'({namespace} as any).__testState = 1;')
    report = _review(project)
    assert bool(report.findings) == denied


def test_native_io_bare_namespace_read_keeps_dynamic_members_bounded(domain_project):
    _, project = domain_project
    _select(project, {"effect_scope":"python_io","policy":{}}, 'void globalThis;')
    assert not _review(project).findings
    _select(project, {"effect_scope":"python_io","policy":{}}, 'const host = globalThis; const key = "process"; (host as any)[key].exit(1);')
    assert any(item.code == "VF_BASE_LIB_HOST_IO" for item in _review(project).findings)


@pytest.mark.parametrize("scope", ["none", "terminal", "python_io", "global_state", "trusted"])
def test_namespace_builtin_mutation_keeps_its_hard_constraint(domain_project, scope):
    _, project = domain_project
    _select(project, {"effect_scope":scope,"policy":{}}, '(globalThis as any).Array.prototype.evil = () => 1;')
    assert any(item.code == "VF_MODULE_STATE" for item in _review(project).findings)


def test_sdk_shared_module_uses_each_selected_factory_and_its_real_support_closure(domain_project):
    _, project = domain_project
    source = _select(project, {"effect_scope":"none","policy":{}}, '')
    source.write_text('import {hostSession} from "./host_support.ts";\n'
        'export function run(){return {output:7};}\n'
        'export function createHost(){return hostSession();}\n')
    (project / "nodes/host_support.ts").write_text('export function hostSession(){'
        'void (globalThis as any).__hostQueue;return {capabilities:{},start(){},stop(){}};}\n')
    resource(project, "host_extension", "test.host").write_text(json.dumps({"kind":"host_extension","id":"test.host",
        "targets":["node"],"provides":[],"rulesets":["vibeflow.host_extension"],
        "implementations":[{"language":"typescript","targets":["node"],"source":{"kind":"file","ref":"nodes/transform.ts","export":"createHost"},
                            "implementation_files":[{"kind":"file","ref":"nodes/host_support.ts"}]}]}))
    report = _review(project, hosts=frozenset({"test.host"}))
    assert not [item for item in report.findings if item.definition_id == "vibeflow.no_side_effects"]
    # Import layering still evaluates the complete declaration module: only
    # effect execution follows the resource's selected factory and helpers.
    assert all(item.code == "VF_IMPORT_LAYER" for item in report.findings)
    assert "host_extension:test.host" in report.results


@pytest.mark.parametrize("node_scope,library_scope", [("none","python_io"),("python_io","none")])
@pytest.mark.parametrize("namespace_import", [False, True])
def test_helper_calls_use_caller_params_while_library_review_keeps_its_own(domain_project, node_scope, library_scope, namespace_import):
    _, project = domain_project
    source = _select(project, {"effect_scope":node_scope,"policy":{}}, 'helpers.helper();' if namespace_import else 'helper();')
    source.write_text(('import * as helpers from "./helper.ts";\n' if namespace_import else 'import {helper} from "./helper.ts";\n') + source.read_text())
    (project / "nodes/helper.ts").write_text('export function helper(){console.log("helper");}\n')
    manifest = resource(project, "node", "example.transform")
    node = json.loads(manifest.read_text()); node["base_libs"] = ["test.helper"]
    manifest.write_text(json.dumps(node))
    resource(project, "base_lib", "test.helper").write_text(json.dumps({"kind":"base_lib","id":"test.helper",
        "rulesets":["test.library"],"implementations":[{"language":"typescript","targets":["node"],
        "source":{"kind":"file","ref":"nodes/helper.ts","export":"helper"}}]}))
    resource(project, "ruleset", "test.library").write_text(json.dumps({"kind":"ruleset","id":"test.library",
        "calls":[{"id":"effects","rule_id":"vibeflow.no_side_effects","params":{"effect_scope":library_scope,"policy":{}}}],
        "entrypoints":{"static":["effects"],"import":[],"run":[]}}))
    report = _review(project)
    for owner, scope in [("example.transform",node_scope),("base_lib:test.helper",library_scope)]:
        findings = [item for result in report.results[owner] for item in result.findings]
        assert bool(findings) == (scope == "none"), (owner, findings)
        if findings:
            assert findings[0].details["source_owner"]["kind"] == "base_lib"


def test_module_initializer_alias_keeps_its_native_import_effect(domain_project):
    _, project = domain_project
    source = _select(project, {"effect_scope":"none","policy":{}}, 'void load;', entrypoint="effects_only")
    source.write_text('import {readFileSync} from "node:fs";\nconst load = readFileSync;\n' + source.read_text())
    assert any(item.definition_id == "vibeflow.no_side_effects" and "node:fs" in item.message
               for item in _review(project).findings)


@pytest.mark.parametrize("constructor,imported", [
    ("defineResource", 'import {defineResource} from "@vibeflow/plugin";'),
    ("descriptor", 'import {defineResource as descriptor} from "@vibeflow/plugin";'),
    ("sdk.defineResource", 'import * as sdk from "@vibeflow/plugin";'),
])
@pytest.mark.parametrize("initializer,denied", [('{type:"number"}', False), ('configure()', True)])
def test_generic_sdk_resource_declaration_keeps_constructor_arguments_checked(domain_project, constructor, imported, initializer, denied):
    _, project = domain_project
    source = _select(project, {"effect_scope":"none","policy":{}}, '')
    source.write_text(imported + '\nfunction configure(){return {type:"number"};}\n'
        + 'const descriptorData = ' + constructor
        + '({kind:"data_schema",type_key:"test.unused",schema:' + initializer + '});\n' + source.read_text())
    report = _review(project)
    assert bool(report.findings) == denied
    if denied:
        assert any(item.code == "VF_IMPORT_SIDE_EFFECT" for item in report.findings)
