"""Portable baseline/current observations; imports use the runner's kernel.

No VibeFlow import happens when this module is loaded. These cases exercise
public fact evaluators and actual graph compilation, not mocked diagnostics.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace


def run_cases(work_root: Path, variant: str, toolchain_root: Path | None = None) -> list[dict]:
    from vibeflow.core.compiler import compile_core
    from vibeflow.core.config.graph import parse_graph_config_data
    from vibeflow.core.contracts import PipelineInputSpec, DataProvider, DataRequirement
    from vibeflow.core.flow import (
        EdgeSpec, ExecutionLockSpec, GraphConfig, IoSpec, LoopSpec, NodeMetadata,
        NodeSpec, NodesetSpec,
    )
    from vibeflow.core.models import CoreCompileRequest, ImplementationFact, ImplementationFacts, TargetFeatureSet
    from vibeflow.core.quality import (
        FileQuality, FunctionQuality, ImportSite, ProjectQualityFacts, QualityPolicy,
        QualityStructureLimits, QualityStructureRoles,
        QualityThresholds,
    )
    from vibeflow.core.quality.implementation import (
        ImplementationLimits, ImplementationMetrics, analyze_call_graph,
    )
    from vibeflow.core.quality.nodesets import nodeset_quality_findings
    from vibeflow.core.quality.workflow_rules.duplicates import duplicate_logic_findings
    from vibeflow.core.quality.workflow_rules.flow import append_flowchart_health, append_join_policy_health
    from vibeflow.core.quality.workflow_rules.flow_data import append_data_contract_warnings
    from vibeflow.core.quality.workflow_rules.planned import planned_health_events

    if variant == "baseline":
        from vibeflow.core.quality import evaluate_project_quality
        from vibeflow.core.quality.implementation import (evaluate_node_implementation,
            evaluate_base_lib_implementation, evaluate_base_lib_dependency_chain)
    else:
        from sandbox.rule_parity.core.support import evaluate_standard_project_quality as evaluate_project_quality
        from vibeflow.builtin.implementation import (check_node_implementation as evaluate_node_implementation,
            check_base_lib_implementation as evaluate_base_lib_implementation, check_base_lib_dependency_chain as evaluate_base_lib_dependency_chain)

    work_root.mkdir(parents=True, exist_ok=True)
    observations = []

    def plain(value):
        if isinstance(value, dict) or hasattr(value, "items"):
            return {str(key): plain(item) for key, item in value.items()}
        if isinstance(value, (tuple, list, set, frozenset)):
            return [plain(item) for item in value]
        if hasattr(value, "__dataclass_fields__"):
            return {key: plain(getattr(value, key)) for key in value.__dataclass_fields__}
        return value

    def emit(case_id, title, family, operation, expected, *, classification="preserved", notes="", evidence=""):
        try:
            value = operation()
            if isinstance(value, dict):
                actual = value
            else:
                if hasattr(value, "errors") and hasattr(value, "warnings"):
                    findings = (*value.errors, *value.warnings)
                elif hasattr(value, "findings"):
                    findings = value.findings
                elif value is None:
                    findings = ()
                else:
                    findings = tuple(value)
                diagnostics=tuple(item for item in findings if hasattr(item,"rule_id") or hasattr(item,"code"))
                codes = sorted({(str(getattr(item, "rule_id", getattr(item, "code", ""))),
                                 str(getattr(item,"severity",getattr(item,"details",{}).get("severity","warning"))))
                                for item in diagnostics})
                status = getattr(value, "status", None) or ("FAIL" if any(severity == "error" for _, severity in codes)
                    else "CONCERNS" if codes else "PASS")
                metrics = {}
                if hasattr(value, "dependency_graph"):
                    metrics.update(dependency_graph=plain(value.dependency_graph),
                        longest_dependency_chain=plain(value.longest_dependency_chain),
                        structure_summary=plain(value.structure_summary))
                if hasattr(value, "compiled_graph"):
                    compiled = value.compiled_graph
                    metrics.update(order=list(compiled.order), effect_scopes=dict(compiled.effect_scopes),
                        schedule_edges=[list(edge.pair) for edge in compiled.resolved_schedule_edges],
                        transfer_edges=[list(edge.pair) for edge in compiled.resolved_transfer_edges])
                metrics["finding_details"] = [plain(getattr(item, "details", {})) for item in diagnostics]
                actual = {"status": status, "codes": [{"code": code, "severity": severity} for code, severity in codes],
                    "positions": [plain(item.source_location) for item in findings if getattr(item, "source_location", {})],
                    "metrics": metrics, "message": "; ".join(item.message for item in findings if hasattr(item, "message"))}
        except Exception as error:
            code = str(getattr(error, "rule_id", getattr(error, "code", type(error).__name__)))
            actual = {"status": "ERROR", "codes": [{"code": code, "severity": "error"}], "positions": [],
                "metrics": {"details": plain(getattr(error, "details", {})), "exception": type(error).__name__}, "message": str(error)}
        observations.append({"id": "core." + case_id, "title": title, "family": family,
            "expected": expected, "actual": actual, "classification": classification,
            "notes": notes, "evidence": evidence})

    def codes(*values):
        return {"codes": [{"code": code, "severity": severity} for code, severity in values], "exact_codes": True}

    def file(path="sample.py", **changes):
        return replace(FileQuality(path, path[:-3].replace("/", "."), 1, 1, 0, 0, 0, 0, 0, (), ()), **changes)

    def project(files, policy=None):
        return evaluate_project_quality(ProjectQualityFacts(str(work_root), tuple(files)), policy)

    project_evidence = "baseline/core/quality/evaluator.py:21-92 → core/rules/builtin/project_quality.py:88-173"
    emit("project.normal", "无超限源码事实", "project.files", lambda: project([file()]), codes(), evidence=project_evidence)
    file_checks = [
        ("lines", 449, None), ("lines", 450, ("QUALITY.FILE.WARN_LINES", "warning")),
        ("lines", 500, ("QUALITY.FILE.WARN_LINES", "warning")), ("lines", 501, ("QUALITY.FILE.MAX_LINES", "error")),
        ("bytes", 60000, None), ("bytes", 60001, ("QUALITY.FILE.MAX_BYTES", "error")),
        ("function_count", 40, None), ("function_count", 41, ("QUALITY.FILE.TOO_MANY_FUNCTIONS", "warning")),
        ("class_count", 20, None), ("class_count", 21, ("QUALITY.FILE.TOO_MANY_CLASSES", "warning")),
        ("public_api_count", 30, None), ("public_api_count", 31, ("QUALITY.FILE.TOO_WIDE_PUBLIC_API", "warning")),
        ("branch_count", 150, None), ("branch_count", 151, ("QUALITY.FILE.TOO_MANY_BRANCHES", "warning")),
    ]
    for field, amount, diagnostic in file_checks:
        emit(f"project.file.{field}.{amount}", f"文件 {field}={amount}", "project.files",
            lambda field=field, amount=amount: project([file(**{field: amount})]), codes(*(diagnostic,) if diagnostic else ()), evidence=project_evidence)
    function = FunctionQuality("calculate", 7, 8, 2, 0, 0, 0, "unique")
    for field, limit, diagnostic in [("lines",80,"MAX_LINES"),("branches",12,"TOO_MANY_BRANCHES"),
        ("max_nesting_depth",4,"TOO_DEEP_NESTING"),("param_count",6,"TOO_MANY_PARAMS")]:
        for amount in (limit, limit + 1):
            emit(f"project.function.{field}.{amount}", f"函数 {field}={amount}", "project.functions",
                lambda field=field, amount=amount: project([file(functions=(replace(function, **{field: amount}),))]),
                codes(*(("QUALITY.FUNCTION." + diagnostic, "warning"),) if amount > limit else ()), evidence=project_evidence)
    emit("project.file.configured", "覆盖文件行数阈值", "project.files",
        lambda: project([file(lines=3)], QualityPolicy(thresholds=QualityThresholds(max_file_lines=2, warn_file_lines=2))),
        codes(("QUALITY.FILE.MAX_LINES", "error")), evidence=project_evidence)

    implementation_evidence = "core/quality/implementation.py:93-184; core/rules/builtin/implementation.py:17-54"
    for field, amounts, warn, maximum, warn_code, error_code in [
        ("source_lines", (449,450,500,501),450,500,"SOURCE_NEAR_LIMIT","SOURCE_TOO_LARGE"),
        ("source_bytes", (53999,54000,60000,60001),54000,60000,"SOURCE_BYTES_NEAR_LIMIT","SOURCE_BYTES_TOO_LARGE")]:
        for amount in amounts:
            code = error_code if amount > maximum else warn_code if amount >= warn else None
            emit(f"implementation.node.{field}.{amount}", f"Node {field}={amount}", "implementation.node",
                lambda field=field, amount=amount: evaluate_node_implementation(ImplementationMetrics(**{field:amount}),ImplementationLimits()),
                codes(*(("NODE.PURITY." + code, "error" if amount > maximum else "warning"),) if code else ()), evidence=implementation_evidence)
    for field, metric in [("max_functions","function_count"),("max_branches","branch_count"),
        ("max_nesting_depth","max_nesting_depth"),("max_params","param_count"),("max_contract_keys","contract_key_count")]:
        for limit in (None,2,1):
            emit(f"implementation.optional.{field}.{limit}", f"可选复杂度 {field}={limit}", "implementation.node",
                lambda field=field, metric=metric, limit=limit: evaluate_node_implementation(ImplementationMetrics(**{metric:2}),replace(ImplementationLimits(),**{field:limit})),
                codes(*(("NODE.MAINTAINABILITY.COMPLEXITY_" + field.upper(), "error"),) if limit == 1 else ()), evidence=implementation_evidence)
    for length in (3,4,5):
        calls={f"f{index}": (f"f{index+1}",) if index+1 < length else () for index in range(length)}
        chain=analyze_call_graph(calls, entry="f0")
        emit(f"implementation.chain.{length}", f"Node helper链长度 {length}", "implementation.node",
            lambda chain=chain: evaluate_node_implementation(ImplementationMetrics(call_chain=chain), ImplementationLimits()),
            codes(*(("NODE.MAINTAINABILITY.CALL_CHAIN_TOO_DEEP", "error" if length > 4 else "warning"),) if length >= 4 else ()), evidence=implementation_evidence)
    for name, calls in [("self",{"run":("run",)}),("mutual",{"run":("helper",),"helper":("run",)})]:
        emit("implementation.recursion." + name, "Node helper递归 " + name, "implementation.node",
            lambda calls=calls: evaluate_node_implementation(ImplementationMetrics(call_chain=analyze_call_graph(calls, entry="run")),ImplementationLimits()),
            codes(("NODE.MAINTAINABILITY.RECURSIVE_CALL_CHAIN","error")), evidence=implementation_evidence)
    for field, limit, diagnostic in [("source_lines",500,"BASE_LIB.SOURCE.MAX_LINES"),("source_bytes",60000,"BASE_LIB.SOURCE.MAX_BYTES")]:
        for amount in (limit,limit+1):
            emit(f"implementation.library.{field}.{amount}", f"BaseLib {field}={amount}", "implementation.base_lib",
                lambda field=field, amount=amount: evaluate_base_lib_implementation(ImplementationMetrics(**{field:amount}),ImplementationLimits()),
                codes(*((diagnostic,"error"),) if amount > limit else (("BASE_LIB.SOURCE.NEAR_LIMIT","warning"),) if variant == "current" and amount == limit else ()), evidence=implementation_evidence,
                notes="Current explicit per-file limits retain the warning interval at the upper boundary." if variant == "current" and amount == limit else "")
    for field, metric in [("max_functions","function_count"),("max_branches","branch_count"),("max_nesting_depth","max_nesting_depth")]:
        emit("implementation.library." + field, "BaseLib可配置 " + field, "implementation.base_lib",
            lambda field=field, metric=metric: evaluate_base_lib_implementation(ImplementationMetrics(**{metric:2}),replace(ImplementationLimits(),**{field:1})),
            codes(("BASE_LIB.COMPLEXITY." + field.upper(),"error")), evidence=implementation_evidence)
    for length in (4,5,6,7):
        calls={f"f{index}": (f"f{index+1}",) if index+1 < length else () for index in range(length)}
        chain=analyze_call_graph(calls,entry="f0")
        emit(f"implementation.dependency_chain.{length}", f"BaseLib依赖链长度 {length}", "implementation.base_lib",
            lambda chain=chain: (lambda value: () if value is None else (value,))(evaluate_base_lib_dependency_chain(chain,ImplementationLimits())),
            codes(*(("NODE.MAINTAINABILITY.DEPENDENCY_CHAIN_TOO_DEEP","error" if length > 6 else "warning"),) if length > 4 else ()), evidence=implementation_evidence)

    dependency_evidence = "core/quality/dependencies.py:11-119; evaluator/project_quality defaults"
    for length in (5,6,10,11):
        files=[file(f"m{index}.py",imports=(f"m{index+1}",) if index+1 < length else ()) for index in range(length)]
        emit(f"project.dependencies.chain.{length}", f"项目依赖链 {length}", "project.dependencies",
            lambda files=files: project(files),
            codes(*(("QUALITY.DEPENDENCY.CHAIN_TOO_DEEP" if length > 10 else "QUALITY.DEPENDENCY.CHAIN_WARN","error" if length > 10 else "warning"),) if length >= 6 else ()), evidence=dependency_evidence)
    for name, edges, expected_codes in [
        ("cycle", {"a":("b",),"b":("c",),"c":("a",)},[("QUALITY.DEPENDENCY.CYCLE","error")]),
        ("bidirectional",{"a":("b",),"b":("a",)},[("QUALITY.DEPENDENCY.CYCLE","error"),("QUALITY.DEPENDENCY.BIDIRECTIONAL","error")])]:
        files=[file(name+".py",imports=targets,import_sites=tuple(ImportSite(name,target,"import "+target,name+".py",3,1) for target in targets)) for name,targets in edges.items()]
        emit("project.dependencies." + name, "项目依赖 " + name, "project.dependencies",lambda files=files: project(files),codes(*expected_codes),evidence=dependency_evidence)
    for length in (2,3):
        repeated=replace(function,lines=length,ast_fingerprint="same")
        emit(f"project.duplicate_function.{length}", f"重复函数长度 {length}", "project.duplicates",
            lambda repeated=repeated: project([file("a.py",functions=(repeated,)),file("b.py",functions=(replace(repeated,qualname="other"),))]),
            codes(*(("QUALITY.DUPLICATE.AST_FINGERPRINT","warning"),) if length >= 3 else ()),evidence="core/quality/duplicates.py:6-42")

    # Root structure is opt-in through QualityStructureLimits in both kernels.
    structure_evidence="core/quality/root_structure.py:17-39; core/quality/structure.py:174-227"
    quiet=QualityStructureLimits(warn_root_code_files=999,max_root_code_files=1000,warn_code_dirs=999,max_code_dirs=1000,
        warn_code_files_per_dir=999,max_code_files_per_dir=1000,warn_code_dir_depth=999,max_code_dir_depth=1000,
        warn_child_code_dirs_per_dir=999,max_child_code_dirs_per_dir=1000,warn_root_level_code_files=999,max_root_level_code_files=1000,
        enforce_role_imports=False)
    structure_limits=[
        ("root_files","warn_root_code_files","max_root_code_files","ROOT_TOO_MANY_CODE_FILES",lambda n:[file(f"pkg/x{i}.py") for i in range(n)]),
        ("root_dirs","warn_code_dirs","max_code_dirs","ROOT_TOO_MANY_CODE_DIRS",lambda n:[file(f"d{i}/x.py") for i in range(n)]),
        ("directory_files","warn_code_files_per_dir","max_code_files_per_dir","DIRECTORY_TOO_MANY_CODE_FILES",lambda n:[file(f"pkg/x{i}.py") for i in range(n)]),
        ("directory_depth","warn_code_dir_depth","max_code_dir_depth","DIRECTORY_TOO_DEEP",lambda n:[file("/".join(f"d{i}" for i in range(n))+"/x.py")]),
        ("child_dirs","warn_child_code_dirs_per_dir","max_child_code_dirs_per_dir","DIRECTORY_TOO_MANY_CHILD_CODE_DIRS",lambda n:[file(f"d{i}/x.py") for i in range(n)]),
        ("root_level","warn_root_level_code_files","max_root_level_code_files","ROOT_LEVEL_CODE_FILE",lambda n:[file(f"x{i}.py") for i in range(n)]),
    ]
    for name,warn_field,max_field,diagnostic,make in structure_limits:
        policy=QualityPolicy(structure_limits=replace(quiet,**{warn_field:2,max_field:3}))
        for amount in (1,2,3,4):
            files=make(amount)
            emit(f"project.structure.{name}.{amount}", f"结构 {name}={amount}（warning2/error>3）", "project.structure",
                lambda files=files,policy=policy:project(files,policy),
                codes(*(("QUALITY.STRUCTURE."+diagnostic,"error" if amount > 3 else "warning"),) if amount >= 2 else ()), evidence=structure_evidence)
    for source_role,target_role,diagnostic in [("base_lib","nodes","BASE_LIB_UPWARD_IMPORT"),
        ("nodes","plugins","NODE_UNDECLARED_PROJECT_IMPORT"),("plugins","nodes","PLUGIN_NODE_IMPORT"),("nodes","base_lib",None)]:
        if variant == "baseline":
            # Historical constructor belongs only to the isolated old kernel.
            roles=QualityStructureRoles(**{"module_roles":{"a":source_role,"b":target_role},"infer_roles_from_path":False})
        else:
            kinds={"nodes":"node", "base_lib":"base_lib", "plugins":"plugin"}
            owners=[{"path":path,"id":resource_id,"kind":kinds[role],"role":"entry",
                     "base_libs":["b"] if source_role == "nodes" and target_role == "base_lib" and resource_id == "a" else [],
                     "dependencies":[],"plugin_id":"test"}
                    for resource_id,path,role in (("a","a.py",source_role),("b","b.py",target_role))]
            roles=QualityStructureRoles(_resource_scopes=({"id":"selected","owners":owners},))
        policy=QualityPolicy(structure_limits=replace(quiet,enforce_role_imports=True),structure_roles=roles)
        emit(f"project.roles.{source_role}.{target_role}", f"声明资源导入 {source_role}→{target_role}", "project.structure",
            lambda policy=policy:project([file("a.py",imports=("b",),import_sites=(ImportSite("a","b","import b","a.py",1,1),)),file("b.py")],policy),
            codes(*(("QUALITY.STRUCTURE."+diagnostic,"error"),) if diagnostic else ()),evidence=structure_evidence)
    for name,threshold in [("fanout","max_directory_fanout"),("fanin","max_directory_fanin")]:
        files=([file("source/x.py",imports=("a.x","b.x")),file("a/x.py"),file("b/x.py")] if name == "fanout"
            else [file("source/x.py"),file("a/x.py",imports=("source.x",)),file("b/x.py",imports=("source.x",))])
        for limit in (2,1):
            emit(f"project.directory.{name}.{limit}", f"目录 {name}阈值 {limit}", "project.structure",
                lambda files=files,threshold=threshold,limit=limit:project(files,QualityPolicy(thresholds=replace(QualityThresholds(),**{threshold:limit}))),
                codes(*(("QUALITY.STRUCTURE.DIRECTORY_"+name.upper(),"warning"),) if limit == 1 else ()),evidence=structure_evidence)
    for count in (12,13):
        emit(f"project.prefix_cluster.{count}",f"共同前缀文件数 {count}","project.structure",
            lambda count=count:project([file(f"domain_case{i}.py") for i in range(count)]),
            codes(*(("QUALITY.STRUCTURE.PREFIX_CLUSTER_SHOULD_BE_PACKAGE","warning"),) if count > 12 else ()),evidence=structure_evidence)
    for count in (3,4):
        targets=tuple(f"domain_part{i}_helpers" for i in range(count))
        files=[file("caller.py",imports=targets),file("domain.py"),*(file(target+".py") for target in targets)]
        emit(f"project.public_entry_bypass.{count}",f"直接绕过public入口导入internal数 {count}","project.structure",
            lambda files=files:project(files),codes(("QUALITY.STRUCTURE.INTERNAL_MODULE_IMPORTED_EXTERNALLY","warning"),
                *(("QUALITY.STRUCTURE.PUBLIC_ENTRY_BYPASSED","warning"),) if count > 3 else ()),evidence=structure_evidence)
    for distance in (3,4):
        files=[file("caller/nested/x.py",imports=("library._helper" if distance==3 else "library.nested._helper",)),
            file("library/_helper.py" if distance==3 else "library/nested/_helper.py")]
        emit(f"project.internal_distance.{distance}",f"internal导入目录距离 {distance}","project.structure",lambda files=files:project(files),
            codes(*(("QUALITY.STRUCTURE.DISTANT_INTERNAL_IMPORT","warning"),) if distance>3 else ()),evidence="core/quality/structure_distance.py:26-54")
    for count in (6,7):
        targets=tuple(f"library{i}.nested.x" for i in range(count))
        files=[file("caller/nested/x.py",imports=targets),*(file(target.replace(".","/")+".py") for target in targets)]
        emit(f"project.scattered_dependencies.{count}",f"远距离依赖目录数 {count}","project.structure",lambda files=files:project(files),
            codes(*(("QUALITY.STRUCTURE.CLUSTER_SCATTERED_DEPENDENCY","warning"),) if count>6 else ()),evidence="core/quality/structure_distance.py:26-54")

    native_evidence="core/compiler.py:99-228; baseline identical checks except effect_scope facts fallback"
    features=TargetFeatureSet("probe",frozenset({"execution_locks","global_state"}))
    def node(name,kind="process",**kwargs):
        return NodeSpec(name,"probe."+name,flow_kind=kind,metadata=NodeMetadata(name,"Parity source-free node."),**kwargs)
    def compile_graph(graph, supplied=None, supported=features):
        if supplied is None:
            supplied=ImplementationFacts(tuple(ImplementationFact(spec.type_used, flow_kind=spec.flow_kind,
                requires=spec.requires, provides=spec.provides) for spec in graph.nodes
                if spec.type_used != "vibeflow.io" and not spec.type_used.startswith("vibeflow.loop.") and spec.type_used not in graph.nodesets))
        return compile_core(CoreCompileRequest(graph, supplied, supported))
    def io(name,operation):
        return NodeSpec(name,"vibeflow.io",io=IoSpec(operation),metadata=NodeMetadata(name,"Parity IO boundary."))
    def healthy(mid=()):
        nodes=(io("start","receive"),*mid,io("end","send"))
        return GraphConfig(nodes,tuple(EdgeSpec(a.id,b.id) for a,b in zip(nodes,nodes[1:])))
    emit("native.normal", "真实编译 receive→process→send", "native.graph", lambda:compile_graph(healthy((node("work"),))), {"should_accept":True},evidence=native_evidence)
    emit("native.strict_unknown", "严格实现事实表中缺 Node", "native.facts",
        lambda:compile_graph(GraphConfig((node("missing"),)),ImplementationFacts(strict=True)),codes(("NODE.TYPE.UNKNOWN","error")),evidence=native_evidence)
    emit("native.duplicate_provider", "两个节点声明同一输出 key", "native.contract",
        lambda:compile_graph(GraphConfig((node("a",provides=(DataProvider("value","value"),)),node("b",provides=(DataProvider("value","value"),))))),
        codes(("GRAPH.COMPILE","error")),evidence=native_evidence)
    emit("native.input_provider_conflict", "节点输出与Root输入 key冲突", "native.contract",
        lambda:compile_graph(GraphConfig((node("a",provides=(DataProvider("value","value"),)),),inputs=(PipelineInputSpec("value","value",required=True),))),
        codes(("GRAPH.COMPILE","error")),evidence=native_evidence)
    for role in ("schedule","transfer"):
        kwargs={"schedule":role == "schedule","transfer":role == "transfer"}
        graph=GraphConfig((node("a"),node("b")),(EdgeSpec("a","b",**kwargs),EdgeSpec("b","a",**kwargs)))
        emit("native.cycle."+role,"普通图"+role+"环","native.graph",lambda graph=graph:compile_graph(graph),
            codes(("GRAPH.CYCLE.FORBIDDEN" if role == "schedule" else "GRAPH.DATA.CYCLE.FORBIDDEN","error")),evidence=native_evidence)
    emit("native.no_edge_role","显式边既不调度也不传输","native.routing",
        lambda:compile_graph(GraphConfig((node("a"),node("b")),(EdgeSpec("a","b",schedule=False,transfer=False),))),codes(("GRAPH.EDGE.NO_ROLE","error")),evidence=native_evidence)
    emit("native.conflicting_edge_roles","重复边给出矛盾role","native.routing",
        lambda:compile_graph(GraphConfig((node("a"),node("b")),(EdgeSpec("a","b",schedule=True),EdgeSpec("a","b",schedule=False)))),codes(("GRAPH.EDGE.ROLE_CONFLICT","error")),evidence=native_evidence)
    emit("native.decision_missing_when","Decision边缺when","native.routing",
        lambda:compile_graph(GraphConfig((node("route","decision"),node("end","terminal")),(EdgeSpec("route","end"),))),codes(("GRAPH.DECISION.MISSING_EDGE_CONDITION","error")),evidence=native_evidence)
    emit("native.async_result_contract","result_key未在实际provides声明","native.async",
        lambda:compile_graph(GraphConfig((node("worker",async_mode="result_key",result_key="value"),))),codes(("GRAPH.ASYNC.RESULT_KEY_CONTRACT","error")),evidence=native_evidence)
    result_node=node("worker",provides=(DataProvider("value","value"),),async_mode="result_key",result_key="value")
    emit("native.async_result_route","result只有transfer边没有schedule消费者","native.async",
        lambda:compile_graph(GraphConfig((result_node,node("consumer")),(EdgeSpec("worker","consumer",schedule=False,transfer=True),))),codes(("GRAPH.ASYNC.RESULT_UNJOINABLE","error")),evidence=native_evidence)
    for kind in ("global_state","lock"):
        graph=(GraphConfig((node("state","global_state"),)) if kind == "global_state"
            else GraphConfig((node("work"),),execution_lock=ExecutionLockSpec("resource")))
        emit("native.feature."+kind,"Target缺少"+kind+"真实执行能力","native.features",lambda graph=graph:compile_graph(graph,supported=TargetFeatureSet()),codes(("TARGET.FEATURE.UNSUPPORTED","error")),evidence=native_evidence)
    emit("native.lock.detached","锁域内detached无法受保护","native.execution_lock",
        lambda:compile_graph(GraphConfig((node("background",async_mode="detached"),),execution_lock=ExecutionLockSpec("resource"))),codes(("GRAPH.EXECUTION_LOCK.DETACHED_FORBIDDEN","error")),evidence=native_evidence)
    emit("native.lock.result_unjoined","锁域内result无静态消费者","native.execution_lock",
        lambda:compile_graph(GraphConfig((result_node,),execution_lock=ExecutionLockSpec("resource"))),codes(("GRAPH.EXECUTION_LOCK.RESULT_UNJOINABLE","error")),evidence=native_evidence)
    emit("native.lock.conflicting_nested_keys","继承锁与不同子锁冲突","native.execution_lock",
        lambda:compile_graph(GraphConfig((node("work",execution_lock=ExecutionLockSpec("other")),),execution_lock=ExecutionLockSpec("resource"))),codes(("GRAPH.EXECUTION_LOCK.NESTED_KEY_CONFLICT","error")),evidence=native_evidence)
    emit("native.lock.same_key","同key继承锁合法","native.execution_lock",
        lambda:compile_graph(GraphConfig((node("work",execution_lock=ExecutionLockSpec("resource")),),execution_lock=ExecutionLockSpec("resource"))),{"should_accept":True},evidence=native_evidence)
    emit("native.global_uncoordinated","global_state无锁产生advisory","native.advisory",
        lambda:compile_graph(GraphConfig((node("state","global_state"),))),codes(("GRAPH.EXECUTION_LOCK.GLOBAL_STATE_UNCOORDINATED","warning")),evidence=native_evidence)
    advisory_graphs={
        "fanout":(GraphConfig((node("start","terminal"),node("a"),node("b"),node("end","terminal")),
            (EdgeSpec("start","a"),EdgeSpec("start","b"),EdgeSpec("a","end"),EdgeSpec("b","end"))),"GRAPH.MAINLINE.UNDECLARED_SYNC_FANOUT"),
        "ambiguous":(GraphConfig((node("start","terminal"),node("end","terminal"),node("a"),node("b")),
            (EdgeSpec("start","end"),EdgeSpec("a","b"))),"GRAPH.MAINLINE.AMBIGUOUS_SIDE_BRANCH"),
        "decision_dead_end":(GraphConfig((node("start","terminal"),node("route","decision"),node("dead"),node("end","terminal")),
            (EdgeSpec("start","route"),EdgeSpec("route","dead",when="branch == 'dead'"),EdgeSpec("route","end",when="branch == 'end'"))),"GRAPH.MAINLINE.DECISION_BRANCH_DEAD_END"),
        "bypass_without_trigger":(GraphConfig((node("start","terminal"),node("work"),node("extra"),node("end","terminal")),
            (EdgeSpec("start","work"),EdgeSpec("work","end"),EdgeSpec("start","extra",schedule=False,transfer=True))),"GRAPH.MAINLINE.DATA_BYPASS_WITHOUT_MAINLINE_TRIGGER"),
    }
    for name,(graph,diagnostic) in advisory_graphs.items():
        emit("native.mainline."+name,"真实mainline推断advisory "+name,"native.advisory",lambda graph=graph:compile_graph(graph),
            {"codes":[{"code":diagnostic,"severity":"warning"}]},evidence="core/mainline.py:170-277")
    emit("native.effect_fallback","flow身份不隐式授予Rule权限","native.facts",
        lambda:compile_graph(GraphConfig((node("work"),))),{"should_accept":True,"metrics":{"effect_scopes.work":"none" if variant == "baseline" else "unconstrained"}},
        classification="approved_change",notes="已批准由Rule输出决定权限；flow_kind仍保留原生语义。",evidence="core/compiler.py:800-824")
    child=NodesetSpec("probe.child","Child","A declared graph block.",(),(),GraphConfig((node("body"),)))
    emit("native.type_conflict","同type_key同时是实现与Nodeset","native.facts",
        lambda:compile_graph(GraphConfig((NodeSpec("call","probe.child"),),nodesets={child.type_key:child}),
            ImplementationFacts((ImplementationFact("probe.child"),),strict=True)),codes(("NODE.TYPE.CONFLICT","error")),evidence=native_evidence)
    def parsed_document(nodes=None,edges=None,**pipeline):
        calls=nodes if nodes is not None else [{"id":"work","type_used":"probe.work"}]
        calls=[{"display_name":"Parity call","description":"Exercises actual config parser.",**call} for call in calls]
        raw={"pipeline":{"nodes":calls,**pipeline}}
        if edges is not None:
            raw["pipeline"]["edges"]=edges
        parsed=parse_graph_config_data(raw)
        return compile_graph(parsed)
    for name,operation,reason in [
        ("empty_nodes",lambda:parsed_document(nodes=[]),"nodes must be a non-empty list"),
        ("duplicate_id",lambda:parsed_document(nodes=[{"id":"work","type_used":"probe.a"},{"id":"work","type_used":"probe.b"}]),"duplicate node id"),
        ("unknown_edge_endpoint",lambda:parsed_document(edges=[{"from":"work","to":"missing"}]),"edge references unknown node"),
        ("ordinary_contract_authority",lambda:parsed_document(nodes=[{"id":"work","type_used":"probe.work","requires":[]}]),"requires is derived from type_used"),
        ("max_steps_zero",lambda:parsed_document(max_steps=0),"max_steps"),
        ("unsupported_join",lambda:parsed_document(nodes=[{"id":"work","type_used":"probe.work","join_policy":"unknown"}]),"join_policy"),
        ("invalid_execution_lock",lambda:parsed_document(execution_lock={"key":""}),"execution_lock.key"),
        ("legacy_boundary",lambda:parsed_document(boundary={}),"boundary is removed"),
        ("legacy_loops",lambda:parsed_document(loops=[]),"pipeline.loops is removed"),
    ]:
        emit("native.config."+name,"原生配置拒绝 "+name,"native.config",operation,{**codes(("GraphConfigError","error")),"message_contains":reason},
            notes="Parser没有独立Finding；记录真实异常类别和完整message，不伪造诊断code。",evidence="core/config/graph.py:67-214,385-424")
    def loop_document(**overrides):
        loop={"body":"probe.child","max_iterations":2,**overrides}
        raw={"nodesets":[{"type_key":"probe.child","display_name":"Child","description":"Loop body.","requires":[],"provides":[],
            "pipeline":{"nodes":[{"id":"body","type_used":"probe.body","display_name":"Body","description":"A source-free body declaration."}]}}],
            "pipeline":{"nodes":[{"id":"loop","type_used":"vibeflow.loop.while","display_name":"Loop","description":"Exercises actual Loop parsing.","requires":[],"provides":[],"loop":loop}]}}
        return compile_graph(parse_graph_config_data(raw))
    for name,overrides,allowed in [("bounded",{},True),("unbounded",{"max_iterations":None},True),
        ("zero_iterations",{"max_iterations":0},False),("unknown_body",{"body":"missing"},False),
        ("unsupported_key",{"until":True},False),("stop_after_zero",{"stop_after":0},False),
        ("stop_when_not_boolean",{"stop_when":{"from":"done","equals":"yes"}},False),
        ("carry_missing_update",{"carry":[{"from":"a","as":"b"}]},False),
        ("unsupported_collect",{"collect":[{"from":"a","as":"b","mode":"last"}]},False)]:
        emit("native.loop."+name,"Loop原生声明 "+name,"native.loop",lambda overrides=overrides:loop_document(**overrides),
            {"should_accept":True} if allowed else {**codes(("GraphConfigError","error")),"message_contains":{
                "zero_iterations":"max_iterations","unknown_body":"unknown nodeset loop body","unsupported_key":"unsupported loop keys",
                "stop_after_zero":"stop_after","stop_when_not_boolean":"stop_when.equals","carry_missing_update":"carry[0].update",
                "unsupported_collect":"collect[0].mode"}[name]},evidence="core/config/loop.py:16-118; config/graph.py:559-568")

    workflow_evidence="core/quality/workflow_rules/{flow,flow_data,join_exclusivity}.py; core/rules/builtin/workflow.py"
    def workflow(graph, topic="flow"):
        compilation=compile_graph(graph)
        state=SimpleNamespace(errors=[],warnings=[])
        if topic == "join":
            append_join_policy_health(compilation.workflow.graph,compilation.compiled_graph,state)
        elif topic == "data":
            append_data_contract_warnings(compilation.workflow.graph,compilation.compiled_graph,state)
        else:
            # The current compatibility flow wrapper also includes data checks.
            # Compose the same two public checks for both kernels and dedupe only
            # code/severity in the observation; no returned diagnostic is hidden.
            append_flowchart_health(compilation.workflow.graph,compilation.compiled_graph,state)
            append_data_contract_warnings(compilation.workflow.graph,compilation.compiled_graph,state)
        return (*state.errors,*state.warnings)
    emit("workflow.normal","正式流程健康正常对照","workflow.flow",lambda:workflow(healthy((node("work"),))),codes(),evidence=workflow_evidence)
    emit("workflow.missing_boundaries","process孤立缺start/end","workflow.flow",lambda:workflow(GraphConfig((node("work"),))),codes(("GRAPH.FLOW.MISSING_START","error"),("GRAPH.FLOW.MISSING_END","error")),evidence=workflow_evidence)
    graph=replace(healthy(),nodes=(*healthy().nodes,node("orphan")))
    emit("workflow.orphan","多节点图中孤立节点","workflow.flow",lambda:workflow(graph),codes(("GRAPH.FLOW.UNREACHABLE_FROM_START","error"),("GRAPH.FLOW.CANNOT_REACH_END","error"),("GRAPH.FLOW.ORPHAN_NODE","error")),evidence=workflow_evidence)
    for duplicate in (False,True):
        graph=healthy((node("work"),))
        graph=replace(graph,edges=(*graph.edges,replace(graph.edges[0],when="route == 1" if duplicate else "")))
        emit("workflow.duplicate_edge."+str(duplicate),"重复边条件"+("冲突" if duplicate else "相同"),"workflow.flow",lambda graph=graph:workflow(graph),
            codes(("GRAPH.EDGE.CONFLICTING_DUPLICATE" if duplicate else "GRAPH.EDGE.DUPLICATE","warning")),evidence=workflow_evidence)
    graph=healthy((node("join",join_policy="all"),))
    emit("workflow.join.redundant","单前驱all join冗余","workflow.join",lambda:workflow(graph,"join"),codes(("GRAPH.JOIN.REDUNDANT_ALL","warning")),evidence=workflow_evidence)
    graph=GraphConfig((node("start","terminal"),node("route","decision"),node("left"),node("right"),node("join",join_policy="all"),node("end","terminal")),
        (EdgeSpec("start","route"),EdgeSpec("route","left",when="branch == 'left'"),EdgeSpec("route","right",when="branch == 'right'"),
         EdgeSpec("left","join"),EdgeSpec("right","join"),EdgeSpec("join","end")))
    emit("workflow.join.exclusive_all","all join等待互斥Decision分支","workflow.join",lambda:workflow(graph,"join"),codes(("GRAPH.JOIN.ALL_BRANCHES_MUTUALLY_EXCLUSIVE","error")),evidence=workflow_evidence)
    dead=GraphConfig((node("start","terminal"),node("route","decision"),node("dead"),node("end","terminal")),
        (EdgeSpec("start","route"),EdgeSpec("route","dead",when="branch == 'dead'"),EdgeSpec("route","end",when="branch == 'end'")))
    emit("workflow.decision.dead_end","Decision branch不能到终点","workflow.flow",lambda:workflow(dead),
        codes(("GRAPH.FLOW.CANNOT_REACH_END","error"),("GRAPH.DECISION.BRANCH_CANNOT_REACH_END","error")),evidence=workflow_evidence)
    graph=GraphConfig((node("a",provides=(DataProvider("a","value"),)),node("b",provides=(DataProvider("b","value"),)),
        node("join",requires=(DataRequirement("value","exactly_one"),))),
        (EdgeSpec("a","join",schedule=True,transfer=True),EdgeSpec("b","join",schedule=True,transfer=True)))
    emit("workflow.data.ambiguous_cardinality","exactly_one同时有两个无条件来源","workflow.data",lambda:workflow(graph,"data"),codes(("GRAPH.DATA.TYPE_CARDINALITY_AMBIGUOUS","error")),evidence=workflow_evidence)
    conditional=replace(graph,edges=(replace(graph.edges[0],when="branch == 'left'"),graph.edges[1]))
    emit("workflow.join.mixed_conditional","safe_any混合conditional与unconditional","workflow.join",lambda:workflow(conditional,"join"),codes(("GRAPH.JOIN.AMBIGUOUS_UNCONDITIONAL","error")),evidence=workflow_evidence)
    graph=healthy((node("producer",provides=(DataProvider("unused","unused"),)),))
    emit("workflow.data.unconsumed","没有直接消费者或Root导出的输出","workflow.data",lambda:workflow(graph,"data"),codes(("GRAPH.DATA.UNCONSUMED_PROVIDER","warning")),evidence=workflow_evidence)
    graph=replace(graph,nodes=(*graph.nodes[:-1],node("join",join_policy="all"),graph.nodes[-1]),
        edges=(EdgeSpec("start","producer"),EdgeSpec("producer","join"),EdgeSpec("start","join",schedule=False,transfer=True),EdgeSpec("join","end")))
    emit("workflow.join.transfer_only","all join依赖不会激活调度的transfer边","workflow.join",lambda:workflow(graph,"join"),codes(("GRAPH.JOIN.ALL_DEPENDS_ON_TRANSFER_ONLY","error")),evidence=workflow_evidence)
    emit("workflow.data.bypass_empty","data bypass边两端没有可交付payload","workflow.data",lambda:workflow(graph,"data"),
        {"codes":[{"code":"GRAPH.DATA.NO_PAYLOAD_BYPASS","severity":"error"}]},evidence=workflow_evidence)
    for requirement in ("exactly_one","optional_one"):
        graph=healthy((node("consumer",requires=(DataRequirement("missing",requirement),)),))
        emit("workflow.data.unreachable."+requirement,"无提供者需求 "+requirement,"workflow.data",lambda graph=graph:workflow(graph,"data"),
            codes(("GRAPH.DATA.MISSING_DIRECT_PROVIDER","error"),*(("GRAPH.DATA.RUNTIME_REQUIREMENT_UNREACHABLE","error"),) if requirement == "exactly_one" else ()),
            notes="baseline直接provider检查对optional_one也报error；保留真实基线语义，不猜测允许。",evidence=workflow_evidence)
    for shape,similar in [("body",False),("wrapper",False),("body",True)]:
        similarities={"a":{"node":"b","relationship":"copy","reason":"Deliberately same."}} if similar else {}
        emit(f"workflow.duplicate_logic.{shape}.{similar}","Workflow重复逻辑/合法声明对照","workflow.duplicates",
            lambda shape=shape,similarities=similarities:duplicate_logic_findings({"a":"same","b":"same"},{"a":{"run_pure_shape":shape},"b":{"run_pure_shape":shape}},node_types={"a":"probe.a","b":"probe.b"},node_similarities=similarities),
            codes(*(("GRAPH.SMELL.DUPLICATE_LOGIC","warning"),) if shape != "wrapper" and not similar else ()),evidence="core/quality/workflow_rules/duplicates.py:8-71")

    nodeset_evidence="core/nodeset_dependencies.py; core/quality/nodesets.py:15-71"
    def nested_graph(depth,width=1,used=True):
        definitions={}
        for index in range(depth):
            body_nodes=(NodeSpec("nested",f"probe.layer{index-1}"),) if index else tuple(node(f"leaf{i}",status="planned") for i in range(width))
            child=GraphConfig(body_nodes)
            definitions[f"probe.layer{index}"]=NodesetSpec(f"probe.layer{index}","Layer","Depth parity block.",(),(),child,status="planned")
        return GraphConfig((NodeSpec("top",f"probe.layer{depth-1}"),) if used else (),nodesets=definitions)
    for depth in (4,5):
        emit(f"workflow.nodeset.depth.{depth}",f"Nodeset声明链深度 {depth}","workflow.nodesets",lambda depth=depth:nodeset_quality_findings(nested_graph(depth)),
            codes(*(("NODESET.NESTING.DEPTH_EXCEEDED","error"),) if depth > 4 else ()),evidence=nodeset_evidence)
    emit("workflow.nodeset.unused_depth","未调用声明链仍有深度事实","workflow.nodesets",lambda:nodeset_quality_findings(nested_graph(5,used=False)),codes(("NODESET.NESTING.DEPTH_EXCEEDED","error")),evidence=nodeset_evidence)
    emit("workflow.nodeset.configured_depth","深度上限显式提高为5","workflow.nodesets",lambda:nodeset_quality_findings(nested_graph(5),max_depth=5),codes(),evidence=nodeset_evidence)
    for width in (10,11):
        emit(f"workflow.nodeset.width.{width}",f"Nodeset内部节点数 {width}","workflow.nodesets",lambda width=width:nodeset_quality_findings(nested_graph(1,width)),
            codes(*(("NODESET.SMELL.TOO_WIDE","warning"),) if width > 10 else ()),evidence=nodeset_evidence)
    for mode in ("nodeset","loop"):
        child_call=NodeSpec("again","probe.recursive") if mode == "nodeset" else NodeSpec("again","vibeflow.loop.while",loop=LoopSpec(body="probe.recursive"))
        definition=NodesetSpec("probe.recursive","Recursive","Forbidden finite recursive definition.",(),(),GraphConfig((child_call,)))
        graph=GraphConfig((NodeSpec("call","probe.recursive"),),nodesets={definition.type_key:definition})
        emit("workflow.nodeset.recursion."+mode,"Nodeset递归引用 "+mode,"workflow.nodesets",lambda graph=graph:nodeset_quality_findings(graph),codes(("NODESET.RECURSION","error")),evidence=nodeset_evidence)
    graph=GraphConfig((node("future",status="planned"),))
    emit("workflow.planned.node","planned声明警告/非业务执行","workflow.planned",lambda:planned_health_events(graph),codes(("GRAPH.PLANNED.NODE","warning")),evidence="core/quality/workflow_rules/planned.py:30-63")
    definition=NodesetSpec("probe.planned","Planned","Unimplemented block.",(),(),GraphConfig(()),status="planned")
    emit("workflow.planned.nodeset","planned Nodeset声明警告","workflow.planned",lambda:planned_health_events(GraphConfig((),nodesets={definition.type_key:definition})),codes(("GRAPH.PLANNED.NODESET","warning")),evidence="core/quality/workflow_rules/planned.py:30-63")
    from vibeflow.core.planned import PlannedBehavior
    for kind,severity in [("blocking","error"),("transparent","warning")]:
        child=GraphConfig((node("future",status="planned",planned_behavior=PlannedBehavior(kind)),))
        definition=NodesetSpec("probe.parent","Parent","Implemented block with future child.",(),(),child)
        emit("workflow.planned.parent."+kind,"已实现Nodeset含planned "+kind,"workflow.planned",
            lambda definition=definition:planned_health_events(GraphConfig((),nodesets={definition.type_key:definition})),
            codes(("GRAPH.PLANNED.NODE","warning"),("GRAPH.PLANNED.PARENT_HAS_PLANNED_CHILD",severity)),evidence="core/quality/workflow_rules/planned.py:30-63")
    def finite_recursive_plan():
        from vibeflow.block_compiler import compile_graph_plan
        definition=NodesetSpec("probe.recursive","Recursive","Cannot produce finite portable blocks.",(),(),GraphConfig((NodeSpec("again","probe.recursive"),)))
        graph=GraphConfig((NodeSpec("call","probe.recursive"),),nodesets={definition.type_key:definition})
        compilation=compile_graph(graph)
        return compile_graph_plan(compilation.workflow.graph,compilation.compiled_graph,compile_nested=True)
    emit("native.portable_recursion","真正有限block编译拒绝递归Nodeset","native.blocks",finite_recursive_plan,
        {**codes(("PortablePlanError","error")),"message_contains":"recursive nodeset reference"},evidence="block_compiler/compiler.py:272-274")

    # This is intentionally Target orchestration: retain the original declaration
    # graph while opting out of a child's review. It catches, rather than xfails,
    # the current loss of Nodeset identity reported during the independent audit.
    def unconstrained_child():
        from vibeflow.targets.python.project.registry import NodeRegistry
        if variant == "current":
            from vibeflow.tooling.application.python.project.declarations import default_python_registry as NodeRegistry
        from vibeflow.targets.python.quality.workflow.validation import validate_graph_health
        child=GraphConfig(()) if variant == "baseline" else GraphConfig((),rulesets=())
        definition=NodesetSpec("probe.child","Child","A valid empty source-free child.",(),(),child)
        graph=healthy((NodeSpec("stage","probe.child",metadata=NodeMetadata("Stage","Calls child.")),))
        graph=replace(graph,nodesets={definition.type_key:definition}, **({"rulesets": ("vibeflow.workflow",)} if variant == "current" else {}))
        return validate_graph_health(graph,registry=NodeRegistry())
    emit("workflow.unconstrained_child_identity","父图默认审查仍识别显式[]子Nodeset","workflow.orchestration",unconstrained_child,{"should_accept":True},
        classification="approved_change",notes="baseline无子图Ruleset选择；current明确[]仅免审查，原生Nodeset身份应保留。不得xfail。",
        evidence="targets/python/quality/rules/workflow.py:18,34-35; baseline workflow/validation.py:80-107")

    if variant != "baseline":
        from vibeflow.core.rules import compile_ruleset
        from vibeflow.builtin import builtin_rule_resources
        rules,sets=builtin_rule_resources()
        for selected,phase,count in [("vibeflow.workflow","import",0),("vibeflow.workflow","static",1),("vibeflow.workflow","run",1),
            ("vibeflow.quality.project","import",0),("vibeflow.quality.project","static",4),("vibeflow.quality.project","run",0),
            ("vibeflow.process","import",1),("vibeflow.process","static",3),("vibeflow.process","run",3)]:
            def inspect_plan(selected=selected,phase=phase):
                plan=compile_ruleset(selected,rules={r.id:r for r in rules},rulesets={s.id:s for s in sets},entrypoint=phase)
                return {"status":"PASS","codes":[],"positions":[],"metrics":{"invocation_count":len(plan.invocations),"rules":[item.rule.id for item in plan.invocations]},"message":"No business Node was imported or executed."}
            emit("selection."+selected+"."+phase,"默认Ruleset入口 "+selected+"/"+phase,"rule.selection",inspect_plan,{"should_accept":True,"metrics":{"invocation_count":count}},classification="new_feature",evidence="core/rules/builtin/effects.py:27-36; project_quality.py:160-173")
        emit("selection.project.explicit_empty","显式空选集只返回事实且诚实标记","rule.selection",lambda:evaluate_project_quality(ProjectQualityFacts(str(work_root),(file(lines=501),)),rulesets=()),
            {"should_accept":True,"codes":[],"exact_codes":True},classification="new_feature",evidence="core/quality/evaluator.py:21-64; rule_report.py:48-85")
    # Keep formal dispatch evidence separate from portable algorithm probes.
    import importlib.util
    for filename in ("formal_cases.py", "variants.py", "formal_variants.py"):
        formal_spec = importlib.util.spec_from_file_location("core_" + filename[:-3], Path(__file__).with_name(filename))
        formal_module = importlib.util.module_from_spec(formal_spec)
        formal_spec.loader.exec_module(formal_module)
        observations.extend(formal_module.run_cases(work_root, variant, toolchain_root))
    return observations
