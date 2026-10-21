"""Small, isolated JavaScript quality scenarios using the pinned sandbox toolchain."""

from __future__ import annotations

from tests.fixtures.support.plugins import resource as sdk_resource

import json
import os
import shutil
from pathlib import Path

import pytest

from vibeflow.targets.shared.quality_support import SourceQualityFacts, QualityPolicy, QualityThresholds
from tests.fixtures.support.project_rules import evaluate_standard_project_quality
from vibeflow.targets.shared.quality_support.implementation import analyze_call_graph
from vibeflow.targets.javascript.build.toolchain import run_quality_facts_driver
from vibeflow.tooling.application.javascript.quality_scan import scan_javascript_quality
from vibeflow.targets.python.quality import PythonSource, analyze_python_source
from vibeflow.tooling.application.cli import main as dispatch_main
from vibeflow.tooling.application.javascript.cli import main
from vibeflow.tooling.project.workspace_loader import load_workspace_config


SANDBOX = Path(__file__).resolve().parents[3] / "sandbox/javascript/minimal"
TOOLCHAIN = Path(os.environ.get("VIBEFLOW_TEST_TOOLCHAIN_ROOT", SANDBOX / "project"))


_GREETING_NODE = {'rulesets': ['vibeflow.process'],
 'id': 'example.greet',
 'display_name': 'Build greeting',
 'description': 'Builds a greeting from a name and an injected clock.',
 'version': '1.0.0',
 'flow_kind': 'terminal',
 'contract': {'requires': [{'type': 'name.text',
                            'cardinality': 'exactly_one',
                            'display_name': 'Name'}],
              'provides': [{'key': 'greeting',
                            'type': 'greeting.text',
                            'display_name': 'Greeting'}],
              'params_schema': {'prefix': {'type': 'string'}},
              'params_defaults': {'prefix': 'Hello'},
              'input_semantics': {'name.text': ['Name input consumed by this '
                                                'node.']},
              'output_semantics': {'greeting': ['Greeting output produced by '
                                                'this node.']}},
 'base_libs': ['example.text'],
 'capabilities': [{'id': 'example.clock', 'operations': ['now']}],
 'tags': ['example'],
 'node_type': 'vibeflow.node',
 'kind': 'node',
 'implementations': [{'language': 'typescript',
                      'targets': ['browser', 'node'],
                      'source': {'kind': 'file',
                                 'ref': 'nodes/greet.ts',
                                 'export': 'run'},
                      'completion': 'suspend'}]}

@pytest.fixture
def quality_case(tmp_path: Path):
    if not (TOOLCHAIN / "node_modules/typescript").is_dir():
        pytest.skip("pinned JavaScript sandbox toolchain is not installed")
    counter = 0

    def make(sources: dict[str, str]) -> Path:
        nonlocal counter
        counter += 1
        root = tmp_path / f"case-{counter}"
        root.mkdir()
        for name in ("package.json", "package-lock.json"):
            shutil.copy2(TOOLCHAIN / name, root / name)
        (root / "node_modules").symlink_to(TOOLCHAIN / "node_modules", target_is_directory=True)
        for relative, content in sources.items():
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        return root

    return make


def _project_case(tmp_path: Path) -> tuple[Path, Path, Path]:
    if not (TOOLCHAIN / "node_modules/typescript").is_dir():
        pytest.skip("pinned JavaScript sandbox toolchain is not installed")
    workspace = tmp_path / "workspace"
    shutil.copytree(SANDBOX, workspace, ignore=shutil.ignore_patterns("node_modules", "__pycache__", "*.pyc"))
    project = workspace / "project"
    (project / "node_modules").symlink_to(TOOLCHAIN / "node_modules", target_is_directory=True)
    from tests.fixtures.support.plugins import resource_declarations, write_plugin
    values = [*resource_declarations(project), _GREETING_NODE]
    source = project / "nodes/greet.ts"
    source.write_text(source.read_text().split("export const resource_6Definition=")[0])
    write_plugin(project, values, target="javascript", plugin_id="example.javascript.minimal")
    (project / "root_rules.jsonc").write_text('{"rulesets":[]}')
    config = project / "vibeflow_project.jsonc"
    data = json.loads(config.read_text(encoding="utf-8"))

    config.write_text(json.dumps(data), encoding="utf-8")
    return workspace / "vibeflow_config.jsonc", project, project / "configs/greeting.jsonc"


def _configure_rule_policy(project: Path, policy: dict[str, object]) -> None:
    """Select numeric review parameters through an explicit Ruleset override."""
    (sdk_resource(project, "ruleset", "test.numeric")).write_text(json.dumps({
        "kind": "ruleset", "id": "test.numeric", "calls": [{"id": "base", "ruleset_id": "vibeflow.process"}],
        "relations": [{"source": "$self", "target": "base/maintainability", "kind": "overrides", "params": {"policy": policy}}],
        "entrypoints": {"static": ["base"], "run": ["base"], "import": ["base"]},
    }), encoding="utf-8")
    file = sdk_resource(project, 'node', 'example.greet')
    data = json.loads(file.read_text(encoding="utf-8"))
    data["rulesets"] = ["test.numeric"]
    file.write_text(json.dumps(data), encoding="utf-8")


def _formal_findings(payload, severity):
    result = list(payload.get("errors" if severity == "error" else "warnings", ()))
    for report in payload.get("reports", ()):
        for item in (*report.get("diagnostics", ()), *report.get("warnings", ())):
            if item.get("severity", "error") == severity and item not in result:
                result.append(item)
    return result


def _registered_rule_report(project: Path, *, policy_data=None, **_):
    """Exercise selected formal implementation rules without a workflow."""
    from vibeflow.core.flow import GraphConfig
    from vibeflow.targets.javascript.quality.rules import run_javascript_rules
    from vibeflow.targets.javascript.build.project_resources import target_neutral_import_policy
    from vibeflow.tooling.project.resources import prepare_workflow_catalogs
    if policy_data is not None:
        _configure_rule_policy(project, policy_data)
    catalogs = prepare_workflow_catalogs(project / "configs/greeting.jsonc")
    import_policy, _ = target_neutral_import_policy(catalogs=catalogs, project_root=project, allowed_external=set())
    return run_javascript_rules(GraphConfig(nodes=(), rulesets=()), catalogs, project_root=project,
                                package_root=project, import_policy=import_policy, include_registered=True)


def _add_planned_chain(project: Path, config: Path, depth: int) -> None:
    nodeset_types = project / "nodeset_types"
    nodeset_types.mkdir(exist_ok=True)
    paths = []
    for index in range(depth):
        path = nodeset_types / f"depth-{index}.jsonc"
        child = f"example.depth.{index - 1}" if index else "example.future"
        path.write_text(json.dumps({
            "type_key": f"example.depth.{index}",
            "display_name": f"Depth {index}",
            "description": "A planned nested step.",
            "status": "planned",
            "requires": [],
            "provides": [],
            "pipeline": {"nodes": [{
                "id": "call", "definition_id": child,
                "display_name": "Call child", "description": "Calls the next layer.",
                "status": "planned", "flow_kind": "process",
                "requires": [], "provides": [],
            }]},
        }), encoding="utf-8")
        paths.append(f"../nodeset_types/{path.name}")
    data = json.loads(config.read_text(encoding="utf-8"))
    data["nodeset_imports"] = paths
    config.write_text(json.dumps(data), encoding="utf-8")


