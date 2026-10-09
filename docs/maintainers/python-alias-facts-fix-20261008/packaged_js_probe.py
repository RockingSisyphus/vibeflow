"""Check generated-package JS Rules via SDK catalogs and native analysis.

Run with an installed wheel's Python using -I, or pass the generated kernel zip
with --kernel. No checkout product code or test fixture modules are imported.
The external toolchain is only read; all probe inputs and its JSON report are
created beneath --work-root / --report.
"""
from __future__ import annotations

import argparse
from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
import traceback


def arguments():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kernel", type=Path, help="generated vibeflow-kernel.zip; omit for installed wheel")
    parser.add_argument("--toolchain-root", required=True, type=Path)
    parser.add_argument("--node-command", default="node")
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--work-root", type=Path)
    return parser.parse_args()


def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main():
    args = arguments()
    checkout = Path(__file__).resolve().parents[3]
    # -I is recommended, and this also removes any inherited checkout PYTHONPATH.
    forbidden_import_roots = {checkout, checkout / "src", checkout / "tools", checkout / "tests"}
    sys.path[:] = [entry for entry in sys.path if entry and Path(entry).resolve() not in forbidden_import_roots]
    if args.kernel:
        args.kernel = args.kernel.resolve(strict=True)
        sys.path.insert(0, str(args.kernel))
    args.toolchain_root = args.toolchain_root.resolve(strict=True)
    if not (args.toolchain_root / "node_modules").is_dir():
        raise ValueError("--toolchain-root must contain the installed TypeScript/esbuild node_modules")
    args.report = args.report.resolve()
    args.report.parent.mkdir(parents=True, exist_ok=True)
    work_parent = (args.work_root or args.report.parent / "packaged-js-probe-work").resolve()
    work_parent.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="run-", dir=work_parent))

    import vibeflow
    from vibeflow.core.flow import GraphConfig, NodeSpec
    from vibeflow.core.rules import RuleContext
    from vibeflow.core.rules.models import plain
    from vibeflow.targets.javascript.build.driver_session import DriverScope
    from vibeflow.targets.javascript.build.project_resources import target_neutral_import_policy, driver_import_policy
    from vibeflow.targets.javascript.build.rule_session import _RuleSession
    from vibeflow.targets.javascript.quality.rules import run_javascript_rules
    from vibeflow.targets.javascript.resources import materialized_resources, resource
    from vibeflow.tooling.project.descriptor_loader import load_workflow_catalogs
    import vibeflow.targets.javascript.build.rule_session as service

    package_file = str(vibeflow.__file__)
    if Path(package_file).resolve().is_relative_to(checkout / "src"):
        raise AssertionError("probe imported checkout product code: " + package_file)
    if args.kernel and not package_file.startswith(str(args.kernel) + "/"):
        raise AssertionError("probe did not import the explicitly selected kernel: " + package_file)
    result = {"status": "running", "package_file": package_file,
              "kernel": str(args.kernel) if args.kernel else None,
              "python": sys.executable, "toolchain_root": str(args.toolchain_root),
              "node_command": args.node_command, "work": str(work), "cases": [],
              "driver_sha256": hashlib.sha256(resource("toolchain_driver.mjs").read_bytes()).hexdigest()}
    requests = []
    original_driver = service.run_rule_check_driver

    def recording_driver(request, **options):
        requests.append(plain(request))
        return original_driver(request, **options)

    service.run_rule_check_driver = recording_driver
    node_id = "probe.effect_node"
    base = {"id": "probe.base", "calls": [
        {"id": "effects", "rule_id": "vibeflow.no_side_effects"},
        {"id": "imports", "rule_id": "vibeflow.import_side_effects"}],
        "entrypoints": {"import": ["imports"], "static": ["effects"], "run": []}}

    def override(identifier, params, mode="both"):
        calls = ["native"]
        return {"id": identifier, "calls": [{"id": "native", "ruleset_id": "probe.base"}],
                "relations": [{"source": "$self", "target": "native/" + topic,
                               "kind": "overrides", "params": params} for topic in ("effects", "imports")],
                "entrypoints": {"import": [] if mode == "effects" else calls,
                                "static": [] if mode == "imports" else calls, "run": []}}

    def project_inputs(name, text, rulesets, selected):
        project = work / name
        project.mkdir()
        (project / "node_modules").symlink_to(args.toolchain_root / "node_modules", target_is_directory=True)
        dump(project / "package.json", {"name": "vibeflow-packaged-probe", "private": True, "type": "module"})
        for filename in ("package-lock.json",):
            if (args.toolchain_root / filename).is_file():
                shutil.copy2(args.toolchain_root / filename, project / filename)
        source = project / "implementation.ts"
        source.write_text(text, encoding="utf-8")
        declaration = {"type_key": node_id, "display_name": "Packaged effect probe",
                       "description": "An explicit generated SDK Node used for package acceptance.",
                       "version": "1", "flow_kind": "process", "contract": {"requires": [], "provides": []},
                       "implementations": [{"language": "typescript", "targets": ["node"],
                                            "source": {"kind": "file", "ref": source.name, "export": "run"}}],
                       "rulesets": [selected]}
        lines = ['import {definePlugin,defineNode,defineRuleset} from "@vibeflow/plugin";',
                 "const node = defineNode(" + json.dumps(declaration) + ");"]
        names = []
        for index, definition in enumerate([base, *rulesets]):
            names.append("ruleset_" + str(index))
            lines.append("const " + names[-1] + " = defineRuleset(" + json.dumps(definition) + ");")
        lines.append('export const plugin = definePlugin({id:"probe.packaged",resources:[node,' + ",".join(names) + "]});")
        (project / "code_plugin.ts").write_text("\n".join(lines) + "\n", encoding="utf-8")
        dump(project / "vibeflow_project.jsonc", {"project_target": "javascript", "quality_enabled": False,
                                                 "javascript": {"package_root": ".", "external_packages": ["@scope/pkg"]}})
        dump(project / "vibeflow_config.jsonc", {"roots": [{"id": "project", "path": "."}]})
        config = project / "workflow.jsonc"
        dump(config, {"plugins": [{"source": {"kind": "file", "ref": "code_plugin.ts", "export": "plugin"}}],
                      "pipeline": {"nodes": [{"id": "probe", "type_used": node_id}]}})
        catalogs = load_workflow_catalogs(project, project_config=project / "vibeflow_project.jsonc",
                                          workflow_config=config, node_command=args.node_command)
        policy, _ = target_neutral_import_policy(catalogs=catalogs, project_root=project,
                                                  allowed_external={"@scope/pkg"}, node_ids=frozenset({node_id}))
        return project, source, catalogs, policy

    def record_case(name, params, text, denied, *, mode="both", code=None, detail=None):
        identifier = "probe." + name
        project, source, catalogs, policy = project_inputs(name, text, [override(identifier, params, mode)], identifier)
        before = len(requests)
        report = run_javascript_rules(GraphConfig(nodes=(NodeSpec("probe", node_id),), rulesets=()), catalogs,
                    project_root=project, package_root=project, target="node", import_policy=policy,
                    node_command=args.node_command)
        findings = tuple(report.findings)
        selected_requests = [item for item in requests[before:] if item.get("ruleParams")]
        invocations = [item for execution in report.results[node_id] for item in execution.plan.invocations]
        assert invocations, name + ": no formal RulePlan invocations"
        assert all(plain(item.params) == params for item in invocations), (name, plain(invocations))
        assert bool(findings) == denied, (name, [item.to_dict() for item in findings])
        if code:
            assert any(item.code == code for item in findings), (name, findings)
        if detail:
            assert any(detail in item.message for item in findings), (name, findings)
        if selected_requests:
            assert all(item["ruleParams"] == params for item in selected_requests), name
            assert all(item["ruleSubjectKind"] == "node" and item["ruleSubjectId"] == node_id
                       for item in selected_requests), name + ": incorrect native Rule subject"
        if not detail:
            assert selected_requests, name + ": did not reach the native driver"
        for finding in findings:
            owner = finding.details.get("source_owner")
            if owner:
                assert owner["kind"] == "node" and "effectScope" not in owner, (name, owner)
        result["cases"].append({"name": name, "params": params, "mode": mode,
                               "denied": bool(findings), "plans": [plain(item.params) for item in invocations],
                               "driver_requests": len(selected_requests),
                               "driver_subjects": [{"kind": item["ruleSubjectKind"], "id": item["ruleSubjectId"],
                                                    "owners": item["importPolicy"]["owners"]} for item in selected_requests],
                               "findings": [item.to_dict() for item in findings]})

    def params(scope, imports=None):
        return {"effect_scope": scope, "policy": {} if imports is None else {"imports": imports}}

    def body(statements="", prelude=""):
        return prelude + "export function run(){" + statements + "return {};}\n"

    try:
        with materialized_resources() as packaged_resources, DriverScope():
            result["materialized_driver"] = str(packaged_resources / "toolchain_driver.mjs")
            record_case("terminal_console", params("terminal"), body('console.log("ok");'), False)
            record_case("terminal_fetch", params("terminal"), body('console.log("ok");void fetch("https://example.invalid");'), True, code="VF_BASE_LIB_HOST_IO", detail="fetch")
            record_case("trusted_console", params("trusted"), body('console.log("ok");'), True, code="VF_BASE_LIB_HOST_IO")
            record_case("global_cache", params("global_state"), body("cache.value += 1;", "const cache = {value:0};\n"), False)
            record_case("none_cache", params("none"), body("cache.value += 1;", "const cache = {value:0};\n"), True)
            record_case("global_prototype", params("global_state"), body("(Array.prototype as any).evil = () => 1;"), True, code="VF_MODULE_STATE")
            record_case("io_fs", params("python_io"), body("void readFile;", 'import {readFile} from "node:fs/promises";\n'), False)
            record_case("io_clock", params("python_io"), body("void Date.now();void Math.random();"), False)
            record_case("terminal_clock", params("terminal"), body("void Date.now();void Math.random();"), True, code="VF_BASE_LIB_HOST_IO")
            record_case("hard_process", params("python_io"), body("const p=process;p.exit(1);"), True, code="VF_BASE_LIB_HOST_IO")
            record_case("io_bare_namespace", params("python_io"), body("void globalThis;"), False)
            for namespace in ("globalThis", "window", "self"):
                record_case("io_slot_" + namespace, params("python_io"), body("(" + namespace + " as any).__probeState = 1;"), False)
                record_case("global_slot_" + namespace, params("global_state"), body("(" + namespace + " as any).__probeState = 1;"), False)
            record_case("none_host_slot", params("none"), body("(globalThis as any).__probeState = 1;"), True)
            record_case("io_namespace_prototype", params("python_io"), body("(globalThis as any).Array.prototype.evil = () => 1;"), True, code="VF_MODULE_STATE")
            policy_cases = [
                ("ban_root", {"banned_roots": ["fs"]}, True),
                ("allow_root", {"banned_roots": ["node:fs"], "allowed_roots": ["fs"]}, False),
                ("ban_module", {"allowed_modules": ["fs"], "banned_modules": ["node:fs/promises"]}, True),
                ("explicit_ban", {"banned_modules": ["fs"], "allowed_roots": ["fs"]}, True)]
            for mode in ("effects", "imports"):
                for suffix, policy, denied in policy_cases:
                    record_case(mode + "_" + suffix, params("python_io", policy), body("void readFile;", 'import {readFile} from "node:fs/promises";\n'), denied, mode=mode, code="VF_IMPORT_POLICY" if denied else None)
                for suffix, policy, denied in (
                    ("scoped_ban", {"banned_roots": ["@scope/pkg"]}, True),
                    ("scoped_allow", {"banned_roots": ["@scope/pkg"], "allowed_modules": ["@scope/pkg/sub"]}, False)):
                    record_case(mode + "_" + suffix, params("none", policy), body("void value;", 'import {value} from "@scope/pkg/sub";\n'), denied, mode=mode, code="VF_IMPORT_POLICY" if denied else None)
            record_case("unknown_scope", params("invented"), body(), True, code="RULE.EXECUTION", detail="effect_scope")
            record_case("irrelevant_policy", {"effect_scope": "none", "policy": {"node_source": {"max_lines": 1}}}, body(), True, code="RULE.EXECUTION", detail="node_source")

            # One SDK catalog, formal RuleSession and source identity exercise both
            # Core source-result caching and the driver request cache with A→B→A.
            selected = [("probe.cache_a", params("terminal"), True),
                        ("probe.cache_b", params("python_io"), False),
                        ("probe.cache_a", params("terminal"), True),
                        ("probe.cache_c", params("python_io", {"banned_roots": ["fs"]}), True),
                        ("probe.cache_b", params("python_io"), False)]
            text = body('console.log("cache");void readFile;', 'import {readFile} from "node:fs";\n')
            definitions = [override(identifier, parameter) for identifier, parameter, _ in (selected[0], selected[1], selected[3])]
            project, source, catalogs, policy = project_inputs("cache_sequence", text, definitions, selected[0][0])
            with ExitStack() as stack:
                session = _RuleSession(stack, catalogs=catalogs, project_root=project, package_root=project,
                                       node_command=args.node_command, target="node")
                context = RuleContext(subject={"kind": "node", "type_key": node_id,
                    "source_identity": ("packaged-probe", str(source), "stable")}, target="node", facts={
                    "source_files": [str(source)], "sources": [{"path": str(source), "text": text}],
                    "analysis_cache": session.analysis_cache, "package_root": str(project),
                    "project_root": str(project), "node_command": args.node_command,
                    "catalogs": catalogs, "source_owners": plain(policy["owners"]),
                    "import_policy": driver_import_policy(policy)})
                counts, sequence = [], []
                for identifier, parameter, denied in selected:
                    native_before = len(requests)
                    executions = session.execute((identifier,), context, before_import=True)
                    # Core de-duplicates aggregate findings on cache aliases;
                    # the cached RuleResult retains the original decision.
                    findings = [item for execution in executions for returned in execution.results.values()
                                for item in returned.findings]
                    assert bool(findings) == denied, (identifier, findings)
                    assert all(plain(item.params) == parameter for execution in executions for item in execution.plan.invocations)
                    rule_results = []
                    for execution in executions:
                        definitions = {item.id: item.rule.id for item in execution.plan.invocations}
                        rules = []
                        for call, returned in execution.results.items():
                            assert returned.state == "completed", (identifier, call, returned.state)
                            assert all(item.definition_id == definitions[call] for item in returned.findings)
                            for record in returned.records.values():
                                if record.type_id == "vibeflow.effect_policy.v1":
                                    assert record.value["effect_scope"] == parameter["effect_scope"]
                            rules.append({"call": call, "definition_id": definitions[call], "state": returned.state,
                                          "records": plain(returned.records),
                                          "findings": [item.to_dict() for item in returned.findings]})
                        rule_results.append(rules)
                    counts.append(len(session.analysis_cache.checks))
                    native_delta = len(requests) - native_before
                    if len(sequence) in (2, 4):
                        assert native_delta == 0, (identifier, native_delta)
                        assert any(item.aliases for item in executions), identifier + ": no Core cache aliases"
                    sequence.append({"ruleset": identifier, "denied": bool(findings), "params": parameter,
                                     "cache_entries": counts[-1], "executed": [list(item.executed) for item in executions],
                                     "aliases": [dict(item.aliases) for item in executions],
                                     "new_native_requests": native_delta, "rule_results": rule_results})
                assert counts[1] > counts[0] and counts[2] == counts[1], counts
                assert counts[3] > counts[2] and counts[4] == counts[3], counts
                result["cache_sequence"] = sequence
            assert all("ownership" not in item.get("ruleTopics", ()) for item in requests)
            assert all("effectScope" not in owner for item in requests for owner in item.get("importPolicy", {}).get("owners", ()))
            assert all(item["ruleSubjectKind"] == "node" and item["ruleSubjectId"] == node_id
                       for item in requests if item.get("ruleParams"))
            result["status"] = "passed"
    except Exception:
        result["status"] = "failed"
        result["error"] = traceback.format_exc()
        raise
    finally:
        service.run_rule_check_driver = original_driver
        result["native_requests"] = len(requests)
        product_modules = {name: str(getattr(module, "__file__", "") or "")
                           for name, module in sorted(sys.modules.copy().items())
                           if name == "vibeflow" or name.startswith("vibeflow.")}
        if args.kernel:
            package_origin = str(args.kernel) + "/vibeflow/"
            foreign = {name: path for name, path in product_modules.items()
                       if not path or not path.startswith(package_origin)}
        else:
            package_origin = Path(package_file).resolve().parent
            foreign = {name: path for name, path in product_modules.items()
                       if not path or not Path(path).resolve().is_relative_to(package_origin)}
        result["product_package_root"] = str(package_origin)
        result["loaded_product_modules"] = product_modules
        result["loaded_product_module_count"] = len(product_modules)
        result["foreign_product_modules"] = foreign
        if foreign:
            result["status"] = "failed"
            result["origin_error"] = "Product modules outside the selected package: " + repr(foreign)
        dump(args.report, result)
        print(json.dumps({"status": result["status"], "report": str(args.report), "cases": len(result["cases"])}))
        assert not foreign, result.get("origin_error")


if __name__ == "__main__":
    main()
