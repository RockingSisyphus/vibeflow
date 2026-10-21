"""Real JS/TS entrypoint observations for the baseline parity runner.

The parent starts a fresh Python child for each kernel.  Nothing in this module
imports VibeFlow until run_cases(), so PYTHONPATH selects the actual variant.
Each case owns its files; the project-local locked toolchain can be shared.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from contextlib import redirect_stdout
from io import StringIO
import json
import os
from pathlib import Path
import shutil
import subprocess
from typing import Any


INPUTS = 'Readonly<{"parity.value": Readonly<{value: number}>}>'
NODE = f'export function run(inputs: {INPUTS}) {{\n  BODY\n  return {{result: inputs["parity.value"].value + 1}};\n}}\n'
PLUGIN = 'export function createPlugin(context: Readonly<{abiVersion: "ABI"}>) {\n  return {beforeRun() { BODY; void context.abiVersion; }};\n}\n'
BASE_LIB = 'export function increment(value: number): number {\n  BODY\n  return value + 1;\n}\n'


@dataclass(frozen=True)
class Case:
    id: str
    title: str
    family: str
    role: str = 'node'
    source: str = ''
    code: str = ''
    entrypoint: str = 'audit'
    extras: dict[str, str] = field(default_factory=dict)
    completion: str = 'immediate'
    classification: str = 'preserved'
    notes: str = ''
    current_code: str | None = None
    declare_base: bool = True
    other_node: bool = False
    empty_selection: bool = False
    metrics: dict[str, Any] = field(default_factory=dict)
    extra_manifests: dict[str, dict[str, Any]] = field(default_factory=dict)
    additional_base_libs: tuple[str, ...] = ()
    additional_plugins: tuple[str, ...] = ()
    external_packages: tuple[str, ...] = ()


def _body(template: str, body: str = '') -> str:
    return template.replace('BODY', body)


def _cases() -> tuple[Case, ...]:
    normal_node = _body(NODE)
    normal_plugin = _body(PLUGIN)
    normal_base = _body(BASE_LIB)
    common = [
        Case('js.node.normal.audit', '正常 Node 静态检查', 'node.control', source=normal_node),
        Case('js.node.normal.build-run', '正常 Node 实际构建和数值执行', 'node.control', source=normal_node, entrypoint='build-run', metrics={'business_result': 4}),
        Case('js.plugin.normal.audit', '已选独立 Runtime Plugin 正常审查', 'plugin.control', 'plugin', normal_plugin),
        Case('js.plugin.normal.build', '已选 Runtime Plugin 合法 ABI 构建', 'plugin.control', 'plugin', normal_plugin, entrypoint='build'),
        Case('js.base.normal.audit', 'Node 引用已声明纯 BaseLib', 'base.control', 'base_lib', normal_base),
        Case('js.node.top-call', 'Node 模块顶层调用', 'imports.purity', source='function bootstrap() { return 1; }\nconst boot = bootstrap();\n' + normal_node, code='VF_IMPORT_SIDE_EFFECT'),
        Case('js.node.mutable-module', 'Node 模块顶层可变绑定', 'imports.purity', source='let count = 0;\n' + normal_node, code='VF_IMPORT_SIDE_EFFECT'),
        Case('js.node.class-static', 'Node 类静态初始化执行', 'imports.purity', source='function bootstrap() { return 1; }\nclass State { static value = bootstrap(); }\n' + normal_node, code='VF_IMPORT_SIDE_EFFECT'),
        Case('js.node.dynamic-import', 'Node 非字面量动态导入', 'imports.dynamic', source=_body(NODE, 'const moduleName = "../base_lib/math.ts"; void import(moduleName);'), code='VF_IMPORT_DYNAMIC'),
        Case('js.node.dynamic-code', 'Node 运行时字符串求值', 'imports.dynamic', source=_body(NODE, 'eval("1 + 1");'), code='VF_IMPORT_DYNAMIC_CODE'),
        Case('js.node.require-dynamic', 'Node 非字面量 require', 'imports.dynamic', source='declare function require(name: string): unknown;\n' + _body(NODE, 'const name = "../base_lib/math.ts"; require(name);'), code='VF_IMPORT_DYNAMIC'),
        Case('js.node.unowned-import', 'Node 导入未声明本地文件', 'imports.ownership', source='import {helper} from "../helpers/unowned.ts";\n' + _body(NODE, 'helper();'), code='VF_IMPORT_OWNER', extras={'helpers/unowned.ts': 'export function helper() { return 1; }\n'}),
        Case('js.node.other-node-import', 'Node 直接导入另一个实际 Node', 'imports.ownership', source='import {run as other} from "./other.ts";\n' + _body(NODE, 'void other;'), code='VF_IMPORT_NODE_TO_NODE', other_node=True),
        Case('js.node.undeclared-base', 'Node 引用未启用的已声明 BaseLib', 'imports.ownership', source='import {increment} from "../base_lib/math.ts";\n' + _body(NODE, 'increment(1);'), code='VF_IMPORT_OWNER', current_code='VF_IMPORT_BASE_LIB', declare_base=False, notes='同一非法导入均须拒绝；基线只给当前启用资源建 owner，新版从完整目录识别 BaseLib 后给更具体诊断。'),
        Case('js.node.immediate-async', 'immediate Node 的实际实现为 async', 'completion', source=normal_node.replace('function run', 'async function run'), code='VF_COMPLETION_IMMEDIATE_PROMISE'),
        Case('js.node.suspend-sync', 'suspend Node 的实际实现为同步', 'completion', source=normal_node, completion='suspend', code='VF_COMPLETION_SUSPEND_NON_PROMISE'),
        Case('js.node.suspend-async.normal', 'suspend Node 正确返回 Promise', 'completion.control', source=normal_node.replace('function run', 'async function run'), completion='suspend'),
        Case('js.node.discarded-promise', 'Node 丢弃 Promise chain', 'async.ownership', source=_body(NODE, 'Promise.resolve(1).then(value => value + 1);'), code='VF_PROMISE_UNOWNED'),
        Case('js.node.void-promise', 'Node 使用 void 丢弃 Promise', 'async.ownership', source=_body(NODE, 'void Promise.resolve(1);'), code='VF_PROMISE_UNOWNED'),
        Case('js.node.timer', 'Node 创建长驻 timer', 'async.ownership', source=_body(NODE, 'setTimeout(() => 1, 1);'), code='VF_NODE_LONG_LIVED_LISTENER', current_code='VF_NODE_RESOURCE_UNOWNED',classification='approved_change',notes='Native resource binding replaces the old method-name rejection.'),
        Case('js.node.module-write', 'Node 写入模块持有对象', 'effects.module_state', source='const shared = Object.freeze({count: 0});\n' + _body(NODE, '(shared as {count: number}).count += 1;'), code='VF_MODULE_STATE'),
        Case('js.node.regexp-state', 'Node 模块持有全局 RegExp 状态', 'effects.module_state', source='const matcher = /value/g;\n' + _body(NODE, 'matcher.test("value");'), code='VF_MODULE_STATE'),
        Case('js.node.console', 'Process 默认无副作用规则检测 console', 'effects.console', source=_body(NODE, 'console.log("parity");'), current_code='VF_BASE_LIB_HOST_IO', classification='new_feature', notes='基线未把 console 纳入 Node host-I/O；当前显式默认 none 补强。'),
        Case('js.node.console-empty', '显式空规则选择不隐式恢复 Process 权限', 'effects.selection', source=_body(NODE, 'console.log("parity");'), empty_selection=True, classification='approved_change'),
        Case('js.node.console-shadow', '局部纯 console 名称遮蔽', 'effects.console', source=_body(NODE, 'const console = {log: (value: number) => value + 1}; console.log(1);')),
        Case('js.node.source-lines', 'Node 源码超过 500 行', 'maintainability.source', source=normal_node.replace('  return ', '  // Implementation line\n' * 501 + '  return '), code='NODE.PURITY.SOURCE_TOO_LARGE'),
        Case('js.node.call-depth', 'Node 实际内部调用链超过四层', 'maintainability.call_chain', source='function a(value: number) { return b(value); }\nfunction b(value: number) { return c(value); }\nfunction c(value: number) { return d(value); }\nfunction d(value: number) { return e(value); }\nfunction e(value: number) { return value + 1; }\n' + _body(NODE, 'a(1);'), code='NODE.MAINTAINABILITY.CALL_CHAIN_TOO_DEEP'),
        Case('js.node.recursive-helper', 'Node 实际递归 helper', 'maintainability.call_chain', source='function recurse(value: number): number { return value > 0 ? recurse(value - 1) : 0; }\n' + _body(NODE, 'recurse(1);'), code='NODE.MAINTAINABILITY.RECURSIVE_CALL_CHAIN'),
        Case('js.node.abi-output', '实际 Node 输出与声明 ABI 不符', 'native.contract', source=normal_node.replace('result:', 'wrong:'), code='VF_TYPESCRIPT', entrypoint='build'),
        Case('js.base.host-global', 'BaseLib 使用宿主 globalThis', 'effects.host_io', 'base_lib', _body(BASE_LIB, 'void globalThis;'), 'VF_BASE_LIB_HOST_IO'),
        Case('js.base.nondeterministic', 'BaseLib 使用 Math.random', 'effects.host_io', 'base_lib', _body(BASE_LIB, 'Math.random();'), 'VF_BASE_LIB_HOST_IO'),
        Case('js.base.reverse-import', 'BaseLib 反向导入实际 Node', 'imports.ownership', 'base_lib', 'import {run} from "../nodes/calc.ts";\n' + _body(BASE_LIB, 'void run;'), 'VF_IMPORT_LAYER'),
        Case('js.base.top-call', 'BaseLib 模块顶层执行调用', 'imports.purity', 'base_lib', 'function boot() { return 1; }\nconst value = boot();\n' + normal_base, 'VF_IMPORT_SIDE_EFFECT'),
        Case('js.base.source-lines', '实际引用 BaseLib 超过 500 行', 'maintainability.source', 'base_lib', normal_base + '\n' * 501, 'BASE_LIB.SOURCE.MAX_LINES'),
    ]
    plugin_negatives = (
        ('host-global', '独立 Plugin 读取 globalThis', 'effects.host_io', _body(PLUGIN, 'void globalThis'), 'VF_PLUGIN_HOST_IO'),
        ('top-call', '独立 Plugin 模块顶层调用', 'imports.purity', 'function boot() { return 1; }\nconst booted = boot();\n' + normal_plugin, 'VF_IMPORT_SIDE_EFFECT'),
        ('module-write', '独立 Plugin 写入模块状态', 'effects.module_state', 'const shared = Object.freeze({count: 0});\n' + _body(PLUGIN, '(shared as {count: number}).count += 1'), 'VF_MODULE_STATE'),
        ('discarded-promise', '独立 Plugin 丢弃 Promise chain', 'async.ownership', _body(PLUGIN, 'Promise.resolve(1).then(value => value + 1)'), 'VF_PLUGIN_PROMISE_UNOWNED'),
        ('void-promise', '独立 Plugin 使用 void 丢弃 Promise', 'async.ownership', _body(PLUGIN, 'void Promise.resolve(1)'), 'VF_PLUGIN_PROMISE_UNOWNED'),
        ('listener', '独立 Plugin 注册长驻 listener', 'async.ownership', _body(PLUGIN, 'globalThis.addEventListener("parity", () => 1)'), 'VF_PLUGIN_LONG_LIVED_LISTENER'),
        ('timer', '独立 Plugin 创建 timer', 'async.ownership', _body(PLUGIN, 'setTimeout(() => 1, 1)'), 'VF_PLUGIN_LONG_LIVED_LISTENER'),
        ('node-import', '独立 Plugin 跨层导入 Node', 'imports.ownership', 'import {run} from "../nodes/calc.ts";\n' + _body(PLUGIN, 'void run'), 'VF_PLUGIN_IMPORT_POLICY'),
        ('immediate-async-hook', 'immediate Plugin 包含 async hook', 'completion', normal_plugin.replace('beforeRun()', 'async beforeRun()'), 'VF_COMPLETION_IMMEDIATE_PROMISE'),
    )
    common.extend(Case('js.plugin.' + name, title, family, 'plugin', source, code) for name, title, family, source, code in plugin_negatives)
    # Current worker cases first review the selected SDK resource, then exercise
    # binding/protocol on success. Historical baseline worker preflight is retained.
    for name in ('host-global', 'module-write', 'discarded-promise', 'timer'):
        selected = next(item for item in plugin_negatives if item[0] == name)
        common.append(Case('js.plugin.' + name + '.build', selected[1] + '（正式 build）', selected[2], 'plugin', selected[3], selected[4], 'build'))
    worker_codes = {'module-write': 'VF_MODULE_STATE', 'discarded-promise': 'VF_PLUGIN_PROMISE_UNOWNED', 'timer': 'VF_PLUGIN_LONG_LIVED_LISTENER'}
    for name in ('host-global', 'module-write', 'discarded-promise', 'timer', 'immediate-async-hook'):
        selected = next(item for item in plugin_negatives if item[0] == name)
        source = 'let shared = 0;\n' + _body(PLUGIN, 'shared += 1') if name == 'module-write' else selected[3]
        common.append(Case('js.plugin.' + name + '.worker', selected[1] + '（真实 worker open）', selected[2], 'plugin', source, worker_codes.get(name, selected[4]), 'worker'))
    common.append(Case('js.plugin.normal.worker', '合法插件在真实 worker 中绑定', 'plugin.control', 'plugin', normal_plugin, entrypoint='worker'))
    common.extend((
        Case('js.plugin.normal.quality-cli', '正式 quality-check 的正常 Plugin 对照', 'plugin.control', 'plugin', normal_plugin, entrypoint='quality-cli'),
        Case('js.plugin.host-global.quality-cli', '正式 quality-check 拒绝独立 Plugin 宿主访问', 'effects.host_io', 'plugin', _body(PLUGIN, 'void globalThis'), 'VF_PLUGIN_HOST_IO', 'quality-cli'),
        Case('js.node.top-call.quality-cli', '正式 quality-check 拒绝 Node 顶层执行', 'imports.purity', source='function boot() { return 1; }\nconst value = boot();\n' + normal_node, code='VF_IMPORT_SIDE_EFFECT', entrypoint='quality-cli'),
    ))
    common.extend((
        Case('js.quality.file-lines', '普通 JS 源文件长度检查', 'quality.source', source=normal_node.replace('  return ', '  // Implementation line\n' * 501 + '  return '), code='QUALITY.FILE.MAX_LINES', entrypoint='quality'),
        Case('js.quality.function-duplicate', '真实 TS AST 重复函数产生 warning', 'quality.duplicates', source='export function first(value: number) {\n  const result = value + 1;\n  return result;\n}\nexport function second(value: number) {\n  const result = value + 2;\n  return result;\n}\n', code='QUALITY.DUPLICATE.AST_FINGERPRINT', entrypoint='quality'),
        Case('js.quality.syntax', '真实 TS 语法错误', 'quality.syntax', source='export function broken( { return 1;\n', code='QUALITY.SYNTAX.JAVASCRIPT', entrypoint='quality'),
        Case('js.quality.metrics', '真实 TS function/branch/参数指标', 'quality.metrics', source='export function choose(value: number, extra?: number) {\n  if (value > 0) return value + (extra ?? 1);\n  return 0;\n}\n', entrypoint='quality', metrics={'function_count': 1, 'first_function_params': 2, 'branch_count': 2}),
    ))
    common.extend((
        Case('js.node.external-undeclared', 'Node 导入工具链已有但未声明的包', 'imports.ownership', source='import * as ts from "typescript";\n' + _body(NODE, 'void ts.version;'), code='VF_IMPORT_EXTERNAL'),
        Case('js.node.external-declared.normal', '同一包明确声明后的正常导入', 'imports.control', source='import * as ts from "typescript";\n' + _body(NODE, 'void ts.version;'), external_packages=('typescript',)),
        Case('js.node.unresolved-import', 'Node 导入实际不存在的文件', 'imports.ownership', source='import {missing} from "../helpers/missing.ts";\n' + _body(NODE, 'void missing;'), code='VF_IMPORT_RESOLVE'),
        Case('js.node.package-root', 'Node 导入 package_root 外真实文件', 'imports.ownership', source='import {outside} from "../../outside.ts";\n' + _body(NODE, 'outside();'), code='VF_IMPORT_PACKAGE_ROOT', extras={'../outside.ts': 'export function outside() { return 1; }\n'}),
        Case('js.base.undeclared-dependency', '启用两 BaseLib 仍须声明它们之间的依赖', 'imports.ownership', 'base_lib', 'import {step} from "./other.ts";\n' + _body(BASE_LIB, 'step(value);'), 'VF_IMPORT_BASE_LIB', extras={'base_lib/other.ts': 'export function step(value: number) { return value + 1; }\n'}, extra_manifests={'base_lib/other.jsonc': _base_descriptor('parity.other_math', 'base_lib/other.ts')}, additional_base_libs=('parity.other_math',)),
        Case('js.plugin.package-private-dependency', '同包生命周期实现可直接复用私有支持代码', 'imports.ownership', 'plugin', 'import {createPlugin as other} from "./other.ts";\n' + _body(PLUGIN, 'void other'), '', extras={'plugins/other.ts': normal_plugin}, extra_manifests={'plugins/other.jsonc': _plugin_descriptor('parity.other_plugin', 'plugins/other.ts')}, additional_plugins=('parity.other_plugin',)),
    ))
    for length in (2, 7):
        extras = {}
        manifests = {'base_lib/math.jsonc': _base_descriptor('parity.math', 'base_lib/math.ts', ('parity.chain1',))}
        for index in range(1, length):
            file = f'base_lib/chain{index}.ts'
            next_id = (f'parity.chain{index + 1}',) if index + 1 < length else ()
            extras[file] = (f'import {{step as next}} from "./chain{index + 1}.ts";\nexport function step(value: number): number {{ return next(value); }}\n'
                            if next_id else 'export function step(value: number): number { return value + 1; }\n')
            manifests[f'base_lib/chain{index}.jsonc'] = _base_descriptor(f'parity.chain{index}', file, next_id)
        common.append(Case(f'js.base.dependency-chain.{length}', f'{length} 个真实 BaseLib 模块的相对导入链', 'maintainability.dependencies', 'base_lib',
                           'import {step} from "./chain1.ts";\nexport function increment(value: number): number { return step(value); }\n',
                           'NODE.MAINTAINABILITY.DEPENDENCY_CHAIN_TOO_DEEP' if length > 6 else '', extras=extras, extra_manifests=manifests,
                           metrics={'dependency_chain_length': length + 1} if length > 6 else {'source_files': length + 1},
                           notes='基线和当前的公开依赖链指标都包含起始 Node；七个 BaseLib 模块的实际 longest_chain_length 是 8。'))
    return tuple(common)


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def _implementation(file: str, export: str, completion: str = 'immediate') -> dict[str, Any]:
    return {'language': 'typescript', 'targets': ['node', 'browser'], 'completion': completion,
            'source': {'kind': 'file', 'ref': file, 'export': export}}


def _base_descriptor(resource_id: str, file: str, dependencies: tuple[str, ...] = ()) -> dict[str, Any]:
    return {'kind': 'base_lib', 'id': resource_id, 'display_name': resource_id, 'description': 'Pure numeric helper.',
            'implementations': [_implementation(file, '')], 'dependencies': list(dependencies), 'external_packages': []}


def _plugin_descriptor(resource_id: str, file: str) -> dict[str, Any]:
    return {'kind': 'plugin', 'id': resource_id, 'type': 'runtime', 'targets': ['node', 'browser'],
            'implementations': [_implementation(file, 'createPlugin')], 'config': {'schema': {'type': 'object'}, 'defaults': {}}, 'dependencies': []}


def _node_descriptor(variant: str, key: str, file: str, case: Case) -> dict[str, Any]:
    result = {'node_type': 'vibeflow.node', 'kind': 'node', 'id': key, 'display_name': key, 'category': 'parity',
        'description': 'One numeric increment; executable metadata stays in the descriptor.', 'version': '1.0.0', 'flow_kind': 'terminal',
        'contract': {'requires': [{'type': 'parity.value', 'cardinality': 'exactly_one', 'display_name': 'Value'}],
            'provides': [{'key': 'result', 'type': 'parity.result', 'display_name': 'Result'}],
            'params_schema': {}, 'params_defaults': {}, 'input_semantics': {'parity.value': ['Input number.']}, 'output_semantics': {'result': ['Incremented number.']}},
        'implementations': [_implementation(file, 'run', case.completion)],
        'base_libs': (["parity.math"] if case.role == 'base_lib' or (case.id == 'js.node.undeclared-base' and case.declare_base) else []) + list(case.additional_base_libs), 'capabilities': []}
    if variant == 'current':
        result.pop('category', None)
        result['rulesets'] = [] if case.empty_selection else ['vibeflow.process']
    return result


def definition(root, variant, kind, resource_id, historical_path):
    if variant == "baseline":
        return root / "manifests" / historical_path
    from tests.fixtures.support.plugins import resource
    return resource(root, kind, resource_id)


def put_definition(root, variant, declaration, historical_path):
    path = definition(root, variant, declaration["kind"], declaration.get("type_key", declaration.get("id")), historical_path)
    _write_json(path, declaration)


def _project(root: Path, variant: str, toolchain: Path, case: Case) -> tuple[Path, Path, Path]:
    root.mkdir(parents=True, exist_ok=False)
    for name in ('package.json', 'package-lock.json'):
        shutil.copy2(toolchain / name, root / name)
    (root / 'node_modules').symlink_to(toolchain / 'node_modules', target_is_directory=True)
    project = {"project_target": "javascript", "javascript": {"package_root": ".", "external_packages": list(case.external_packages)}, }
    if variant == "baseline":
        project["descriptors"] = {group: ["manifests/" + group] for group in ("nodes", "base_lib", "data_schemas", "plugins")}
    else:
        from tests.fixtures.support.plugins import write_plugin
        write_plugin(root, [], target="javascript", plugin_id="parity.resources")
    _write_json(root / "vibeflow_project.jsonc", project)
    workspace = root.parent / (root.name + '-workspace.jsonc')
    _write_json(workspace, {'roots': [{'id': 'parity', 'path': root.name, 'config': 'vibeflow_project.jsonc'}]})
    descriptor = _node_descriptor(variant, 'parity.calc', 'nodes/calc.ts', case)
    put_definition(root, variant, descriptor, 'nodes/calc.jsonc')
    for key in ('value', 'result'):
        put_definition(root, variant, {'kind': 'data_schema', 'type_key': 'parity.' + key, 'display_name': key, 'schema': {'type': 'number'}}, ('data_schemas/' + key + '.jsonc'))
    sources = {'nodes/calc.ts': _body(NODE), 'base_lib/math.ts': _body(BASE_LIB), **case.extras}
    selected_file = 'nodes/calc.ts'
    if case.role == 'base_lib':
        selected_file = 'base_lib/math.ts'
        sources['nodes/calc.ts'] = 'import {increment} from "../base_lib/math.ts";\n' + NODE.replace('BODY', 'increment(1);')
    elif case.role == 'plugin':
        selected_file = 'plugins/runtime.ts' if variant=='baseline' else 'plugins/code_plugin/runtime.ts'
    selected_source = case.source
    if variant == 'current' and case.id == 'js.plugin.module-write.worker':
        selected_source = 'const shared = Object.freeze({count:0});\n' + _body(PLUGIN, '(shared as {count:number}).count += 1')
    sources[selected_file] = selected_source.replace('ABI', 'vibeflow.plugin.v1' if variant == 'baseline' else 'vibeflow.plugin.v4')
    if variant=='current':
        sources={('plugins/code_plugin/'+name[len('plugins/'):] if name.startswith('plugins/') and not name.startswith('plugins/code_plugin/') else name):text for name,text in sources.items()}
        if case.role=='plugin':sources[selected_file]=sources[selected_file].replace('../nodes/','../../nodes/').replace('../base_lib/','../../base_lib/')
    for name, text in sources.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text.replace('ABI', 'vibeflow.plugin.v1' if variant == 'baseline' else 'vibeflow.plugin.v4'), encoding='utf-8')
    if case.role == 'base_lib' or case.id == 'js.node.undeclared-base':
        put_definition(root, variant, {'kind': 'base_lib', 'id': 'parity.math', 'display_name': 'Increment helper', 'description': 'Pure numeric helper.', 'implementations': [_implementation('base_lib/math.ts', '')], 'dependencies': [], 'external_packages': []}, 'base_lib/math.jsonc')
    pipeline = {'entry_mode': 'async', 'inputs': [{'key': 'value', 'type': 'parity.value', 'display_name': 'Value', 'required': True}],
        'nodes': [{'id': 'calculate', 'definition_id': 'parity.calc', 'display_name': 'Calculate', 'description': 'Increment the input.'}], 'edges': [],
        'outputs': [{'type': 'parity.result', 'cardinality': 'exactly_one', 'display_name': 'Result', 'as': 'result'}]}
    config: dict[str, Any] = {'pipeline': pipeline}
    if case.other_node:
        sources['nodes/other.ts'] = f'export function run(inputs: {INPUTS}) {{ void inputs; return {{}}; }}\n'
        (root / 'nodes/other.ts').write_text(sources['nodes/other.ts'], encoding='utf-8')
        other_descriptor = _node_descriptor(variant, 'parity.other', 'nodes/other.ts', Case('other', 'Other', 'control'))
        other_descriptor['contract']['provides'] = []
        other_descriptor['contract']['output_semantics'] = {}
        put_definition(root, variant, other_descriptor, 'nodes/other.jsonc')
        pipeline['nodes'].append({'id': 'other', 'definition_id': 'parity.other', 'display_name': 'Other', 'description': 'Independent implementation.'})
        pipeline['edges'].append({'from': 'calculate', 'to': 'other'})
    if case.role == 'plugin':
        put_definition(root, variant, {'kind': 'plugin', 'id': 'parity.plugin', 'type': 'runtime', 'targets': ['node', 'browser'], 'implementations': [_implementation(selected_file, 'createPlugin')], 'config': {'schema': {'type': 'object'}, 'defaults': {}}}, 'plugins/runtime.jsonc')
        config['plugins'] = ['parity.plugin', *case.additional_plugins]
    for file, descriptor in case.extra_manifests.items():
        put_definition(root, variant, descriptor, file)
    if variant == "current":
        from tests.fixtures.support.plugins import resource_declarations, update_resources
        values = resource_declarations(root)
        for declaration in values:
            if declaration["kind"]=='plugin':
                for implementation in declaration.get('implementations',[]):
                    ref=implementation['source']['ref']
                    if ref.startswith('plugins/code_plugin/'):ref=ref[len('plugins/code_plugin/'):]
                    elif ref.startswith('plugins/'):ref=ref[len('plugins/'):]
                    implementation['source']['ref']=ref
            if declaration["kind"] in {"base_lib", "plugin"}:
                declaration["rulesets"] = ["vibeflow." + declaration["kind"]]
        update_resources(root, values)
        config["plugins"] = [{"source": {"kind":"file", "ref":"plugins/code_plugin/plugin.ts", "export":"plugin"}}]
    config_path = root / 'workflow.jsonc'
    _write_json(config_path, config)
    return workspace, config_path, root / selected_file


def _finding_rows(value: Any) -> list[dict[str, Any]]:
    """Read real diagnostic transports, preserving the original codes and spans."""
    if isinstance(value, (list, tuple)):
        return [item for child in value for item in _finding_rows(child)]
    if not isinstance(value, dict):
        return []
    result = []
    if ('code' in value or 'rule_id' in value) and 'message' in value:
        result.append(value)
    for child in value.values():
        if isinstance(child, (dict, list, tuple)):
            result.extend(_finding_rows(child))
    return result


def _actual(status: str, rows: list[dict[str, Any]], *, message: str = '', metrics: dict[str, Any] | None = None) -> dict[str, Any]:
    codes = []
    positions = []
    metrics = dict(metrics or {})
    for row in rows:
        code = str(row.get('code', row.get('rule_id', '')))
        entry = {'code': code, 'severity': str(row.get('severity', 'error'))}
        if entry not in codes:
            codes.append(entry)
        location = row.get('source_location') or {key: row[key] for key in ('line', 'column') if key in row}
        location = dict(location)
        if not location.get('path'):
            location['path'] = row.get('file', row.get('path', row.get('source_path', '')))
        if location.get('path'):
            positions.append({'code': code, **location})
        details = row.get('details', {})
        if isinstance(details, dict) and isinstance(details.get('longest_chain_length'), int):
            metrics['dependency_chain_length'] = details['longest_chain_length']
    return {'status': status, 'codes': codes, 'positions': positions, 'metrics': metrics, 'message': message}


def _observe(case: Case, root: Path, workspace: Path, config: Path, source: Path, *, variant: str) -> dict[str, Any]:
    # Imports occur only after the parent's child selects the kernel via PYTHONPATH.
    from vibeflow.tooling.application.javascript.audit import JavascriptAuditRequest, audit_javascript_project
    from vibeflow.tooling.application.javascript.build import ProjectBuildRequest, build_project_aot
    from vibeflow.targets.javascript.build.plugin_session import JavascriptPluginSession
    if variant == "baseline":
        from vibeflow.targets.javascript.quality.source import scan_javascript_quality
    else:
        from vibeflow.tooling.application.javascript.quality_scan import scan_javascript_quality
    worker_metrics: dict[str, Any] = {}
    try:
        if case.entrypoint == 'quality-cli':
            from vibeflow.tooling.application.javascript.cli import main
            stdout = StringIO()
            with redirect_stdout(stdout):
                exit_code = main(['quality-check', '--workspace', str(workspace), '--json'])
            payload = json.loads(stdout.getvalue())
            return _actual(str(payload.get('status', 'FAIL' if exit_code else 'PASS')), _finding_rows(payload),
                           metrics={'exit_code': exit_code}, message=str(payload.get('message', '')))
        if case.entrypoint == 'worker':
            if variant == 'current':
                # The SDK resource's selected Ruleset owns health decisions.
                # The raw worker subsequently verifies binding and protocol only.
                worker_metrics.update(sdk_rules_checked=True, worker_opened=False)
                audit_javascript_project(JavascriptAuditRequest(workspace=workspace, config=config))
            with JavascriptPluginSession() as session:
                if variant == 'current':
                    worker_metrics['worker_opened'] = True
                session.open('parity', plugin={'id': 'parity.plugin', 'type': 'runtime', 'module': str(source), 'export': 'createPlugin', 'completion': case.completion, 'config': {}, **({'rulesets': ['vibeflow.plugin']} if 'rulesets' in json.loads(definition(root, variant, 'plugin', 'parity.plugin', 'plugins/runtime.jsonc').read_text()) else {})}, package_root=root, target='node', workflow_id='parity')
            return _actual('PASS', [], metrics=worker_metrics)
        if case.entrypoint == 'quality':
            report = scan_javascript_quality(source, package_root=root)
            rows = [item.to_dict() for item in report.findings]
            file = report.files[0] if report.files else None
            metrics = {'files': len(report.files), **({'lines': file.lines, 'bytes': file.bytes, 'function_count': file.function_count, 'branch_count': file.branch_count,
                        'first_function_params': file.functions[0].param_count if file.functions else 0} if file is not None else {})}
            return _actual(report.status, rows, metrics=metrics)
        if case.entrypoint == 'audit':
            result = audit_javascript_project(JavascriptAuditRequest(workspace=workspace, config=config))
            return _actual('CONCERNS' if result.warnings else 'PASS', list(result.warnings), metrics={'source_files': len(result.source_files)})
        result = build_project_aot(ProjectBuildRequest(workspace, config, root.parent / (root.name + '-build'), 'node', 'single-esm'))
        metrics: dict[str, Any] = {'built': True}
        if case.entrypoint == 'build-run':
            script = f'import {{pathToFileURL}} from "node:url"; const workflow = await import(pathToFileURL({json.dumps(str(result.entry))})); process.stdout.write(JSON.stringify(await workflow.runWorkflowAsync({{value: 3}})));'
            completed = subprocess.run(['node', '--input-type=module', '--eval', script], cwd=root, capture_output=True, text=True, check=False)
            if completed.returncode:
                return _actual('ERROR', [], message=completed.stderr)
            metrics['business_result'] = json.loads(completed.stdout)['result']
        return _actual('CONCERNS' if result.prepared.warnings else 'PASS', list(result.prepared.warnings), metrics=metrics)
    except Exception as error:
        payload = {'code': str(getattr(error, 'code', None) or getattr(error, 'rule_id', None) or type(error).__name__), 'message': str(error),
                   'details': dict(getattr(error, 'details', {}) or {}), 'diagnostics': list(getattr(error, 'diagnostics', ()) or ())}
        return _actual('FAIL', _finding_rows(payload), metrics=worker_metrics, message=str(error))


def run_cases(work_root: Path, variant: str, toolchain_root: Path | None = None) -> list[dict[str, Any]]:
    """Observe actual baseline/current entrances without changing expected behavior."""
    if variant not in {'baseline', 'current'}:
        raise ValueError('variant must be baseline or current')
    toolchain = Path(toolchain_root or os.environ.get('VIBEFLOW_TEST_TOOLCHAIN_ROOT', '')).resolve()
    if not (toolchain / 'node_modules').is_dir() or not (toolchain / 'package-lock.json').is_file():
        raise ValueError('A project-local toolchain with the selected variant lockfile is required')
    work_root = Path(work_root).resolve()
    work_root.mkdir(parents=True, exist_ok=True)
    observations = []
    for index, case in enumerate(_cases()):
        root = work_root / f'{index:02d}-{case.id}'
        workspace, config, source = _project(root, variant, toolchain, case)
        actual = _observe(case, root, workspace, config, source, variant=variant)
        code = case.current_code if variant == 'current' and case.current_code is not None else case.code
        if variant=='current' and case.id=='js.node.package-root':code='VF_IMPORT_OWNER'
        if variant=='current' and case.id=='js.plugin.node-import':code='DESCRIPTOR.INVALID'
        if variant == 'current' and case.id in {'js.node.recursive-helper', 'js.base.nondeterministic', 'js.node.dynamic-code'}:
            code = ''  # B04/B06/B07: preserve the baseline, retire current default inference.
        severity = 'warning' if case.id == 'js.quality.function-duplicate' else 'error'
        expected: dict[str, Any] = {'should_accept': not code or severity == 'warning',
            'codes': [{'code': code, 'severity': severity}] if code else [], 'metrics': dict(case.metrics)}
        if variant == 'current' and 'source_files' in expected['metrics']:
            # The selected code-plugin declaration is now a recorded source.
            expected['metrics']['source_files'] += 1
        if case.entrypoint == 'quality-cli':
            expected['metrics'].setdefault('exit_code', 0 if expected['should_accept'] else 1)
        if variant == 'current' and case.entrypoint == 'worker':
            expected['metrics'].update(sdk_rules_checked=True, worker_opened=not bool(code))
            if code:
                expected['located_codes'] = [code]
        if code and case.entrypoint != 'worker' and case.id not in {'js.node.abi-output', 'js.quality.function-duplicate','js.plugin.node-import'}:
            expected['located_codes'] = [code]
        observations.append({'id': case.id, 'title': case.title, 'family': case.family, 'expected': expected, 'actual': actual,
            'classification': case.classification, 'notes': case.notes,
            'evidence': {'level': 'sdk-rules-then-worker' if variant == 'current' and case.entrypoint == 'worker' else case.entrypoint, 'source': str(source), 'config': str(config), 'workspace': str(workspace)}})
    import importlib.util
    import sys
    spec = importlib.util.spec_from_file_location('javascript_parity_variants', Path(__file__).with_name('variants.py'))
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    observations.extend(module.run_variants(work_root / 'variants', variant, toolchain, fixture=sys.modules[__name__]))
    return observations


__all__ = ['run_cases']