def test_unregistered_source_and_exclusions(quality_case, capsys) -> None:
    root = quality_case({
        "src/large.ts": "export const value = 1;\n" + "\n" * 500,
        "tests/test.ts": "export const tested = true;\n",
        "generated/huge.ts": "export const generated = 1;\n" + "\n" * 1000,
        "dist/output.js": "export const built = 1;\n" + "\n" * 1000,
        "src/auto.generated.tsx": "export const generated = 1;\n" + "\n" * 1000,
        "src/compact.min.mjs": "export const minified = 1;\n" + "\n" * 1000,
    })
    report = scan_javascript_quality(root, package_root=root)
    assert report.status == "FAIL"
    assert {item.path for item in report.files} == {"src/large.ts", "tests/test.ts"}
    assert any(item.code == "QUALITY.FILE.MAX_LINES" for item in report.findings)
    excluded = scan_javascript_quality(root, package_root=root, excluded_dirs=(*__import__("vibeflow.targets.javascript.quality.source", fromlist=["DEFAULT_EXCLUDED_DIRS"]).DEFAULT_EXCLUDED_DIRS, "src", "tests"))
    assert excluded.status == "PASS" and not excluded.files


def test_source_facts_cover_syntax_typescript_types_and_internal_imports(quality_case) -> None:
    root = quality_case({
        "src/index.ts": (
            "import { value } from './helper.js';\n"
            "import { ext } from 'external-package';\n"
            "export function named(a = 1, ...rest: number[]) {\n"
            "  if (a) return value;\n"
            "  return rest.length;\n"
            "}\n"
            "export const arrow = ({x}: {x:number}) => x ?? value;\n"
            "export class Worker { async run() { for (const x of [1]) { if (x) return x; } } }\n"
            "const typeError: string = 42;\n"
            "void ext; void typeError;\n"
        ),
        "src/helper.ts": "export const value = 1;\n",
        "src/bare.ts": "import { value } from 'src/helper.ts';\nexport const result = value;\n",
    })
    report = scan_javascript_quality(root, package_root=root)
    file = next(item for item in report.files if item.path == "src/index.ts")
    assert report.status in {"PASS", "CONCERNS"}
    assert "src/helper.ts" in report.dependency_graph["src/index.ts"]
    assert "external-package" not in report.dependency_graph["src/index.ts"]
    assert report.dependency_graph["src/bare.ts"] == ()
    assert file.import_sites[0].line == 1
    assert {item.qualname for item in file.functions} >= {"named", "arrow", "Worker.run"}
    assert next(item for item in file.functions if item.qualname == "arrow").param_count == 1
    assert file.branch_count >= 3
    assert not any(item.rule_id == "QUALITY.SYNTAX.JAVASCRIPT" for item in report.findings)
    broken_line = "export const broken = ;"
    broken = quality_case({"broken.ts": f"export const valid = 1;\n{broken_line}\n"})
    syntax = scan_javascript_quality(broken, package_root=broken)
    assert syntax.status == "FAIL"
    assert syntax.findings[0].rule_id == "QUALITY.SYNTAX.JAVASCRIPT"
    assert syntax.findings[0].source_location["line"] == 2
    assert syntax.findings[0].source_location["column"] == broken_line.index(";") + 1


