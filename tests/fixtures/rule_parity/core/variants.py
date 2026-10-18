"""Remaining finite Core branches, using public facts and real compilation."""

from __future__ import annotations

from dataclasses import replace
import importlib.util
from pathlib import Path
from types import SimpleNamespace


def run_cases(work_root: Path, variant: str, toolchain_root: Path | None = None) -> list[dict]:
    spec = importlib.util.spec_from_file_location("core_parity_support", Path(__file__).with_name("support.py"))
    support = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(support)
    rows = []
    def emit(name,title,family,operation,expected,**kw):
        if variant=="current" and (name.startswith("native.result_") or name=="native.detached_unlocked" or name.startswith("native.nested_lock.") and name.endswith(("detached","planned_detached"))):
            expected=support.expectation(("GRAPH.ASYNC.MIGRATION","error"))
            kw.update(classification="approved_change",notes="Retired concurrency declarations require explicit task targets, including planned and nested calls.")
        support.append(rows,name,title,family,operation,expected,**kw)
    codes = support.expectation
    from vibeflow.targets.shared.quality_support import FileQuality, FunctionQuality, ImportSite, ProjectQualityFacts, QualityPolicy, QualityStructureLimits, QualityStructureRoles, QualityThresholds
    from vibeflow.targets.shared.quality_support.models import QualityStructureConventions
    from vibeflow.targets.shared.quality_support.implementation import CallChain, ImplementationLimits, ImplementationMetrics, analyze_call_graph

    if variant == "baseline":
        from vibeflow.targets.shared.quality_support import evaluate_project_quality
        from vibeflow.targets.shared.quality_support.implementation import (evaluate_node_implementation,
            evaluate_base_lib_implementation, evaluate_base_lib_dependency_chain)
    else:
        from tests.fixtures.rule_parity.core.support import evaluate_standard_project_quality as evaluate_project_quality
        from vibeflow.targets.shared.rule_support.implementation import (check_node_implementation as evaluate_node_implementation,
            check_base_lib_implementation as evaluate_base_lib_implementation, check_base_lib_dependency_chain as evaluate_base_lib_dependency_chain)

    def file(path="sample.py", **changes):
        return replace(FileQuality(path, path[:-3].replace("/", "."), 1, 1, 0, 0, 0, 0, 0, (), ()), **changes)
    def project(files, policy=None):
        return evaluate_project_quality(ProjectQualityFacts(str(work_root), tuple(files)), policy)
    limits = QualityStructureLimits()
    quiet = replace(limits, **{name: 10000 for name in limits.__dataclass_fields__ if name.startswith(("warn_", "max_"))}, enforce_role_imports=False)
    root_subjects = (
        ("root_files", "warn_root_code_files", "max_root_code_files", "ROOT_TOO_MANY_CODE_FILES", lambda n: [file(f"d{i // 8}/f{i}.py") for i in range(n)]),
        ("root_dirs", "warn_code_dirs", "max_code_dirs", "ROOT_TOO_MANY_CODE_DIRS", lambda n: [file(f"d{i}/file.py") for i in range(n)]),
        ("directory_files", "warn_code_files_per_dir", "max_code_files_per_dir", "DIRECTORY_TOO_MANY_CODE_FILES", lambda n: [file(f"pkg/f{i}.py") for i in range(n)]),
        ("directory_depth", "warn_code_dir_depth", "max_code_dir_depth", "DIRECTORY_TOO_DEEP", lambda n: [file("/".join(f"d{i}" for i in range(n)) + "/file.py")]),
        ("child_dirs", "warn_child_code_dirs_per_dir", "max_child_code_dirs_per_dir", "DIRECTORY_TOO_MANY_CHILD_CODE_DIRS", lambda n: [file(f"d{i}/file.py") for i in range(n)]),
        ("root_level", "warn_root_level_code_files", "max_root_level_code_files", "ROOT_LEVEL_CODE_FILE", lambda n: [file(f"f{i}.py") for i in range(n)]),
    )
    for name, warn_field, max_field, diagnostic, make in root_subjects:
        warning, maximum = getattr(limits, warn_field), getattr(limits, max_field)
        policy = QualityPolicy(structure_limits=replace(quiet, **{warn_field: warning, max_field: maximum}))
        for boundary, amount in (("below", warning - 1), ("warn", warning), ("max", maximum), ("above", maximum + 1)):
            emit(f"structure.default.{name}.{boundary}", f"默认结构阈值 {name}/{boundary}={amount}", "project.structure.variants",
                lambda amount=amount, make=make, policy=policy: project(make(amount), policy),
                codes(*(("QUALITY.STRUCTURE." + diagnostic, "error" if amount > maximum else "warning"),) if amount >= warning else ()),
                evidence="core/quality/root_structure.py:77-187,250-278; QualityStructureLimits defaults")
    for name, selected in (("none", None), ("disabled", replace(limits, enabled=False))):
        emit("structure.closed." + name, "未启用Root结构判定 " + name, "project.structure.variants",
            lambda selected=selected: project([file(f"pkg/x{i}.py") for i in range(121)], QualityPolicy(structure_limits=selected)), codes(),
            evidence="core/quality/root_structure.py:27-28; no fake disabled threshold")
    customized_file = replace(QualityThresholds(), max_file_bytes=2, max_functions_per_file=2,
        max_classes_per_file=2, max_public_api_per_file=2, max_file_branches=2)
    customized_function = replace(QualityThresholds(), max_function_lines=2, max_function_branches=2, max_function_nesting=2, max_function_params=2)
    for amount in (2, 3):
        emit(f"project.custom.file.{amount}", "项目文件自定义阈值同边界/超限", "project.files.variants",
            lambda amount=amount: project([file(bytes=amount, function_count=amount, class_count=amount, public_api_count=amount, branch_count=amount)], QualityPolicy(thresholds=customized_file)),
            codes(*(("QUALITY.FILE.MAX_BYTES", "error"), ("QUALITY.FILE.TOO_MANY_FUNCTIONS", "warning"),
                ("QUALITY.FILE.TOO_MANY_CLASSES", "warning"), ("QUALITY.FILE.TOO_WIDE_PUBLIC_API", "warning"),
                ("QUALITY.FILE.TOO_MANY_BRANCHES", "warning")) if amount > 2 else ()), evidence="baseline quality/evaluator.py:95-155 → selected files Rule")
        function = FunctionQuality("customized", 7, 9, amount, amount, amount, amount, "custom")
        emit(f"project.custom.function.{amount}", "项目函数自定义阈值同边界/超限", "project.functions.variants",
            lambda function=function: project([file(functions=(function,))], QualityPolicy(thresholds=customized_function)),
            codes(*tuple(("QUALITY.FUNCTION." + diagnostic, "warning") for diagnostic in ("MAX_LINES", "TOO_MANY_BRANCHES", "TOO_DEEP_NESTING", "TOO_MANY_PARAMS")) if amount > 2 else ()),
            evidence="baseline quality/evaluator.py:158-203 → selected files Rule")
    for field, metric in (("warn_source_lines", "source_lines"), ("warn_source_bytes", "source_bytes")):
        amount = 450 if metric == "source_lines" else 54000
        emit("implementation.warning_disabled." + field, "Node警告阈值显式None", "implementation.variants",
            lambda field=field, metric=metric, amount=amount: evaluate_node_implementation(ImplementationMetrics(**{metric: amount}), replace(ImplementationLimits(), **{field: None})),
            codes(), evidence="core/quality/implementation.py:100-107 nullable warning only")
    for amount in (2, 3, 4):
        emit(f"implementation.custom_chain.{amount}", "Node helper自定义warn2/max3", "implementation.variants",
            lambda amount=amount: evaluate_node_implementation(ImplementationMetrics(call_chain=CallChain(amount, tuple(f"f{i}" for i in range(amount)))),
                replace(ImplementationLimits(), warn_call_chain_length=2, max_call_chain_length=3)),
            codes(("NODE.MAINTAINABILITY.CALL_CHAIN_TOO_DEEP", "error" if amount > 3 else "warning")), evidence="core/quality/implementation.py:114-129")
    for amount in (2, 3, 4):
        def dependency(amount=amount):
            finding = evaluate_base_lib_dependency_chain(CallChain(amount, tuple(f"m{i}" for i in range(amount))),
                replace(ImplementationLimits(), warn_dependency_chain_length=2, max_dependency_chain_length=3))
            return (finding,) if finding is not None else ()
        emit(f"implementation.custom_dependency.{amount}", "BaseLib依赖自定义warn>2/max3", "implementation.variants", dependency,
            codes(*(("NODE.MAINTAINABILITY.DEPENDENCY_CHAIN_TOO_DEEP", "error" if amount > 3 else "warning"),) if amount > 2 else ()), evidence="core/quality/implementation.py:153-168")

    role_cases = (
        ("inferred_node", "nodes/a.py", "utils/b.py", False),
        ("inferred_task_node", "task_nodes/a.py", "utils/b.py", False),
        ("inferred_custom_nodes", "custom_nodes/a.py", "utils/b.py", False),
        ("inference_off", "nodes/a.py", "utils/b.py", False),
        ("module_base", "nodes/a.py", "vendor/b.py", True),
        ("path_base", "nodes/a.py", "vendor/b.py", True),
        ("explicit_override", "nodes/a.py", "utils/b.py", False),
        ("prefix_exact", "base_library/a.py", "utils/b.py", False),
    )
    for name, source_path, target_path, declared in role_cases:
        target_module = target_path[:-3].replace("/", ".")
        source_module = source_path[:-3].replace("/", ".")
        files = [file(source_path, imports=(target_module,),
            import_sites=(ImportSite(source_module,target_module,"import "+target_module,source_path,1,1),)), file(target_path)]
        owners = [{"path":source_path,"id":"node","kind":"node","role":"entry","base_libs":["library"]},
                  {"path":target_path,"id":"library","kind":"base_lib","role":"entry","base_libs":[]}]
        if variant == "baseline":
            historical_options={"inference_off":{"infer_roles_from_path":False},
                "module_base":{"base_lib_modules":("vendor",)}, "path_base":{"base_lib_paths":("vendor",)},
                "explicit_override":{"module_roles":{"nodes.a":"unknown"}},
                "prefix_exact":{"base_lib_paths":("base_lib",)}}
            roles = QualityStructureRoles(**historical_options.get(name, {}))
        else:
            roles = QualityStructureRoles(_resource_scopes=({"id":"selected","owners":owners},) if declared else ())
        changed = name.startswith("inferred_")
        emit("roles." + name, "源码身份只来自真实声明 " + name, "project.structure.variants",
            lambda files=files, roles=roles: project(files, QualityPolicy(structure_limits=replace(quiet, enforce_role_imports=True), structure_roles=roles)),
            codes(*(("QUALITY.STRUCTURE.NODE_UNDECLARED_PROJECT_IMPORT","error"),) if variant == "baseline" and changed else ()),
            classification="approved_change" if changed else "preserved",
            notes="目录名不再赋予未声明源码Node或BaseLib身份；真实资源依赖仍由明确归属检查。",
            evidence="core/quality/root_structure.py; core/quality/resource_imports.py")
    for stem, exempt in (("runner", True), ("custom_runner", False), ("entry", True)):
        conventions = QualityStructureConventions(distance_exempt_stems=("runner", "entry"))
        source = file(f"a/b/{stem}.py", imports=("d.e._helper",))
        emit("distance.stem." + stem, "远距离免检stem精确匹配 " + stem, "project.structure.variants",
            lambda source=source, conventions=conventions: project([source, file("d/e/_helper.py")], QualityPolicy(structure_conventions=conventions)),
            codes(*(("QUALITY.STRUCTURE.DISTANT_INTERNAL_IMPORT", "warning"),) if not exempt else ()), evidence="core/quality/structure_distance.py:155-157")
    for ignored in (False, True):
        conventions = QualityStructureConventions(ignored_prefix_stems=("domain_hidden_helpers",) if ignored else ("__init__",))
        files = [file("caller.py", imports=("domain_hidden_helpers",)), file("domain.py"), file("domain_hidden_helpers.py")]
        emit("structure.ignored_stem." + str(ignored), "内部文件stem显式免检", "project.structure.variants",
            lambda files=files, conventions=conventions: project(files, QualityPolicy(structure_conventions=conventions)),
            codes(*(("QUALITY.STRUCTURE.INTERNAL_MODULE_IMPORTED_EXTERNALLY", "warning"),) if not ignored else ()), evidence="core/quality/structure_distance.py:64-69; structure.py:76-109")
    for public_api, require_exports in ((0, True), (1, True), (0, False)):
        convention = QualityStructureConventions(require_exports_for_public_entry=require_exports)
        targets = tuple(f"domain_part{i}_helpers" for i in range(4))
        files = [file("caller.py", imports=targets), file("domain.py", public_api_count=public_api), *(file(name + ".py") for name in targets)]
        emit(f"structure.public_entry.{public_api}.{require_exports}", "public entry实际export前提", "project.structure.variants",
            lambda files=files, convention=convention: project(files, QualityPolicy(structure_conventions=convention)),
            codes(("QUALITY.STRUCTURE.INTERNAL_MODULE_IMPORTED_EXTERNALLY", "warning"),
                *(("QUALITY.STRUCTURE.PUBLIC_ENTRY_BYPASSED", "warning"),) if public_api or not require_exports else ()), evidence="core/quality/structure.py:297-326,368-372")

    for name, graph, expected_codes, longest in (
        ("diamond", {"a": ("b", "c"), "b": ("d",), "c": ("d",), "d": ()}, (), ["a", "b", "d"]),
        ("self_cycle", {"a": ("a",)}, (), ["a"]),
        ("duplicate_import", {"a": ("b", "b"), "b": ()}, (), ["a", "b"]),
        ("external_missing", {"a": ("external.library",)}, (), ["a"]),
    ):
        files = [file(module + ".py", imports=targets, import_sites=tuple(ImportSite(module, target, "import " + target, module + ".py", 9, 2) for target in targets)) for module, targets in graph.items()]
        emit("dependencies." + name, "项目依赖特殊路径 " + name, "project.dependencies.variants",
            lambda files=files: project(files), codes(*expected_codes, metrics={"longest_dependency_chain": longest}),
            classification="baseline_limitation" if name == "self_cycle" else "preserved",
            notes="Public project evaluation deliberately removes resolved self-import edges; the explicit dependency algorithm is tested separately." if name == "self_cycle" else "",
            evidence="core/quality/dependencies.py:156-191; evaluator local graph resolution")
    from vibeflow.targets.shared.quality_support.dependencies import dependency_findings
    emit("dependencies.self_cycle_direct", "直接公共依赖算法仍识别显式自环", "project.dependencies.variants",
        lambda: dependency_findings({"a": ("a",)}, {}, QualityThresholds())[0], codes(("QUALITY.DEPENDENCY.CYCLE", "error")),
        notes="This checks the direct public algorithm, not a claim that the default evaluator retains self-import edges.", evidence="core/quality/dependencies.py:51-70,186-200")
    for name, calls, entry, length in (("diamond", {"run": ("a", "b"), "a": ("leaf",), "b": ("leaf",), "leaf": ()}, "run", 3),
        ("unknown_target", {"run": ("external",)}, "run", 1), ("unknown_entry", {"run": ()}, "absent", 0)):
        def call_graph(calls=calls, entry=entry):
            chain = analyze_call_graph(calls, entry=entry)
            return {"status": "PASS", "codes": [], "positions": [], "metrics": support.plain(chain), "message": "Actual public call-graph result."}
        emit("call_graph." + name, "helper多路径/外部引用 " + name, "implementation.variants", call_graph,
            codes(metrics={"length": length}), evidence="core/quality/implementation.py:17-38")
    for name, function in (("empty_fingerprint", FunctionQuality("one", 3, 5, 3, 0, 0, 0, "")),
        ("different_fingerprint", FunctionQuality("one", 3, 5, 3, 0, 0, 0, "one"))):
        other = replace(function, qualname="two", ast_fingerprint="two" if name == "different_fingerprint" else "")
        emit("duplicate." + name, "重复函数fingerprint实际边界 " + name, "project.duplicates.variants",
            lambda function=function, other=other: project([file("one.py", functions=(function,)), file("two.py", functions=(other,))]),
            codes(*(("QUALITY.DUPLICATE.AST_FINGERPRINT", "warning"),) if name == "empty_fingerprint" else ()),
            classification="baseline_limitation" if name == "empty_fingerprint" else "preserved",
            notes="The baseline actively groups empty fingerprints when lines>=3; this case records that limitation, not invented analysis.", evidence="core/quality/duplicates.py:7-13")
    _graph_variants(emit, codes, support, variant)
    return rows


