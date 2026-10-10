#!/usr/bin/env python3
"""Developer audit of retired architecture files, symbols and installed contents."""
from __future__ import annotations
import argparse
import ast
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]
RETIRED_FILES = (
    'targets/python/quality/source_analysis/runtime_dispatch.py',
    'targets/python/quality/source_analysis/parameter_facts.py',
    'targets/python/quality/source_analysis/exit_stacks.py',
    'core/descriptors/rule_catalogs.py', 'core/descriptors/rule_models.py',
    'core/quality/workflow_rules/rule_catalog.py',
    'targets/javascript/build/nodeset_limits.py',
    'targets/javascript/frontend/frontend_condition.py',
    'targets/javascript/frontend/frontend_loop.py',
    'targets/javascript/frontend/frontend_parser.py',
    'targets/javascript/frontend/frontend_validation.py',
    'targets/javascript/frontend/model.py', 'targets/javascript/frontend/model_types.py',
    'targets/javascript/quality/models.py', 'targets/javascript/quality/validation.py',
    'targets/python/project/base_lib.py', 'targets/python/project/base_lib_types.py',
    'targets/python/project/context.py', 'targets/python/project/descriptors.py',
    'targets/python/project/registry_base.py', 'targets/python/project/resources.py',
    'targets/python/quality/base_lib.py', 'targets/python/quality/imports.py',
    'targets/python/quality/rules.py', 'targets/python/quality/workflow/base_lib.py',
    'targets/python/quality/source_analysis/preflight.py',
    'targets/python/quality/workflow/planned.py', 'targets/python/quality/workflow/registry.py',
    'targets/javascript/build/rule_extensions.py',
    'targets/python/runtime/config.py', 'tooling/application/python/cli/reports.py',
    'tooling/application/python/project/plugin_resources.py',
    'tooling/application/python/project/resources.py',
    'tooling/application/python/project/source_preflight.py',
)
MOVED_FILES = ('core/rules/builtin/__init__.py', 'core/rules/builtin/effects.py',
    'core/rules/builtin/implementation.py', 'core/rules/builtin/project_quality.py',
    'core/rules/builtin/workflow.py')
RETIRED_PACKAGE_DIRS = ('core/rules/builtin',)
RETIRED_SYMBOLS = frozenset({'RuntimeDispatchSite', 'RuntimeDispatchAnalysis',
    'analyze_runtime_dispatch', 'analyze_source_runtime_dispatch',
    '_RuntimeDispatchAnalyzer', '_SourceDispatchAnalyzer','NodeInfo', 'NodeContract', 'RegistryBase', 'BaseLibInfo',
    'BaseLibRegistry', 'PluginInfo', 'PluginResourceRegistry', 'ConfigResources',
    'WorkflowSpec', 'adapt_base_lib_registry', 'base_lib_descriptor_from_registry',
    'normalize_plugin_info', 'normalize_base_lib_info', 'scan_base_lib', 'analyze_base_lib',
    'parse_javascript_plugin_descriptor', '_validate_source_size', '_parse_source',
    '_execute_graph_block', '_assert_block_eligible', '_configured_nodeset_depth',
    '_render_custom_node_style', '_custom_node_style', '_cloud_path',
    '_validate_review_documents', '_duplicate_fingerprints', '_string_items',
    '_validate_key_tuple', '_validate_semantics', '_validate_schema_mapping',
    '_is_inputs_subscript', '_dedupe_violations', '_validate_complexity_metrics',
    '_validate_call_chain_metrics', '_core_metrics', '_numeric_violations',
    '_validate_contract_examples_shape', 'implemented_base_lib_modules',
    'node_base_lib_imports', 'summarize_base_lib_dependency_chain',
    'append_planned_findings', 'validate_nodeset_depth', 'nodeset_depth_error_report',
    'is_base_lib',
    'legacy_workflow_spec_payload', 'boundary_registry',
    'evaluate_default_project_quality', 'NODE_INFO', 'PLUGIN_INFO', 'BASE_LIB_INFO',
    '_role_for_file', '_is_declared_base_lib', '_role_for_path', '_is_node_role',
    '_role_import_finding', '_role_import_findings', '_NODE_ROLES', '_BASE_LIB_ROLE',
    '_PLUGIN_ROLE', 'base_lib_paths', 'base_lib_modules', 'module_roles',
    'infer_roles_from_path', 'SIDE_EFFECT_IMPORT_ROOTS', 'SIDE_EFFECT_CALLS',
    'SIDE_EFFECT_ATTR_CALLS'})
RETIRED_DIAGNOSTIC_CODES = frozenset({'node_info_flow_kind', 'node_flow_kind_invalid',
    'missing_node_info', 'missing_contract', 'node_external_invalid',
    'node_decision_missing_route_output', 'type_mismatch', 'signature_unavailable',
    'example_shape'})
RETIRED_HELPERS = ('tests/fixtures/support/code_plugins.py',
    'tests/fixtures/support/source_membership.py', 'tests/fixtures/support/contributions.py')