def test_every_handwritten_javascript_extension_has_distinct_file_identity(quality_case) -> None:
    suffixes = (".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".mts", ".cts")
    root = quality_case({
        f"src/sample{suffix}": (
            "module.exports = 1;\n" if suffix in {".cjs", ".cts"}
            else "export const value = 1;\n"
        )
        for suffix in suffixes
    })
    report = scan_javascript_quality(root, package_root=root)
    assert {item.path for item in report.files} == {f"src/sample{suffix}" for suffix in suffixes}
    assert len({item.module for item in report.files}) == len(suffixes)
    assert not any(item.rule_id == "QUALITY.SYNTAX.JAVASCRIPT" for item in report.findings)


def test_target_source_facts_do_not_assemble_default_rules(quality_case, monkeypatch):
    from vibeflow.targets.shared.rule_support.plugin import BuiltinPlugin
    from vibeflow.targets.javascript.quality.source import collect_javascript_quality_facts
    root = quality_case({"large.ts":"export const value = 1;\n" + "\n" * 500})
    def unexpected(*args, **kwargs):
        raise AssertionError("Target fact collection must not contribute plugins")
    monkeypatch.setattr(BuiltinPlugin, "contributions", unexpected)
    cache = {}
    facts = collect_javascript_quality_facts(root, package_root=root, facts_cache=cache)
    assert cache[str(root)] is facts
    assert facts.files[0]["path"] == "large.ts"
    assert facts.files[0]["lines"] == 501
    assert facts.findings == ()


def test_application_source_scan_reuses_supplied_catalog_and_bindings(quality_case, monkeypatch):
    from vibeflow.targets.shared.rule_support.plugin import BuiltinPlugin
    from vibeflow.tooling.project.resources import load_builtin_plugins
    root = quality_case({"large.ts":"export const value = 1;\n" + "\n" * 500})
    contributed = []
    original = BuiltinPlugin.contributions
    def counted(self, config=None):
        contributed.append(self.id)
        return original(self, config)
    monkeypatch.setattr(BuiltinPlugin, "contributions", counted)
    catalog = load_builtin_plugins("javascript").catalogs
    cache = {}
    report = scan_javascript_quality(root, package_root=root, catalog=catalog, facts_cache=cache)
    assert contributed == ["vibeflow.core"]
    assert report.checked_rulesets == ("vibeflow.quality.source",)
    assert len(report.rule_executions) == 1
    assert any(item.code == "QUALITY.FILE.MAX_LINES" for item in report.findings)
    assert len(cache[str(root)].files) == len(report.files) == 1


def test_source_scan_does_not_configure_same_id_external_rule(quality_case):
    from types import SimpleNamespace
    from vibeflow.core.descriptors.contributions import ContributionBuilder, compose_contributions
    from vibeflow.core.rules import RuleCall, RuleDescriptor, RuleResult, RulesetDescriptor
    from vibeflow.targets.shared.bindings import attach_native_bindings
    root = quality_case({"source.ts": "export const value = 1;\n"})
    rule = RuleDescriptor("vibeflow.quality.files",
        params_schema={"max_file_lines": {"type": "object"}},
        params_defaults={"max_file_lines": {"label": "external parameter"}})
    builder = ContributionBuilder("external.project")
    builder.add(rule)
    builder.add(RulesetDescriptor("vibeflow.quality.source", (RuleCall("external", rule.id),)))
    catalog = compose_contributions((builder.finish(),))
    observed = []
    def check(context, inputs, params):
        observed.append(dict(params))
        return RuleResult()
    definition = SimpleNamespace(id=builder.id, bindings=lambda: {("rule", rule.id): check})
    attach_native_bindings(catalog, (definition,))
    report = scan_javascript_quality(root, package_root=root, catalog=catalog,
        thresholds=QualityThresholds(max_file_lines=1))
    assert report.status == "PASS"
    assert observed == [{"max_file_lines": {"label": "external parameter"}}]


def test_source_import_resolution_handles_index_reexport_and_package_alias(quality_case) -> None:
    root = quality_case({
        "src/main.ts": (
            "import { one } from './util';\n"
            "import { two } from '#alias';\n"
            "export { three } from './other.js';\n"
            "export const total = one + two;\n"
        ),
        "src/util/index.ts": "export const one = 1;\n",
        "src/alias.ts": "export const two = 2;\n",
        "src/other.ts": "export const three = 3;\n",
    })
    package = root / "package.json"
    data = json.loads(package.read_text(encoding="utf-8"))
    data["imports"] = {"#alias": "./src/alias.ts"}
    package.write_text(json.dumps(data), encoding="utf-8")
    report = scan_javascript_quality(root, package_root=root)
    assert set(report.dependency_graph["src/main.ts"]) == {
        "src/util/index.ts", "src/alias.ts", "src/other.ts",
    }
    main = next(item for item in report.files if item.path == "src/main.ts")
    assert [site.line for site in main.import_sites] == [1, 2, 3]
    assert all(site.column > 1 for site in main.import_sites)


def test_language_facts_count_optional_parameters_and_control_flow(quality_case) -> None:
    root = quality_case({
        "src/flow.ts": (
            "export const worker = {\n"
            "  async run(a?: number, b = 1, ...rest: number[]) {\n"
            "    let value = a ?? b;\n"
            "    if (value && b) value++;\n"
            "    for (const item of rest) value += item;\n"
            "    while (value < 0) value++;\n"
            "    switch (value) { case 1: value++; break; default: break; }\n"
            "    try { value++; } catch { value--; }\n"
            "    return value ? value : b;\n"
            "  },\n"
            "};\n"
        ),
        "src/types.d.ts": "export declare const declared: number;\n",
    })
    report = scan_javascript_quality(root, package_root=root)
    assert {item.path for item in report.files} == {"src/flow.ts", "src/types.d.ts"}
    flow = next(item for item in report.files if item.path == "src/flow.ts")
    method = next(item for item in flow.functions if item.qualname == "run")
    assert method.param_count == 3
    assert method.branches == 8
    assert flow.branch_count == method.branches


def test_simple_python_and_javascript_facts_share_core_rule(quality_case) -> None:
    root = quality_case({
        "src/branch.ts": (
            "export function branch(value) {\n"
            "  if (value) return 1;\n"
            "  return 0;\n"
            "}\n"
        ),
    })
    python = analyze_python_source(PythonSource(
        module="src.branch", relative_path="src/branch.py",
        source_path=str(root / "src/branch.py"),
        text="def branch(value):\n    if value:\n        return 1\n    return 0\n",
    ))
    thresholds = QualityThresholds(max_function_branches=0)
    javascript = scan_javascript_quality(root, package_root=root, thresholds=thresholds)
    js_function = javascript.files[0].functions[0]
    py_function = python.file.functions[0]
    assert (js_function.param_count, js_function.branches) == (
        py_function.param_count, py_function.branches,
    ) == (1, 1)
    python_report = evaluate_standard_project_quality(
        SourceQualityFacts(root=str(root), files=(python.file,)),
        QualityPolicy(thresholds=thresholds),
    )
    assert javascript.status == "CONCERNS"
    assert any(item.rule_id == "QUALITY.FUNCTION.TOO_MANY_BRANCHES" for item in javascript.findings)
    assert any(item.rule_id == "QUALITY.FUNCTION.TOO_MANY_BRANCHES" for item in python_report.findings)


def test_dynamic_parameter_call_does_not_invent_internal_edge(quality_case) -> None:
    root = quality_case({
        "src/run.ts": (
            "function helper() { return helper(); }\n"
            "export function run(helper: () => number) { return helper(); }\n"
        ),
    })
    source = root / "src/run.ts"
    facts = run_quality_facts_driver({
        "qualityRoot": str(root),
        "qualityFiles": [str(source)],
        "qualityImplementations": [{'node_type': 'vibeflow.node',
            'id': "example.run", "path": str(source),
            "export": "run", "kind": "node",
        }],
    }, package_root=root)
    implementation = facts.implementations[0]
    assert implementation["calls"]["run"] == []
    assert analyze_call_graph(implementation["calls"], entry="run").recursive_paths == ()


def test_source_threshold_boundary_and_independent_file(quality_case, capsys) -> None:
    root = quality_case({"exact.ts": "export const x = 1;\n" + "\n" * 499})
    report = scan_javascript_quality(root, package_root=root, thresholds=QualityThresholds(max_file_lines=500, warn_file_lines=500))
    assert report.status == "CONCERNS"
    assert {item.rule_id for item in report.findings} == {"QUALITY.FILE.WARN_LINES"}
    report = scan_javascript_quality(root / "exact.ts", package_root=root, thresholds=QualityThresholds(max_file_lines=499, warn_file_lines=499))
    assert report.status == "FAIL" and len(report.files) == 1


def test_quality_warning_text_and_exit_code(quality_case, capsys) -> None:
    root = quality_case({"src/near.ts": "export const x = 1;\n" + "\n" * 449})
    from tests.fixtures.support.projects import register_root
    register_root(root, "javascript")
    (root / "root_rules.jsonc").write_text('{"rulesets":[{"rule_id":"vibeflow.root.files"}]}')
    code = main(["quality-check", "--path", str(root)])
    output = capsys.readouterr().out
    assert code == 0
    assert "Project quality: CONCERNS" in output
    assert "QUALITY.FILE.WARN_LINES" in output




def test_mixed_workspace_root_rule_parameters_apply_to_both_targets(tmp_path, capsys):
    workspace, project, _ = _project_case(tmp_path)
    python_root = workspace.parent / "python-project"
    python_root.mkdir()
    (python_root / "vibeflow_project.jsonc").write_text('{"project_target":"python"}')
    (python_root / "large.py").write_text("value = 1\n" * 100)
    data = json.loads(workspace.read_text())
    data["roots"].append({"id":"python-demo", "path":"python-project"})
    workspace.write_text(json.dumps(data))
    for root in (python_root, project):
        (root / "root_rules.jsonc").write_text(json.dumps({"rulesets":[{"rule_id":"vibeflow.root.files"}],
            "rule_params":{"vibeflow.root.files":{"max_file_lines":1,"warn_file_lines":1}}}))
    assert dispatch_main(["quality-check", "--workspace", str(workspace), "--json"]) == 1
    payload = json.loads(capsys.readouterr().out)
    errors = [item for item in payload["errors"] if item["rule_id"] == "QUALITY.FILE.MAX_LINES"]
    assert {item["root_id"] for item in errors} == {"python-demo", "js-demo"}


def test_multiple_workflows_and_empty_root_collect_root_source_once(tmp_path, capsys, monkeypatch):
    workspace, project, config = _project_case(tmp_path)
    (project / "root_rules.jsonc").write_text('{"rulesets":[{"rule_id":"vibeflow.root.files"}]}')
    shutil.copy2(config, config.with_name("second.jsonc"))
    (project / "unregistered.ts").write_text("export const value=1;\n" + "\n" * 500)
    from vibeflow.targets.javascript.build import quality_source
    original = quality_source.collect_javascript_quality_facts
    calls = []
    def counted(root, **kwargs):
        calls.append(Path(root))
        return original(root, **kwargs)
    monkeypatch.setattr(quality_source, "collect_javascript_quality_facts", counted)
    assert main(["quality-check", "--workspace", str(workspace), "--json"]) == 1
    payload = json.loads(capsys.readouterr().out)
    assert len(payload["reports"]) == 2
    assert calls == [project]
    assert sum(item["rule_id"] == "QUALITY.FILE.MAX_LINES" for item in payload["errors"]) == 1
    calls.clear()
    config.unlink()
    config.with_name("second.jsonc").unlink()
    assert main(["quality-check", "--workspace", str(workspace), "--json"]) == 1
    assert json.loads(capsys.readouterr().out)["reports"] == []
    assert calls == [project]


def test_generated_local_preview_is_not_application_source(tmp_path, capsys):
    workspace, project, _ = _project_case(tmp_path)
    from vibeflow.tooling.presentation.viewer import install_page
    install_page(project)
    # This is a display-data script, even if damaged; quality checks must keep
    # inspecting the project's actual source after a preview has been generated.
    (project/"vibeflow-preview/index.js").write_text("not application JavaScript !!!")
    code = main(["quality-check", "--workspace", str(workspace), "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 0, payload
    facts = scan_javascript_quality(project, package_root=project)
    assert facts.files
    assert not any("vibeflow-preview" in row.path for row in facts.files)


@pytest.mark.parametrize("value", [0, True, 1.5, "5"])
def test_project_depth_field_rejects_invalid_value(tmp_path: Path, value) -> None:
    workspace, project, _ = _project_case(tmp_path)
    path = project / "vibeflow_project.jsonc"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["javascript"]["nodeset_max_depth"] = value
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(Exception, match="unknown fields"):
        load_workspace_config(workspace)


def test_registered_node_uses_config_schema_keys_and_static_call_chain(tmp_path: Path, capsys) -> None:
    workspace, project, config = _project_case(tmp_path)
    source = project / "nodes/greet.ts"
    original = source.read_text(encoding="utf-8")
    source.write_text(original + "\nfunction h1() { return h2(); }\nfunction h2() { return h3(); }\nfunction h3() { return 1; }\n", encoding="utf-8")
    source.write_text(source.read_text(encoding="utf-8").replace("  const name =", "  h1();\n  const name ="), encoding="utf-8")
    code = main(["validate", "--workspace", str(workspace), "--config", str(config), "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 0 and payload["status"] == "CONCERNS"
    assert any(item["rule_id"] == "NODE.MAINTAINABILITY.CALL_CHAIN_TOO_DEEP" and item["details"]["path"] == ["run", "h1", "h2", "h3"] for item in payload["warnings"])
    source.write_text(source.read_text(encoding="utf-8").replace("function h3() { return 1; }", "function h3() { return h4(); }\nfunction h4() { return 1; }"), encoding="utf-8")
    code = main(["validate", "--workspace", str(workspace), "--config", str(config), "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 1 and payload["code"] == "NODE.MAINTAINABILITY.CALL_CHAIN_TOO_DEEP"
    assert payload["diagnostics"][0]["details"]["path"] == ["run", "h1", "h2", "h3", "h4"]
    source.write_text(source.read_text(encoding="utf-8").replace("function h4() { return 1; }", "function h4() { return h1(); }"), encoding="utf-8")
    code = main(["validate", "--workspace", str(workspace), "--config", str(config), "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 1 and payload["code"] == "NODE.MAINTAINABILITY.CALL_CHAIN_TOO_DEEP"
    source.write_text(source.read_text(encoding="utf-8").replace("function h4() { return h1(); }", "function h4() { return 1; }").replace("function h3() { return h4(); }\nfunction h4() { return 1; }", "function h3() { return 1; }"), encoding="utf-8")
    _configure_rule_policy(project, {"complexity": {"max_params": 1}})
    code = main(["validate", "--workspace", str(workspace), "--config", str(config), "--json"])
    assert code == 0
    capsys.readouterr()
    _configure_rule_policy(project, {"complexity": {"max_params": 0}})
    code = main(["validate", "--workspace", str(workspace), "--config", str(config), "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 1
    assert payload["code"] == "NODE.MAINTAINABILITY.COMPLEXITY_MAX_PARAMS"
    _configure_rule_policy(project, {"complexity": {"max_params": 1}})
    manifest = sdk_resource(project, 'node', 'example.greet')
    data = json.loads(manifest.read_text(encoding="utf-8"))
    data["contract"]["params_schema"]["suffix"] = {"type": "string"}
    data["contract"]["params_defaults"]["suffix"] = "!"
    manifest.write_text(json.dumps(data), encoding="utf-8")
    code = main(["validate", "--workspace", str(workspace), "--config", str(config), "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 1 and payload["code"] == "NODE.MAINTAINABILITY.COMPLEXITY_MAX_PARAMS"


@pytest.mark.parametrize(
    ("field", "metric"),
    [
        ("max_functions", "function_count"),
        ("max_branches", "branch_count"),
        ("max_nesting_depth", "max_nesting_depth"),
        ("max_contract_keys", "contract_key_count"),
    ],
)
def test_registered_node_optional_limits_reach_javascript_quality_cli(
    tmp_path: Path, capsys, field: str, metric: str,
) -> None:
    workspace, project, config = _project_case(tmp_path)
    # SDK resource scope is supplied by this explicit workflow.
    source = project / "nodes/greet.ts"
    source.write_text(
        source.read_text(encoding="utf-8")
        + "\nfunction extra(a: number) { if (a) { if (a > 1) return a; } return 0; }\n",
        encoding="utf-8",
    )
    rule = f"NODE.MAINTAINABILITY.COMPLEXITY_{field.upper()}"

    def check(limit: int | None) -> dict[str, object]:
        _configure_rule_policy(project, {"complexity": {field: limit}})
        main(["quality-check", "--workspace", str(workspace), "--json"])
        payload = json.loads(capsys.readouterr().out)
        return {"errors": _formal_findings(payload,"error")}

    baseline = check(None)
    assert not any(item["rule_id"] == rule for item in baseline["errors"])
    from vibeflow.tooling.project.resources import prepare_workflow_catalogs
    from vibeflow.targets.javascript.quality.implementation import registered_implementation_requests
    catalogs = prepare_workflow_catalogs(project / "configs/greeting.jsonc")
    owners, _ = registered_implementation_requests(
        catalogs, project_root=project, selected_files=(str(source),),
    )
    facts = run_quality_facts_driver({
        "qualityRoot": str(project), "qualityFiles": [str(source)],
        "qualityImplementations": owners,
    }, package_root=project)
    file = facts.files[0]
    actual = (
        len(next(iter(catalogs.nodes)).contract.requires)
        + len(next(iter(catalogs.nodes)).contract.provides)
        if metric == "contract_key_count" else int(file[metric])
    )
    assert actual >= 2
    equal = check(actual)
    assert not any(item["rule_id"] == rule for item in equal["errors"])
    exceeded = check(actual - 1)
    assert any(item["rule_id"] == rule for item in exceeded["errors"])


def test_root_source_errors_refuse_quality_validate_and_build(tmp_path: Path, capsys) -> None:
    workspace, project, config = _project_case(tmp_path)
    (project / "root_rules.jsonc").write_text('{"rulesets":[{"rule_id":"vibeflow.root.files"}]}')
    (project / "unregistered.ts").write_text("export const x = 1;\n" + "\n" * 500, encoding="utf-8")
    code = main(["quality-check", "--workspace", str(workspace), "--json"])
    quality = json.loads(capsys.readouterr().out)
    assert code == 1 and any(f["rule_id"] == "QUALITY.FILE.MAX_LINES" for f in quality["errors"])
    code = main(["validate", "--workspace", str(workspace), "--config", str(config), "--json"])
    validated = json.loads(capsys.readouterr().out)
    assert code == 1 and validated["code"] == "QUALITY.FILE.MAX_LINES"
    code = main([
        "build", "--workspace", str(workspace), "--config", str(config),
        "--target", "node", "--profile", "esm-module",
        "--out-dir", str(tmp_path / "output"),
    ])
    built = json.loads(capsys.readouterr().out)
    assert code == 1 and built["code"] == "QUALITY.FILE.MAX_LINES"


def test_nodeset_width_warning_reaches_validate_quality_and_build(tmp_path: Path, capsys) -> None:
    workspace, project, config = _project_case(tmp_path)
    data = json.loads(config.read_text(encoding="utf-8"))
    definition = {
        "type_key": "example.planned.wide",
        "display_name": "Wide planned group",
        "description": "Groups eleven planned steps.",
        "status": "planned",
        "requires": [],
        "provides": [],
        "pipeline": {"nodes": [{
            "id": f"step-{index}",
            "definition_id": "example.future",
            "display_name": f"Step {index}",
            "description": "Future step.",
            "status": "planned",
            "flow_kind": "process",
            "requires": [],
            "provides": [],
        } for index in range(11)]},
    }
    nodeset = project / "nodeset_types/wide.jsonc"
    nodeset.parent.mkdir()
    nodeset.write_text(json.dumps(definition), encoding="utf-8")
    data["nodeset_imports"] = ["../nodeset_types/wide.jsonc"]
    config.write_text(json.dumps(data), encoding="utf-8")
    definition["pipeline"]["nodes"].pop()
    nodeset.write_text(json.dumps(definition), encoding="utf-8")
    code = main(["validate", "--workspace", str(workspace), "--config", str(config), "--json"])
    at_limit = json.loads(capsys.readouterr().out)
    assert code == 0 and not any(
        item["rule_id"] == "NODESET.SMELL.TOO_WIDE" for item in at_limit.get("warnings", ())
    )
    definition["pipeline"]["nodes"].append({
        "id": "step-10", "definition_id": "example.future", "display_name": "Step 10",
        "description": "Future step.", "status": "planned", "flow_kind": "process",
        "requires": [], "provides": [],
    })
    nodeset.write_text(json.dumps(definition), encoding="utf-8")
    code = main(["validate", "--workspace", str(workspace), "--config", str(config), "--json"])
    validated = json.loads(capsys.readouterr().out)
    assert code == 0 and validated["status"] == "CONCERNS", validated
    assert any(item["rule_id"] == "NODESET.SMELL.TOO_WIDE" for item in validated["warnings"])
    code = main(["quality-check", "--workspace", str(workspace), "--json"])
    checked = json.loads(capsys.readouterr().out)
    assert code == 0 and checked["status"] == "CONCERNS"
    assert any(item["rule_id"] == "NODESET.SMELL.TOO_WIDE" for item in checked["reports"][0]["warnings"])
    code = main([
        "build", "--workspace", str(workspace), "--config", str(config),
        "--target", "node", "--profile", "esm-module",
        "--out-dir", str(tmp_path / "wide-output"),
    ])
    built = json.loads(capsys.readouterr().out)
    assert code == 0 and built["status"] == "CONCERNS"
    assert any(item["rule_id"] == "NODESET.SMELL.TOO_WIDE" for item in built["warnings"])


def test_nodeset_depth_rule_setting_reaches_validate_quality_and_build(tmp_path: Path, capsys) -> None:
    workspace, project, config = _project_case(tmp_path)
    _add_planned_chain(project, config, 4)
    code = main(["validate", "--workspace", str(workspace), "--config", str(config), "--json"])
    at_limit = json.loads(capsys.readouterr().out)
    assert code == 0 and not any(
        item["rule_id"] == "NODESET.NESTING.DEPTH_EXCEEDED"
        for item in at_limit.get("errors", ())
    )
    _add_planned_chain(project, config, 5)
    code = main(["validate", "--workspace", str(workspace), "--config", str(config), "--json"])
    validated = json.loads(capsys.readouterr().out)
    assert code == 1 and validated["code"] == "NODESET.NESTING.DEPTH_EXCEEDED"
    assert validated["diagnostics"][0]["details"]["actual_depth"] == 5
    assert len(validated["diagnostics"][0]["details"]["calls"]) == 4
    code = main(["quality-check", "--workspace", str(workspace), "--json"])
    checked = json.loads(capsys.readouterr().out)
    assert code == 1 and checked["reports"][0]["code"] == "NODESET.NESTING.DEPTH_EXCEEDED"
    code = main([
        "build", "--workspace", str(workspace), "--config", str(config),
        "--target", "node", "--profile", "esm-module",
        "--out-dir", str(tmp_path / "depth-output"),
    ])
    built = json.loads(capsys.readouterr().out)
    assert code == 1 and built["code"] == "NODESET.NESTING.DEPTH_EXCEEDED"
    from tests.fixtures.support.rule_inspection import depth_ruleset
    from tests.fixtures.support.plugins import append_resource
    append_resource(project,depth_ruleset(5).to_dict())
    data=json.loads(config.read_text());data['rulesets']=['test.depth'];config.write_text(json.dumps(data))
    for path in (project/'nodeset_types').glob('depth-*.jsonc'):
        declaration=json.loads(path.read_text());declaration['rulesets']=['test.depth'];path.write_text(json.dumps(declaration))
    code = main(["validate", "--workspace", str(workspace), "--config", str(config), "--json"])
    accepted = json.loads(capsys.readouterr().out)
    assert code == 0, accepted


def test_planned_nodeset_depth_respects_explicit_empty_boundary(tmp_path: Path, capsys) -> None:
    workspace, project, config = _project_case(tmp_path)
    _add_planned_chain(project, config, 5)
    code = main(["validate", "--workspace", str(workspace), "--config", str(config), "--json"])
    rejected = json.loads(capsys.readouterr().out)
    assert code == 1 and rejected["code"] == "NODESET.NESTING.DEPTH_EXCEEDED"
    boundary = project / "nodeset_types/depth-2.jsonc"
    data = json.loads(boundary.read_text())
    data["rulesets"] = []
    boundary.write_text(json.dumps(data))
    code = main(["validate", "--workspace", str(workspace), "--config", str(config), "--json"])
    accepted = json.loads(capsys.readouterr().out)
    assert code == 0 and accepted["status"] in {"PASS", "CONCERNS"}, accepted


def test_planned_nodeset_recursion_reaches_javascript_cli(tmp_path: Path, capsys) -> None:
    workspace, project, config = _project_case(tmp_path)
    _add_planned_chain(project, config, 1)
    definition = project / "nodeset_types/depth-0.jsonc"
    data = json.loads(definition.read_text(encoding="utf-8"))
    data["pipeline"]["nodes"][0]["definition_id"] = "example.depth.0"
    definition.write_text(json.dumps(data), encoding="utf-8")
    code = main(["validate", "--workspace", str(workspace), "--config", str(config), "--json"])
    validated = json.loads(capsys.readouterr().out)
    assert code == 1 and validated["code"] == "NODESET.RECURSION"
    code = main(["quality-check", "--workspace", str(workspace), "--json"])
    checked = json.loads(capsys.readouterr().out)
    assert code == 1 and checked["reports"][0]["code"] == "NODESET.RECURSION"


@pytest.mark.parametrize("violation", ["node_source", "nodeset_depth"])
def test_review_uses_registered_node_and_nodeset_quality_rules(
    tmp_path: Path, capsys, violation: str,
) -> None:
    workspace, project, config = _project_case(tmp_path)
    project_config = project / "vibeflow_project.jsonc"
    data = json.loads(project_config.read_text(encoding="utf-8"))
    data["architecture"] = {"documents": [{
        "workflow": "configs/greeting.jsonc",
        "document": "review_artifacts/GREETING_ARCHITECTURE.jsonc",
    }]}
    project_config.write_text(json.dumps(data), encoding="utf-8")
    if violation == "node_source":
        source = project / "nodes/greet.ts"
        source.write_text(source.read_text(encoding="utf-8").replace("  return ", "  // Local implementation\n" * 501 + "  return "), encoding="utf-8")
        expected = "NODE.PURITY.SOURCE_TOO_LARGE"
    else:
        _add_planned_chain(project, config, 5)
        expected = "NODESET.NESTING.DEPTH_EXCEEDED"
    output = tmp_path / "review.svg"
    code = main([
        "review", "--workspace", str(workspace), "--config", str(config),
        "--output", str(output),
    ])
    payload = json.loads(capsys.readouterr().out)
    assert code == 1 and payload["failed_stage"] == "preflight"
    assert payload["code"] == expected
    assert not output.exists()


def test_registered_base_lib_size_reaches_quality_and_validate(tmp_path: Path, capsys) -> None:
    workspace, project, config = _project_case(tmp_path)
    source = project / "base_lib/text.ts"
    original = source.read_text(encoding="utf-8")
    lines = original.splitlines()
    source.write_text("\n".join([*lines, *([""] * (499 - len(lines))), "// pad"]), encoding="utf-8")
    code = main(["validate", "--workspace", str(workspace), "--config", str(config), "--json"])
    at_line_limit = json.loads(capsys.readouterr().out)
    assert code == 0 and at_line_limit["status"] in {"PASS", "CONCERNS"}
    source.write_text(original + "\n" * 501, encoding="utf-8")
    code = main(["validate", "--workspace", str(workspace), "--config", str(config), "--json"])
    validated = json.loads(capsys.readouterr().out)
    assert code == 1 and validated["code"] == "BASE_LIB.SOURCE.MAX_LINES"
    code = main(["quality-check", "--workspace", str(workspace), "--json"])
    checked = json.loads(capsys.readouterr().out)
    assert code == 1
    assert any(item["rule_id"] == "BASE_LIB.SOURCE.MAX_LINES" for item in _formal_findings(checked, "error"))
    source.write_text(original + "\n// " + "中" * ((60000 - len(original.encode("utf-8")) - 4) // 3), encoding="utf-8")
    exact_bytes = len(source.read_bytes())
    source.write_bytes(source.read_bytes() + b"x" * (60000 - exact_bytes))
    code = main(["validate", "--workspace", str(workspace), "--config", str(config), "--json"])
    at_byte_limit = json.loads(capsys.readouterr().out)
    assert code == 0 and at_byte_limit["status"] in {"PASS", "CONCERNS"}
    source.write_text(original + "\n// " + "中" * 20000 + "\n", encoding="utf-8")
    code = main(["validate", "--workspace", str(workspace), "--config", str(config), "--json"])
    oversized_bytes = json.loads(capsys.readouterr().out)
    assert code == 1 and oversized_bytes["code"] == "BASE_LIB.SOURCE.MAX_BYTES"


def test_registered_node_base_lib_dependency_chain_uses_shared_policy(tmp_path: Path, capsys) -> None:
    workspace, project, config = _project_case(tmp_path)
    library = project / "base_lib"
    source = library / "text.ts"
    source.write_text(
        'import { step1 } from "./step1.ts";\n'
        'export function normalizeName(value: string): string { return step1(value); }\n',
        encoding="utf-8",
    )
    from vibeflow.targets.shared.quality_support.policy_data import COMMON_POLICY_DATA
    from vibeflow.tooling.project.resources import prepare_workflow_catalogs

    def check(steps: int):
        text_manifest = sdk_resource(project, 'base_lib', 'example.text')
        text_data = json.loads(text_manifest.read_text(encoding="utf-8"))
        text_data["dependencies"] = ["example.step1"]
        text_manifest.write_text(json.dumps(text_data), encoding="utf-8")
        for index in range(1, steps + 1):
            next_call = (
                f'import {{ step{index + 1} }} from "./step{index + 1}.ts";\n'
                if index < steps else ""
            )
            body = f"step{index + 1}(value)" if index < steps else "value.trim()"
            (library / f"step{index}.ts").write_text(
                next_call + f"export function step{index}(value: string): string {{ return {body}; }}\n",
                encoding="utf-8",
            )
            descriptor = {
                "kind": "base_lib", "id": f"example.step{index}",
                "display_name": f"Step {index}", "description": "Pure text helper.",
                "implementations": [{"language": "typescript", "targets": ["browser", "node"],
                                     "source": {"kind": "file", "ref": f"base_lib/step{index}.ts"}}],
                "dependencies": [f"example.step{index + 1}"] if index < steps else [],
                "external_packages": [],
            }
            sdk_resource(project, "base_lib", f"example.step{index}").write_text(
                json.dumps(descriptor), encoding="utf-8",
            )
        catalogs = prepare_workflow_catalogs(project / "configs/greeting.jsonc")
        return _registered_rule_report(
            project, policy_data=COMMON_POLICY_DATA,
        )

    warning = [item for item in check(3).findings
               if item.rule_id == "NODE.MAINTAINABILITY.DEPENDENCY_CHAIN_TOO_DEEP"]
    assert len(warning) == 1 and warning[0].severity == "warning"
    assert warning[0].details["longest_chain_length"] == 5
    code = main(["quality-check", "--workspace", str(workspace), "--json"])
    checked = json.loads(capsys.readouterr().out)
    assert code == 0 and any(
        item["rule_id"] == "NODE.MAINTAINABILITY.DEPENDENCY_CHAIN_TOO_DEEP"
        for item in _formal_findings(checked, "warning")
    )
    code = main(["validate", "--workspace", str(workspace), "--config", str(config), "--json"])
    validated_warning = json.loads(capsys.readouterr().out)
    assert code == 0 and any(
        item["rule_id"] == "NODE.MAINTAINABILITY.DEPENDENCY_CHAIN_TOO_DEEP"
        for item in validated_warning["warnings"]
    )
    code = main([
        "build", "--workspace", str(workspace), "--config", str(config),
        "--target", "node", "--profile", "esm-module", "--out-dir", str(tmp_path / "warning-output"),
    ])
    built_warning = json.loads(capsys.readouterr().out)
    assert code == 0 and any(
        item["rule_id"] == "NODE.MAINTAINABILITY.DEPENDENCY_CHAIN_TOO_DEEP"
        for item in built_warning["warnings"]
    )
    _configure_rule_policy(project, {"maintainability": {
        "warn_dependency_chain_length": 5, "max_dependency_chain_length": 6,
    }})
    code = main([
        "quality-check", "--workspace", str(workspace),
        "--json",
    ])
    customized = json.loads(capsys.readouterr().out)
    assert code == 0 and not any(
        item["rule_id"] == "NODE.MAINTAINABILITY.DEPENDENCY_CHAIN_TOO_DEEP"
        for item in _formal_findings(customized, "warning")
    )
    error = [item for item in check(5).findings
             if item.rule_id == "NODE.MAINTAINABILITY.DEPENDENCY_CHAIN_TOO_DEEP"]
    assert len(error) == 1 and error[0].severity == "error"
    assert error[0].details["longest_chain_length"] == 7
    code = main(["validate", "--workspace", str(workspace), "--config", str(config), "--json"])
    validated = json.loads(capsys.readouterr().out)
    assert code == 1 and validated["code"] == "NODE.MAINTAINABILITY.DEPENDENCY_CHAIN_TOO_DEEP", validated
    code = main([
        "build", "--workspace", str(workspace), "--config", str(config),
        "--target", "node", "--profile", "esm-module", "--out-dir", str(tmp_path / "chain-output"),
    ])
    built = json.loads(capsys.readouterr().out)
    assert code == 1 and built["code"] == "NODE.MAINTAINABILITY.DEPENDENCY_CHAIN_TOO_DEEP"


def test_registered_node_direct_recursion_reaches_javascript_quality_cli(
    tmp_path: Path, capsys,
) -> None:
    workspace, project, config = _project_case(tmp_path)
    # SDK resource scope is supplied by this explicit workflow.
    source = project / "nodes/greet.ts"
    source.write_text(
        source.read_text(encoding="utf-8").replace(
            "  const name =", "  await run(inputs, params, context);\n  const name =",
        ),
        encoding="utf-8",
    )
    code = main(["quality-check", "--workspace", str(workspace), "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 0, payload
    assert not _formal_findings(payload, "error")


@pytest.mark.parametrize("unit", ["lines", "bytes"])
def test_registered_node_physical_source_limits_include_file_padding(tmp_path: Path, unit: str) -> None:
    _, project, _ = _project_case(tmp_path)
    source = project / "nodes/greet.ts"
    original = source.read_text(encoding="utf-8")
    from vibeflow.targets.shared.quality_support.policy_data import COMMON_POLICY_DATA

    for extra in (0, 1):
        if unit == "lines":
            size = 500 + extra
            text = "\n".join([*original.splitlines(), *([""] * (size - len(original.splitlines()) - 1)), "// pad"])
            code = "NODE.PURITY.SOURCE_TOO_LARGE" if extra else "NODE.PURITY.SOURCE_NEAR_LIMIT"
        else:
            size = 60000 + extra
            text = original + "\n//" + "x" * (size - len(original.encode("utf-8")) - 3)
            code = "NODE.PURITY.SOURCE_BYTES_TOO_LARGE" if extra else "NODE.PURITY.SOURCE_BYTES_NEAR_LIMIT"
        source.write_text(text, encoding="utf-8")
        report = _registered_rule_report(project, policy_data=COMMON_POLICY_DATA)
        matches = [item for item in report.findings if item.object_type == "node" and item.rule_id == code]
        assert len(matches) == 1 and matches[0].details[unit] == size
        assert matches[0].severity == ("error" if extra else "warning")


def test_registered_node_source_limits_preserve_exact_boundaries(tmp_path: Path) -> None:
    _, project, config = _project_case(tmp_path)
    # SDK resource scope is supplied by this explicit workflow.
    source = project / "nodes/greet.ts"
    original = source.read_text(encoding="utf-8")
    from vibeflow.targets.shared.quality_support.policy_data import COMMON_POLICY_DATA
    from vibeflow.tooling.project.resources import prepare_workflow_catalogs
    catalogs = prepare_workflow_catalogs(project / "configs/greeting.jsonc")

    def findings(text: str):
        source.write_text(text, encoding="utf-8")
        report = _registered_rule_report(
            project, policy_data=COMMON_POLICY_DATA,
        )
        return {item.rule_id: item for item in report.findings if item.object_type == "node"}

    lines = original.splitlines()
    at_lines = findings(original.replace("  return ", "  // Local line\n" * (500 - len(lines)) + "  return "))
    assert "NODE.PURITY.SOURCE_TOO_LARGE" not in at_lines
    assert at_lines["NODE.PURITY.SOURCE_NEAR_LIMIT"].severity == "warning"
    over_lines = findings(original.replace("  return ", "  // Local line\n" * (501 - len(lines)) + "  return "))
    assert over_lines["NODE.PURITY.SOURCE_TOO_LARGE"].details["lines"] == 501
    at_bytes = findings(original.replace("  return ", "  //" + "x" * (60000 - len(original.encode("utf-8")) - 5) + "\n  return "))
    assert "NODE.PURITY.SOURCE_BYTES_TOO_LARGE" not in at_bytes
    assert at_bytes["NODE.PURITY.SOURCE_BYTES_NEAR_LIMIT"].severity == "warning"
    over_bytes = findings(original.replace("  return ", "  //" + "x" * (60001 - len(original.encode("utf-8")) - 5) + "\n  return "))
    assert over_bytes["NODE.PURITY.SOURCE_BYTES_TOO_LARGE"].details["bytes"] == 60001


@pytest.mark.parametrize(
    ("field", "metric"),
    [("max_functions", "function_count"),
     ("max_branches", "branch_count"),
     ("max_nesting_depth", "max_nesting_depth")],
)
def test_registered_base_lib_optional_limits_reach_javascript_quality(
    tmp_path: Path, field: str, metric: str,
) -> None:
    _, project, config = _project_case(tmp_path)
    # SDK resource scope is supplied by this explicit workflow.
    source = project / "base_lib/text.ts"
    source.write_text(
        source.read_text(encoding="utf-8")
        + "\nexport function extra(a: number) { if (a) { if (a > 1) return a; } return 0; }\n",
        encoding="utf-8",
    )
    from copy import deepcopy
    from vibeflow.targets.shared.quality_support.policy_data import COMMON_POLICY_DATA
    from vibeflow.tooling.project.resources import prepare_workflow_catalogs
    catalogs = prepare_workflow_catalogs(project / "configs/greeting.jsonc")
    facts = run_quality_facts_driver({
        "qualityRoot": str(project), "qualityFiles": [str(source)],
    }, package_root=project)
    actual = int(facts.files[0][metric])
    assert actual >= 2
    rule = f"BASE_LIB.COMPLEXITY.{field.upper()}"

    def check(limit: int | None):
        policy = deepcopy(COMMON_POLICY_DATA)
        policy["complexity"][field] = limit
        return _registered_rule_report(
            project, policy_data=policy,
        )

    assert not any(item.rule_id == rule for item in check(None).findings)
    assert not any(item.rule_id == rule for item in check(actual).findings)
    assert any(item.rule_id == rule and item.severity == "error"
               for item in check(actual - 1).findings)


def test_structure_roles_use_descriptor_ownership_not_directory_name(tmp_path: Path, capsys) -> None:
    workspace, project, config = _project_case(tmp_path)
    helper = project / "nodes/helper.ts"
    helper.write_text("export const value = 1;\n", encoding="utf-8")
    ordinary = project / "nodes/ordinary.ts"
    ordinary.write_text("import { value } from './helper.js';\nexport const result = value;\n", encoding="utf-8")
    registered = project / "nodes/greet.ts"
    registered.write_text(
        "import { value } from './helper.js';\n" + registered.read_text(encoding="utf-8") + "\nvoid value;\n",
        encoding="utf-8",
    )
    code = main(["quality-check", "--workspace", str(workspace), "--json"])
    checked = json.loads(capsys.readouterr().out)
    assert code == 1
    structural = [item for item in _formal_findings(checked,"error")]
    structural = [item for item in structural
                  if item["rule_id"] == "VF_IMPORT_OWNER"]
    assert structural, json.dumps(checked)
    assert all(item["object_id"] == "example.greet" for item in structural)
    assert structural[0]["source_location"]["line"] == 1


def test_selected_metrics_keep_one_file_and_sdk_declaration_attribution(tmp_path: Path, capsys) -> None:
    workspace, project, config = _project_case(tmp_path)
    # SDK resource scope is supplied by this explicit workflow.
    manifest = sdk_resource(project, 'node', 'example.greet')
    second = sdk_resource(project, "node", "example.greet.second")
    data = json.loads(manifest.read_text(encoding="utf-8"))
    data["id"] = "example.greet.second"
    second.write_text(json.dumps(data), encoding="utf-8")
    workflow = json.loads(config.read_text())
    workflow["pipeline"]["nodes"].append({"id":"second","definition_id":"example.greet.second", "display_name":"Second", "description":"Another call to the same source"})
    config.write_text(json.dumps(workflow))
    source = project / "nodes/greet.ts"
    source.write_text(source.read_text(encoding="utf-8").replace("  return ", "  // Local implementation\n" * 501 + "  return "), encoding="utf-8")
    code = main(["quality-check", "--workspace", str(workspace), "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 1 and len(payload["reports"]) == 1
    files = scan_javascript_quality(project, package_root=project).files
    assert sum(item.path == "nodes/greet.ts" for item in files) == 1
    node_errors = [item for item in _formal_findings(payload,"error") if item["rule_id"] == "NODE.PURITY.SOURCE_TOO_LARGE"]
    assert {item["object_id"] for item in node_errors} == {
        "example.greet",
        "example.greet.second",
    }
    shutil.copy2(SANDBOX / "project/configs/greeting.jsonc", config)
    code = main(["quality-check", "--workspace", str(workspace), "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 1
    assert payload["reports"][0]["code"] == "NODE.PURITY.SOURCE_TOO_LARGE"


def test_selected_plugin_ownership_is_checked(tmp_path: Path, capsys) -> None:
    workspace, project, config = _project_case(tmp_path)
    # SDK resource scope is supplied by this explicit workflow.
    manifest = sdk_resource(project, 'node', 'example.greet')
    data = json.loads(manifest.read_text(encoding="utf-8"))
    data["implementations"][0]["targets"] = ["browser"]
    manifest.write_text(json.dumps(data), encoding="utf-8")
    source = project / "nodes/greet.ts"
    source.write_text(source.read_text(encoding="utf-8").replace("  const name =", "  void fetch('https://example.invalid/test');\n  const name ="), encoding="utf-8")
    code = main(["quality-check", "--workspace", str(workspace), "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 1 and len(payload["reports"]) == 1
    assert any(item["rule_id"] == "VF_PROMISE_UNOWNED" for item in _formal_findings(payload,"error"))

# Publish controlled definitions before each formal operation.


def test_quality_cli_reports_completed_checks_from_source_and_resource_rules(tmp_path, capsys):
    workspace, project, _ = _project_case(tmp_path)
    code = main(["quality-check", "--workspace", str(workspace), "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 0, payload
    checked = {item["id"] for item in payload["checked"]}
    assert {"source_quality", "node_contract_shape", "node_relationships", "effect_boundaries"} <= checked
    assert "direct_input_writes" not in checked  # Python-only Rule is unavailable on JS.
    assert {"code_security", "general_execution_semantics", "determinism", "all_side_effects"} <= {
        item["id"] for item in payload["not_checked"]}