def _graph_variants(emit, codes, support, variant):
    from vibeflow.core.compiler import compile_core
    from vibeflow.core.contracts import DataProvider, DataRequirement
    from vibeflow.core.flow import EdgeSpec, ExecutionLockSpec, GraphConfig, LoopSpec, NodeMetadata, NodeSpec, NodesetSpec
    from vibeflow.core.models import CoreCompileRequest, ImplementationFact, ImplementationFacts, TargetFeatureSet
    from vibeflow.targets.shared.quality_support.workflow_rules.joins import append_join_policy_health
    from vibeflow.targets.shared.quality_support.workflow_rules.flow_data import append_data_contract_warnings
    from vibeflow.targets.shared.quality_support.workflow_rules.planned import graph_has_blocking_planned, graph_has_planned, planned_health_events
    from vibeflow.core.planned import PlannedBehavior

    def retired(mode, *, nested=False, planned=False):
        from vibeflow.core.config.graph import parse_graph_config_data
        call = {'id':'work','type_used':'variant.work','async':mode,
            **({'result_key':'worker.out'} if mode == 'result_key' else {}),
            **({'status':'planned','flow_kind':'process','requires':[],'provides':[]} if planned else {})}
        data = {'pipeline':{'nodes':[call]}}
        if nested:
            data = {'pipeline':{'nodes':[]},'nodesets':[{'type_key':'variant.child','display_name':'Child',
                'description':'Nested migration','requires':[],'provides':[],'pipeline':{'nodes':[call]}}]}
        return parse_graph_config_data(data)
    def node(name, kind="process", **fields):
        return NodeSpec(name, "variant." + name, flow_kind=kind, metadata=NodeMetadata(name, "Portable branch probe."), **fields)
    def compile(graph):
        collected, visited = {}, set()
        def walk(current, known):
            if id(current) in visited:
                return
            visited.add(id(current))
            known = {**known, **current.nodesets}
            for spec in current.nodes:
                if spec.type_used not in known and spec.type_used != "vibeflow.io" and not spec.type_used.startswith("vibeflow.loop."):
                    collected[spec.type_used] = ImplementationFact(spec.type_used, flow_kind=spec.flow_kind, requires=spec.requires, provides=spec.provides)
            for definition in current.nodesets.values():
                walk(definition.graph, known)
        walk(graph, {})
        return compile_core(CoreCompileRequest(graph, ImplementationFacts(tuple(collected.values())),
            TargetFeatureSet("probe", frozenset({"global_state", "execution_locks"}))))
    result = node("worker", provides=(DataProvider("worker.out", "worker.value"),), **({"async_mode":"result_key","result_key":"worker.out"} if variant == "baseline" else {}))
    consumer = node("consumer", requires=(DataRequirement("worker.value", "exactly_one"),))
    for conditional in (False, True):
        graph = GraphConfig((result, consumer), (EdgeSpec("worker", "consumer", schedule=True, transfer=True, when="choice == 1" if conditional else ""),), execution_lock=ExecutionLockSpec("shared"))
        emit("native.result_consumer." + str(conditional), "锁域result静态消费者是否无条件", "native.async.variants",
            lambda graph=graph: compile(graph) if variant == "baseline" else retired("result_key"), codes(*(("GRAPH.EXECUTION_LOCK.RESULT_UNJOINABLE", "error"),) if conditional else (),
                **({"message_contains": "statically provable"} if conditional else {})), evidence="core/compiler.py:561-612,657-697")
    emit("native.result_without_outgoing", "无锁result且没有任何后继的原生编译边界", "native.async.variants",
        lambda: compile(GraphConfig((result,))) if variant == "baseline" else retired("result_key"), codes(), classification="baseline_limitation",
        notes="Native route rejection is conditional on having an effective outgoing edge; absence alone is not rejected outside a lock. This is not proof of executable workflow health.", evidence="core/compiler.py:538-541")
    emit("native.detached_unlocked", "detached在无锁域可编译", "native.async.variants",
        lambda: compile(GraphConfig((node("background", async_mode="detached"),))) if variant == "baseline" else retired("detached"), codes(), evidence="core/compiler.py:575-593")
    for invocation in ("nodeset", "loop"):
        for scenario in ("same_key", "different_key", "detached", "planned_detached"):
            worker = node("work", **({"async_mode":"detached" if "detached" in scenario else ""} if variant == "baseline" else {}),
                status="planned" if scenario == "planned_detached" else "implemented",
                execution_lock=ExecutionLockSpec("other" if scenario == "different_key" else "shared") if "key" in scenario else None)
            child = NodesetSpec("variant.child", "Child", "Nested execution-lock branch.", (), (), GraphConfig((worker,)))
            call = NodeSpec("stage", child.type_key) if invocation == "nodeset" else NodeSpec("stage", "vibeflow.loop.while", loop=LoopSpec(body=child.type_key))
            graph = GraphConfig((call,), nodesets={child.type_key: child}, execution_lock=ExecutionLockSpec("shared"))
            diagnostic = "GRAPH.EXECUTION_LOCK.NESTED_KEY_CONFLICT" if scenario == "different_key" else "GRAPH.EXECUTION_LOCK.DETACHED_FORBIDDEN" if scenario == "detached" else ""
            emit(f"native.nested_lock.{invocation}.{scenario}", "Nodeset/Loop实际嵌套锁 " + scenario, "native.execution_lock.variants",
                lambda graph=graph,scenario=scenario: retired("detached",nested=True,planned=scenario=="planned_detached") if variant == "current" and "detached" in scenario else compile(graph), codes(*((diagnostic, "error"),) if diagnostic else (),
                    **({"message_contains": "incompatible key" if scenario == "different_key" else "cannot use async='detached'"} if diagnostic else {})),
                evidence="core/compiler.py:561-655,979-1030; executable/planned distinction")

    def review(graph, topic):
        compilation = compile(graph)
        state = SimpleNamespace(errors=[], warnings=[])
        checker = append_join_policy_health if topic == "join" else append_data_contract_warnings
        checker(compilation.workflow.graph, compilation.compiled_graph, state)
        return (*state.errors, *state.warnings)
    for name, left, right, exclusive in (
        ("eq_neq", "choice == 1", "choice != 1", True), ("neq_eq", "choice != 1", "choice == 1", True),
        ("neq_neq", "choice != 1", "choice != 2", False), ("same_eq", "choice == 1", "choice == 1", False),
        ("different_keys", "left == 1", "right == 2", False),
    ):
        graph = GraphConfig((node("start", "terminal"), node("route", "decision"), node("left"), node("right"), node("join", join_policy="all"), node("end", "terminal")),
            (EdgeSpec("start", "route", schedule=True), EdgeSpec("route", "left", when=left, schedule=True), EdgeSpec("route", "right", when=right, schedule=True),
             EdgeSpec("left", "join", schedule=True), EdgeSpec("right", "join", schedule=True), EdgeSpec("join", "end", schedule=True)))
        emit("workflow.exclusive." + name, "all join条件互斥实际operator " + name, "workflow.join.variants",
            lambda graph=graph: review(graph, "join"), codes(*(("GRAPH.JOIN.ALL_BRANCHES_MUTUALLY_EXCLUSIVE", "error"),) if exclusive else ()),
            evidence="core/quality/workflow_rules/join_exclusivity.py:195-208")
    for bypass in (False, True):
        nodes = (node("start", "terminal"), node("route", "decision"), node("left"), node("right"), node("left_tail"), node("right_tail"), node("join", join_policy="all"), node("end", "terminal"))
        edges = (EdgeSpec("start", "route", schedule=True), EdgeSpec("route", "left", when="choice == 1", schedule=True), EdgeSpec("route", "right", when="choice == 2", schedule=True),
            EdgeSpec("left", "left_tail", schedule=True), EdgeSpec("right", "right_tail", schedule=True), EdgeSpec("left_tail", "join", schedule=True), EdgeSpec("right_tail", "join", schedule=True), EdgeSpec("join", "end", schedule=True))
        if bypass:
            edges += (EdgeSpec("start", "left_tail", schedule=True),)
        graph = GraphConfig(nodes, edges)
        emit("workflow.exclusive.dominators." + str(bypass), "Decision间接分支和非支配入口对照", "workflow.join.variants",
            lambda graph=graph: review(graph, "join"), codes(*(("GRAPH.JOIN.ALL_BRANCHES_MUTUALLY_EXCLUSIVE", "error"),) if not bypass else ()),
            evidence="core/quality/workflow_rules/join_exclusivity.py:98-133,138-165")
    for cardinality in ("exactly_one", "optional_one", "all"):
        graph = GraphConfig((node("left", provides=(DataProvider("left.out", "value"),)), node("right", provides=(DataProvider("right.out", "value"),)), node("join", requires=(DataRequirement("value", cardinality),))),
            (EdgeSpec("left", "join", schedule=True), EdgeSpec("right", "join", schedule=True)))
        emit("workflow.cardinality." + cardinality, "多个无条件provider与cardinality " + cardinality, "workflow.data.variants",
            lambda graph=graph: review(graph, "data"), codes(*(("GRAPH.DATA.TYPE_CARDINALITY_AMBIGUOUS", "error"),) if cardinality != "all" else ()),
            evidence="core/quality/workflow_rules/flow_data.py:251-276")
    for exported in (False, True):
        graph = GraphConfig((node("producer", provides=(DataProvider("producer.out", "value"),)),), outputs=(DataProvider("producer.out", "value"),) if exported else ())
        emit("workflow.exported_provider." + str(exported), "Root输出声明抑制未消费provider", "workflow.data.variants",
            lambda graph=graph: review(graph, "data"), codes(*(("GRAPH.DATA.UNCONSUMED_PROVIDER", "warning"),) if not exported else ()), evidence="core/quality/workflow_rules/flow_data.py:290-299")
    graph = GraphConfig((node("producer", provides=(DataProvider("producer.out", "value"),)), node("middle"),
        node("consumer", requires=(DataRequirement("value", "exactly_one"),))),
        (EdgeSpec("producer", "middle", schedule=True), EdgeSpec("middle", "consumer", schedule=True),
         EdgeSpec("producer", "consumer", schedule=False, transfer=True)))
    emit("workflow.bypass.actual_payload", "有实际同type数据的transfer bypass正常对照", "workflow.data.variants",
        lambda: review(graph, "data"), codes(), evidence="core/quality/workflow_rules/flow_data.py:130-166")
    for exclusive in (False, True):
        graph = GraphConfig((node("route", "decision"), node("left", provides=(DataProvider("left.out", "value"),)),
            node("right", provides=(DataProvider("right.out", "value"),)), node("consumer", requires=(DataRequirement("value", "exactly_one"),))),
            (EdgeSpec("route", "left", when="choice == 1", schedule=True), EdgeSpec("route", "right", when="choice == 2" if exclusive else "choice == 1", schedule=True),
             EdgeSpec("left", "consumer", when="ready == 1" if not exclusive else "", schedule=True), EdgeSpec("right", "consumer", schedule=True)))
        emit("workflow.cardinality.conditional." + str(exclusive), "互斥provider免歧义/普通conditional仅warning", "workflow.data.variants",
            lambda graph=graph: review(graph, "data"), codes(*(("GRAPH.DATA.TYPE_CARDINALITY_AMBIGUOUS", "warning"),) if not exclusive else ()),
            evidence="core/quality/workflow_rules/flow_data.py:251-276,336-359")
    for cardinality in ("exactly_one", "all"):
        graph = GraphConfig((node("a", provides=(DataProvider("a.value", "value"),)),
            node("consumer", requires=(DataRequirement("value", cardinality),)), node("b", provides=(DataProvider("b.value", "value"),))),
            (EdgeSpec("a", "consumer", schedule=True, transfer=True), EdgeSpec("consumer", "b", schedule=True, transfer=False),
             EdgeSpec("b", "consumer", schedule=False, transfer=True)))
        def mixed_cycle(graph=graph):
            compilation = compile(graph)
            state = SimpleNamespace(errors=[], warnings=[])
            append_data_contract_warnings(compilation.workflow.graph, compilation.compiled_graph, state)
            actual = support.observe(lambda: (*state.errors, *state.warnings))
            actual["metrics"]["compiled"] = {
                "schedule_edges": sorted(list(edge.pair) for edge in compilation.compiled_graph.resolved_schedule_edges),
                "transfer_edges": sorted(list(edge.pair) for edge in compilation.compiled_graph.resolved_transfer_edges)}
            return actual
        emit("workflow.cardinality.mixed_role_cycle." + cardinality, "两种角色各自无环但合并回路的数据判定 " + cardinality,
            "workflow.data.variants", mixed_cycle,
            codes(*(("GRAPH.DATA.TYPE_CARDINALITY_AMBIGUOUS", "warning"),) if cardinality == "exactly_one" else (),
                metrics={"compiled.schedule_edges": [["a", "consumer"], ["consumer", "b"]],
                    "compiled.transfer_edges": [["a", "consumer"], ["b", "consumer"]]}),
            notes="Actual compilation succeeds: the union has consumer↔b while schedule and transfer separately remain acyclic. The one-source requirement warns; all is a normal control.",
            evidence="core/compiler.py schedule/transfer cycle checks; core/quality/workflow_rules/flow_data.py:263-264,361-370")

    from vibeflow.targets.shared.quality_support.nodesets import nodeset_quality_findings
    for invocation in ("nodeset", "loop"):
        def nested_call(name, target):
            return NodeSpec(name, target) if invocation == "nodeset" else NodeSpec(name, "vibeflow.loop.while", loop=LoopSpec(body=target))
        first = NodesetSpec("variant.first", "First", "Mutual reference declaration.", (), (), GraphConfig((nested_call("second", "variant.second"),)))
        second = NodesetSpec("variant.second", "Second", "Mutual reference declaration.", (), (), GraphConfig((nested_call("first", "variant.first"),)))
        graph = GraphConfig((), nodesets={first.type_key: first, second.type_key: second})
        emit("planned.unused_mutual_recursion." + invocation, "未调用互递归定义仍须产生结构事实 " + invocation, "workflow.nodesets.variants",
            lambda graph=graph: nodeset_quality_findings(graph), codes(("NODESET.RECURSION", "error")),
            notes="This tests the public declaration algorithm; formal unused-declaration dispatch is independently tested and currently regresses.", evidence="core/nodeset_dependencies.py; core/quality/nodesets.py:34-48")

    for behavior in ("blocking", "transparent", "python_stub"):
        planned = node("future", status="planned", planned_behavior=PlannedBehavior(behavior, "stubs/future.py" if behavior == "python_stub" else ""))
        child = NodesetSpec("variant.parent", "Parent", "Implemented parent containing a planned child.", (), (), GraphConfig((planned,)))
        graph = GraphConfig((), nodesets={child.type_key: child})
        def planned_events(graph=graph):
            events = planned_health_events(graph)
            actual = support.observe(lambda: events)
            actual["metrics"]["implementation_checks"] = [support.plain(item) for item in events if not hasattr(item, "rule_id")]
            return actual
        emit("planned.parent." + behavior, "父定义planned行为分支 " + behavior, "workflow.planned.variants", planned_events,
            codes(("GRAPH.PLANNED.NODE", "warning"), ("GRAPH.PLANNED.PARENT_HAS_PLANNED_CHILD", "error" if behavior == "blocking" else "warning"),
                metrics={"implementation_checks": [{"behavior": {"kind": "python_stub", "stub_module": "stubs/future.py"}, "object_type": "node", "object_id": "future", "project_root": ""}]} if behavior == "python_stub" else {"implementation_checks": []}),
            evidence="core/quality/workflow_rules/planned.py:54-63,140-164")
    for behavior in ("blocking", "transparent", "python_stub"):
        for used in (False, True):
            child = NodesetSpec("variant.planned", "Planned", "Unused/referenced planned definition.", (), (), GraphConfig(()), status="planned",
                planned_behavior=PlannedBehavior(behavior, "stubs/child.py" if behavior == "python_stub" else ""))
            graph = GraphConfig((NodeSpec("stage", child.type_key),) if used else (), nodesets={child.type_key: child})
            def planned_flags(graph=graph):
                actual = support.observe(lambda: planned_health_events(graph))
                actual["metrics"].update(has_planned=graph_has_planned(graph), has_blocking_planned=graph_has_blocking_planned(graph))
                return actual
            emit("planned.reference_flags." + behavior + "." + str(used), "planned声明告警与实际引用flag分离 " + behavior, "workflow.planned.variants", planned_flags,
                codes(("GRAPH.PLANNED.NODESET", "warning"), metrics={"has_planned": used, "has_blocking_planned": used and behavior == "blocking"}), evidence="core/quality/workflow_rules/planned.py:67-120")