RETIRED_MODULES = frozenset('vibeflow.' + value.removesuffix('.py').replace('/', '.').removesuffix('.__init__')
    for value in (*RETIRED_FILES, *MOVED_FILES)
    if not (ROOT / 'src/vibeflow' / value.removesuffix('.py') / '__init__.py').is_file())
RETIRED_HELPER_MODULES = frozenset(value.removesuffix('.py').replace('/', '.') for value in RETIRED_HELPERS)


def _retired_source_references(source, path):
    failures = []
    for node in ast.walk(ast.parse(source)):
        name = node.id if isinstance(node, ast.Name) else node.arg if isinstance(node, ast.arg) else node.name if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) else None
        if name in RETIRED_SYMBOLS:
            failures.append({'path': path, 'line': node.lineno,
                             'reason': 'retired symbol: ' + name})
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value in RETIRED_DIAGNOSTIC_CODES:
            failures.append({'path': path, 'line': node.lineno,
                             'reason': 'retired diagnostic code: ' + node.value})
    return failures


def audit(wheel=None):
    failures = []
    for relative in (*RETIRED_FILES, *MOVED_FILES):
        if (ROOT / 'src/vibeflow' / relative).exists():
            failures.append({'path': 'src/vibeflow/' + relative, 'reason': 'retired file remains'})
    for relative in RETIRED_PACKAGE_DIRS:
        if (ROOT / 'src/vibeflow' / relative).exists():
            failures.append({'path': 'src/vibeflow/' + relative, 'reason': 'retired package namespace remains'})
    for relative in RETIRED_HELPERS:
        if (ROOT / relative).exists():
            failures.append({'path': relative, 'reason': 'test conversion bridge remains'})
    for path in (ROOT / 'src/vibeflow').rglob('*.py'):
        failures.extend(_retired_source_references(path.read_text(), str(path.relative_to(ROOT))))
    for directory in ('src', 'tests', 'sandbox', 'distribution', 'tools'):
        for path in (ROOT / directory).rglob('*.py'):
            if '__pycache__' in path.parts:
                continue
            try:
                tree = ast.parse(path.read_text())
            except SyntaxError:
                # Negative regression fixtures deliberately contain invalid source.
                continue
            for node in ast.walk(tree):
                modules = [node.module or ''] if isinstance(node, ast.ImportFrom) else [value.name for value in node.names] if isinstance(node, ast.Import) else []
                for module in modules:
                    if module in RETIRED_HELPER_MODULES:
                        failures.append({'path': str(path.relative_to(ROOT)), 'line': node.lineno,
                                         'reason': 'test conversion bridge import'})
                    if any(module == retired or module.startswith(retired + '.') for retired in RETIRED_MODULES):
                        failures.append({'path': str(path.relative_to(ROOT)), 'line': node.lineno,
                                         'reason': 'retired product module import: ' + module})
                if isinstance(node, ast.Constant) and isinstance(node.value, str) and not path.is_relative_to(ROOT / 'tests/fixtures/rule_parity'):
                    # Frozen parity generators contain historical imports. Current
                    # generated programs must use the same API as normal callers.
                    for module in RETIRED_MODULES:
                        if 'from ' + module + ' import ' in node.value or 'import ' + module + '\n' in node.value:
                            failures.append({'path': str(path.relative_to(ROOT)), 'line': node.lineno,
                                             'reason': 'retired import in generated current program: ' + module})
    if wheel:
        with zipfile.ZipFile(wheel) as archive:
            names = set(archive.namelist())
            for relative in (*RETIRED_FILES, *MOVED_FILES):
                if 'vibeflow/' + relative in names:
                    failures.append({'path': relative, 'reason': 'retired wheel content'})
            for relative in RETIRED_PACKAGE_DIRS:
                if any(name.startswith('vibeflow/' + relative + '/') for name in names):
                    failures.append({'path': relative, 'reason': 'retired wheel package namespace'})
            for name in sorted(names):
                if name.startswith('vibeflow/') and name.endswith('.py'):
                    failures.extend(_retired_source_references(archive.read(name).decode(), name))
    return {'status': 'FAIL' if failures else 'PASS',
            'retired_files': list(RETIRED_FILES), 'relocated_builtin_files': list(MOVED_FILES),
            'retired_test_helpers': list(RETIRED_HELPERS),
            'retired_package_namespaces': list(RETIRED_PACKAGE_DIRS),
            'retired_symbols': sorted(RETIRED_SYMBOLS),
            'retired_diagnostic_codes': sorted(RETIRED_DIAGNOSTIC_CODES), 'failures': failures}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--wheel', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = audit(args.wheel)
    output = json.dumps(result, ensure_ascii=False, indent=2) + '\n'
    if args.output:
        args.output.write_text(output)
    print(output, end='')
    return int(result['status'] != 'PASS')


if __name__ == '__main__':
    raise SystemExit(main())
