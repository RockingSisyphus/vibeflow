"""Finite TS predicate variants, exercised through real public entrances.

The fixture module is supplied by its caller rather than importing a kernel or
assuming that the repository is on the isolated child's PYTHONPATH.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
import json
from pathlib import Path
import subprocess
from typing import Any


@dataclass(frozen=True)
class Variation:
    case: Any
    severity: str = 'error'
    policy: dict[str, Any] = field(default_factory=dict)
    node_patch: dict[str, Any] = field(default_factory=dict)
    call_patch: dict[str, Any] = field(default_factory=dict)
    pipeline_patch: dict[str, Any] = field(default_factory=dict)
    config_patch: dict[str, Any] = field(default_factory=dict)
    profile: str = 'single-esm'
    target: str = 'node'
    message_contains: str = ''
    located: bool = True


def variants(f: Any) -> tuple[Variation, ...]:
    C, body = f.Case, f._body
    node, plugin, host, base = body(f.NODE), body(f.PLUGIN), body(f.HOST), body(f.BASE_LIB)
    rows: list[Variation] = []

    def add(name, title, family, source, code='', *, role='node', **options):
        case_options = options.pop('case_options', {})
        rows.append(Variation(C('js.variant.' + name, title, family, role, source, code, **case_options), **options))

    # Actual checker signatures, distinct from the async keyword and ABI shape.
    promise_node = f'export function run(inputs: {f.INPUTS}): Promise<{{result: number}}> {{ return Promise.resolve({{result: inputs["parity.value"].value + 1}}); }}\n'
    add('completion.promise-signature', '同步函数实际返回 Promise 的 immediate 实现', 'completion.signature', promise_node, 'VF_COMPLETION_IMMEDIATE_PROMISE')
    add('completion.promise-suspend', '同步函数返回 Promise 满足 suspend 签名', 'completion.signature', promise_node, case_options={'completion': 'suspend'})
    add('completion.await-owned', 'suspend Node await 自己拥有的 Promise', 'async.ownership', body(f.NODE, 'await Promise.resolve(1);').replace('function run', 'async function run'), case_options={'completion': 'suspend'})
    helper = 'function later(): Promise<number> { return Promise.resolve(1); }\n'
    add('completion.helper-immediate', 'immediate 调用 checker 证明返回 Promise 的 helper', 'completion.signature', helper + body(f.NODE, 'const pending = later(); void pending;'), 'VF_COMPLETION_IMMEDIATE_PROMISE')
    add('completion.helper-discarded', 'suspend Node 丢弃 helper 返回的 Promise', 'async.ownership', helper + body(f.NODE, 'later();').replace('function run', 'async function run'), 'VF_PROMISE_UNOWNED', case_options={'completion': 'suspend'})
    add('completion.helper-await', 'suspend Node await helper 返回的 Promise', 'async.ownership', helper + body(f.NODE, 'await later();').replace('function run', 'async function run'), case_options={'completion': 'suspend'})
    add('completion.new-promise', 'immediate Node 构造 Promise', 'completion.syntax', body(f.NODE, 'const pending = new Promise(resolve => resolve(1)); void pending;'), 'VF_COMPLETION_IMMEDIATE_PROMISE')
    add('completion.nested-uncalled', '未调用的局部 async 函数不属于当前完成协议', 'completion.boundary', body(f.NODE, 'async function deferred() { return 1; } void deferred;'), case_options={'classification': 'baseline_limitation', 'notes': 'Node visitor 在嵌套函数边界停止；此处不宣称它审核了未调用异步函数的内部工作。'})
    add('completion.nested-escape', '将局部 async 函数保存到局部对象仍是旧分析边界', 'completion.boundary', body(f.NODE, 'const escaped = {callback: async () => 1}; void escaped;'), case_options={'classification': 'baseline_limitation'})
    add('completion.shadow-promise', '同名局部 Promise 触发旧语法启发式', 'completion.boundary', body(f.NODE, 'const Promise = {resolve: (value: number) => value}; Promise.resolve(1);'), 'VF_COMPLETION_IMMEDIATE_PROMISE', case_options={'classification': 'baseline_limitation'})
    add('completion.shadow-on', '局部纯 on 函数触发旧 listener 名称启发式', 'completion.boundary', body(f.NODE, 'function on() { return 1; } on();'), 'VF_NODE_LONG_LIVED_LISTENER', case_options={'classification': 'baseline_limitation'})
    add('completion.plugin-promise-hook', 'immediate Plugin hook 同步返回 Promise', 'completion.signature', plugin.replace('BODY', '').replace('void context.abiVersion;', 'void context.abiVersion; return Promise.resolve();'), 'VF_COMPLETION_IMMEDIATE_PROMISE', role='plugin')
    add('completion.plugin-suspend-hook', 'suspend Plugin 允许 async hook 且工厂同步', 'completion.signature', plugin.replace('beforeRun()', 'async beforeRun()'), role='plugin', case_options={'completion': 'suspend'})
    add('completion.plugin-async-factory', 'Plugin 工厂自身 async 不等于可 suspend hook', 'completion.signature', plugin.replace('function createPlugin', 'async function createPlugin'), 'VF_PLUGIN_FACTORY', role='plugin')
    add('completion.host-async-start', 'Host 生命周期 async start 属于允许职责', 'completion.signature', host.replace('start()', 'async start()'), role='host')
    add('completion.abi-input', '真实 build 拒绝 Node 输入 TS 签名不匹配', 'native.contract', node.replace(f.INPUTS, 'Readonly<{"parity.value": Readonly<{value: string}>}>'), 'VF_TYPESCRIPT', case_options={'entrypoint': 'build'}, located=False)

    # Immutable import-time declarations keep the intended mutation rule reachable.
    frozen = 'const shared = Object.freeze({count: 0, nested: Object.freeze({count: 0})});\n'
    for name, code in (
        ('alias', 'const alias = shared; (alias as {count: number}).count += 1;'),
        ('alias-chain', 'const a = shared; const b = a; (b as {count: number}).count = 2;'),
        ('nested-alias', 'const nested = shared.nested; (nested as {count: number}).count++;'),
        ('delete', 'delete (shared as {count?: number}).count;'),
        ('object-assign', 'Object.assign(shared, {count: 2});'),
        ('define-property', 'Object.defineProperty(shared, "count", {value: 2});'),
        ('reflect-set', 'Reflect.set(shared, "count", 2);'),
        ('reflect-delete', 'Reflect.deleteProperty(shared, "count");'),
    ):
        add('state.' + name, '模块状态 ' + name, 'effects.module_state', frozen + body(f.NODE, code), 'VF_MODULE_STATE')
    for name, code in (
        ('prototype', '(Array.prototype as unknown as {parity: number}).parity = 1;'),
        ('prototype-alias', 'const proto = Array.prototype; (proto as unknown as {parity: number}).parity = 1;'),
        ('prototype-assigned-alias', 'let proto: unknown; proto = Array.prototype; (proto as {parity: number}).parity++;'),
        ('builtin-object', '(Math as unknown as {parity: number}).parity = 1;'),
        ('builtin-alias', 'const math = Math; Object.assign(math, {parity: 1});'),
        ('builtin-computed', '(JSON as unknown as Record<string, unknown>)["parity"] = 1;'),
    ):
        add('state.' + name, '共享内建状态 ' + name, 'effects.module_state', body(f.NODE, code), 'VF_MODULE_STATE')
    add('state.local-object.normal', '局部对象正常可变', 'effects.shadow', body(f.NODE, 'const shared = {count: 0}; shared.count++; Object.assign(shared, {count: 2});'))
    add('state.local-array.normal', '局部数组 prototype 同名属性不是共享原型', 'effects.shadow', body(f.NODE, 'const Array = {prototype: {count: 0}}; Array.prototype.count++;'))
    for flag in ('y', 'gy'):
        add('state.regexp-' + flag, '模块持有 RegExp ' + flag + ' 状态', 'effects.regexp', 'const matcher = /value/' + flag + ';\n' + body(f.NODE, 'matcher.exec("value");'), 'VF_MODULE_STATE')
    add('state.regexp-local.normal', '每次调用创建局部 g/y RegExp', 'effects.regexp', body(f.NODE, 'const matcher = /value/gy; matcher.test("value");'))
    add('state.regexp-stateless.normal', '模块普通无 g/y RegExp', 'effects.regexp', 'const matcher = /value/i;\n' + body(f.NODE, 'matcher.test("value");'))
    add('state.global-this-write', 'Host globalThis 对象写入不在旧 builtin/module alias 判断中', 'effects.analysis_boundary', body(f.HOST, '(globalThis as unknown as {parity: number}).parity = 1;'), role='host',
        case_options={'classification': 'baseline_limitation', 'notes': 'globalThis 非 builtinObjects 集合；未据此宣称审查允许所有全局状态。'})

    # Host primitives use the real checker, including local symbol shadows.
    for name, expression in (
        ('date', 'Date.now();'), ('performance', 'performance.now();'),
        ('crypto', 'void crypto;'), ('process', 'void process;'),
        ('document', 'void document;'), ('fetch', 'void fetch;'),
        ('math-computed', 'const operation = "random"; Math[operation]();'),
        ('math-escape', 'const math = Math; void math;'),
    ):
        add('base.host-' + name, 'BaseLib 宿主子分支 ' + name, 'effects.host_io', body(f.BASE_LIB, expression), 'VF_BASE_LIB_HOST_IO', role='base_lib')
    for name, expression in (
        ('date', 'const Date = {now: () => 1}; Date.now();'),
        ('fetch', 'const fetch = (value: number) => value + 1; fetch(value);'),
        ('math', 'const Math = {random: () => 1}; Math.random();'),
        ('pure-math', 'Math.abs(value);'),
    ):
        add('base.shadow-' + name, 'BaseLib 正常纯局部 ' + name, 'effects.shadow', body(f.BASE_LIB, expression), role='base_lib')
    for module in ('fs', 'http', 'worker_threads'):
        add('base.builtin-' + module, 'BaseLib 导入宿主 builtin ' + module, 'effects.host_io', f'import * as platform from "node:{module}";\n' + body(f.BASE_LIB, 'void platform;'), 'VF_BASE_LIB_HOST_IO', role='base_lib')
    add('plugin.shadow-global.normal', 'Plugin 局部 globalThis 名称遮蔽', 'effects.shadow', body(f.PLUGIN, 'const globalThis = {value: 1}; void globalThis.value'), role='plugin')

    # Real selected resources, rather than invented policy owners.
    plugin_extras = {'plugins/other.ts': plugin}
    plugin_manifest = {'plugins/other.jsonc': f._plugin_descriptor('parity.other_plugin', 'plugins/other.ts')}
    for role, template in (('node', f.NODE), ('base_lib', f.BASE_LIB)):
        add('imports.' + role + '-plugin', role + ' 跨层导入实际已选 Plugin', 'imports.layer', 'import {createPlugin} from "../plugins/other.ts";\n' + body(template, 'void createPlugin;'), 'VF_IMPORT_LAYER', role=role,
            case_options={'extras': plugin_extras, 'extra_manifests': plugin_manifest}, config_patch={'plugins': ['parity.other_plugin']})
    for kind in ('runtime', 'registry', 'capability'):
        add('imports.' + kind + '-unowned', '正式 Application 无独立 ' + kind + ' 源 owner 时仍拒绝未归属文件', 'imports.unreachable_owner', f'import {{helper}} from "../{kind}/helper.ts";\n' + body(f.NODE, 'helper();'), 'VF_IMPORT_OWNER',
            case_options={'extras': {f'{kind}/helper.ts': 'export function helper() { return 1; }\n'}, 'classification': 'baseline_limitation', 'notes': '真实归属生成器不生产该 kind；此案例准确验证未归属拒绝，不伪造 owner 声称 VF_IMPORT_LAYER 分支可达。'})
    base_other = f._base_descriptor('parity.other_math', 'base_lib/other.ts')
    math = f._base_descriptor('parity.math', 'base_lib/math.ts', ('parity.other_math',))
    add('imports.base-declared.normal', '声明实际 BaseLib 间依赖后的正常相对导入', 'imports.control', 'import {step} from "./other.ts";\n' + body(f.BASE_LIB, 'step(value);'), role='base_lib',
        case_options={'extras': {'base_lib/other.ts': 'export function step(value: number) { return value + 1; }\n'}, 'extra_manifests': {'base_lib/other.jsonc': base_other, 'base_lib/math.jsonc': math}})
    for role, factory, template, helper, path, resource_id, selected_key in (
        ('plugin', 'createPlugin', f.PLUGIN, f._plugin_descriptor, 'plugins', 'parity.other_plugin', 'plugins'),
        ('host', 'createHostExtension', f.HOST, f._host_descriptor, 'host_extensions', 'parity.other_host', 'host_extensions'),
    ):
        main_id = 'parity.plugin' if role == 'plugin' else 'parity.host'
        main_file = 'plugins/runtime.ts' if role == 'plugin' else 'host_extensions/host.ts'
        main_manifest = helper(main_id, main_file)
        main_manifest['dependencies'] = [resource_id]
        add('imports.' + role + '-declared.normal', '声明实际 ' + role + ' 间依赖后的正常导入', 'imports.control', f'import {{{factory} as other}} from "./other.ts";\n' + body(template, 'void other;'), role=role,
            case_options={'extras': {path + '/other.ts': body(template)}, 'extra_manifests': {path + '/other.jsonc': helper(resource_id, path + '/other.ts'), path + ('/runtime.jsonc' if role == 'plugin' else '/host.jsonc'): main_manifest}}, config_patch={selected_key: [main_id, resource_id]})

    # Host duties make native capability checks reachable before optional Node IO.
    for name, expression, code in (
        ('worker', 'new Worker("./worker.js");', 'VF_SINGLE_ESM_WORKER'),
        ('shared-worker', 'new SharedWorker("./worker.js");', 'VF_SINGLE_ESM_WORKER'),
        ('service-worker', 'navigator.serviceWorker.register("./worker.js");', 'VF_SINGLE_ESM_WORKER'),
        ('worklet', 'declareWorklet.addModule("./processor.js");', 'VF_SINGLE_ESM_WORKER'),
        ('module-url', 'new URL("./asset.dat", import.meta.url);', 'VF_SINGLE_ESM_RESOURCE'),
        ('fetch-local', 'fetch("./asset.dat");', 'VF_SINGLE_ESM_RESOURCE'),
        ('import-scripts', 'importScripts("./worker.js");', 'VF_SINGLE_ESM_RESOURCE'),
        ('wasm', 'void WebAssembly;', 'VF_SINGLE_ESM_WASM'),
    ):
        source = body(f.HOST, expression)
        if name == 'worklet':
            source = 'declare const declareWorklet: {addModule(path: string): void};\n' + source
        add('native.' + name, 'single-esm 原生能力 ' + name, 'native.single_esm', source, code, role='host', target='browser', case_options={'entrypoint': 'build'})
    for name, expression in (('absolute-url', 'new URL("https://example.invalid/data", import.meta.url);'), ('fetch-absolute', 'fetch("https://example.invalid/data");')):
        add('native.' + name + '.normal', 'single-esm 允许非本地资源 URL ' + name, 'native.single_esm', body(f.HOST, expression), role='host', target='browser', case_options={'entrypoint': 'build', 'notes': '只构建，不启动 Host，不产生网络请求。'})

    # Precise text boundaries use real TS files, not fabricated metrics.
    def lines(count):
        return node + '\n' * (count - len(node.splitlines()))
    def bytes_(count):
        return node + '//' + 'x' * (count - len(node.encode()) - 3) + '\n'
    for count, code, severity in ((449, '', 'error'), (450, 'NODE.PURITY.SOURCE_NEAR_LIMIT', 'warning'), (500, 'NODE.PURITY.SOURCE_NEAR_LIMIT', 'warning'), (501, 'NODE.PURITY.SOURCE_TOO_LARGE', 'error')):
        add('numeric.lines-' + str(count), '真实 Node 源码行边界 ' + str(count), 'maintainability.source', lines(count), code, severity=severity)
    for count, code, severity in ((53999, '', 'error'), (54000, 'NODE.PURITY.SOURCE_BYTES_NEAR_LIMIT', 'warning'), (60000, 'NODE.PURITY.SOURCE_BYTES_NEAR_LIMIT', 'warning'), (60001, 'NODE.PURITY.SOURCE_BYTES_TOO_LARGE', 'error')):
        add('numeric.bytes-' + str(count), '真实 Node 字节边界 ' + str(count), 'maintainability.source', bytes_(count), code, severity=severity)
    source = body(f.NODE, 'if (inputs["parity.value"].value > 0) { if (inputs["parity.value"].value > 1) { void 1; } }')
    for key, limit, normal_limit in (('max_functions', 1, 2), ('max_branches', 1, 2), ('max_nesting_depth', 1, 2), ('max_contract_keys', 1, 2)):
        for value, code in ((limit, 'NODE.MAINTAINABILITY.COMPLEXITY_' + key.upper()), (normal_limit, '')):
            measured_source = 'function helper(value: number) {return value + 1;}\n' + source if key == 'max_functions' else source
            add('numeric.' + key + '-' + str(value), '显式 TS 数值规则 ' + key + '=' + str(value), 'maintainability.configured', measured_source, code, policy={'complexity': {key: value}})
    for limit, code in ((1, 'NODE.MAINTAINABILITY.COMPLEXITY_MAX_PARAMS'), (2, '')):
        add('numeric.max_params-' + str(limit), '实际 Node descriptor 参数数与限值 ' + str(limit), 'maintainability.configured', node, code, policy={'complexity': {'max_params': limit}},
            node_patch={'contract': {'params_schema': {'first': {'type': 'number'}, 'second': {'type': 'number'}}, 'params_defaults': {'first': 1, 'second': 2}}})
    for key in ('max_functions', 'max_branches', 'max_nesting_depth'):
        for limit in (1, 2):
            measured = 'function helper(value: number) {return value + 1;}\n' + base if key == 'max_functions' else body(f.BASE_LIB, 'if (value > 0) {if (value > 1) {void 1;}}')
            add('numeric.base-' + key + '-' + str(limit), 'BaseLib 可配置 TS 指标 ' + key + '=' + str(limit), 'maintainability.configured', measured,
                'BASE_LIB.COMPLEXITY.' + key.upper() if limit == 1 else '', role='base_lib', policy={'complexity': {key: limit}})
    for count in (500, 501):
        source = base + '\n' * (count - len(base.splitlines()))
        add('numeric.base-lines-' + str(count), '真实 BaseLib 行边界 ' + str(count), 'maintainability.source', source, 'BASE_LIB.SOURCE.MAX_LINES' if count > 500 else '', role='base_lib')
    for count in (60000, 60001):
        source = base + '//' + 'x' * (count - len(base.encode()) - 3) + '\n'
        add('numeric.base-bytes-' + str(count), '真实 BaseLib 字节边界 ' + str(count), 'maintainability.source', source, 'BASE_LIB.SOURCE.MAX_BYTES' if count > 60000 else '', role='base_lib')
    for depth in (3, 4, 5):
        extras, manifests = {}, {'base_lib/math.jsonc': f._base_descriptor('parity.math', 'base_lib/math.ts', ('parity.chain1',))}
        for index in range(1, depth):
            dependencies = (f'parity.chain{index+1}',) if index + 1 < depth else ()
            file = f'base_lib/chain{index}.ts'
            extras[file] = f'import {{step as next}} from "./chain{index+1}.ts";\nexport function step(value: number): number {{return next(value);}}\n' if dependencies else 'export function step(value: number) {return value + 1;}\n'
            manifests[f'base_lib/chain{index}.jsonc'] = f._base_descriptor(f'parity.chain{index}', file, dependencies)
        add('numeric.dependency-' + str(depth + 1), '实际依赖链指标 ' + str(depth + 1), 'maintainability.dependencies', 'import {step} from "./chain1.ts";\nexport function increment(value: number): number {return step(value);}\n', 'NODE.MAINTAINABILITY.DEPENDENCY_CHAIN_TOO_DEEP' if depth + 1 > 4 else '', role='base_lib', severity='warning',
            case_options={'extras': extras, 'extra_manifests': manifests, 'metrics': {'dependency_chain_length': depth + 1} if depth + 1 > 4 else {'source_files': depth + 1}})

    # JS TaskPlan is generated from JSONC call metadata; there is no Python-like
    # public constructor to inject into the implementation.
    for mode in ('result_key', 'detached'):
        patch = {'async': mode, **({'result_key': 'result'} if mode == 'result_key' else {})}
        add('task.' + mode + '.normal', '真实 JSONC ' + mode + ' TaskPlan 构建和执行', 'native.task_plan', node, case_options={'entrypoint': 'build-run', 'metrics': {'business_result': 4}}, call_patch=patch)
        add('task.' + mode + '.sync', '同步 workflow 原生生成 TaskPlan ' + mode + ' 元数据', 'native.task_plan', node, call_patch=patch, pipeline_patch={'entry_mode': 'sync'}, located=False,
            case_options={'notes': 'metadata 本身不是同步调用 Promise；不把 Python 线程资格假设套给 JavaScript 计划。'})
    add('task.result-missing-contract', 'TaskPlan result_key 必须是实际声明输出', 'native.task_plan', node, 'GRAPH.ASYNC.RESULT_KEY_CONTRACT', call_patch={'async': 'result_key', 'result_key': 'missing'}, located=False)
    add('task.helper-timer-escape', '实际调用的独立 helper timer 未被 Node export visitor 递归审查', 'async.analysis_boundary', 'function launch() {setTimeout(() => 1, 1);}\n' + body(f.NODE, 'launch();'),
        case_options={'classification': 'baseline_limitation', 'notes': '实际到达 helper，但 completion visitor 不沿调用图展开；通过只能证明旧边界，不证明 timer 获得了 TaskPlan owner。'})
    add('task.helper-promise-escape', '返回 void 的 helper 隐藏丢弃 Promise 工作', 'async.analysis_boundary', 'function launch(): void {void Promise.resolve(1);}\n' + body(f.NODE, 'launch();'),
        case_options={'classification': 'baseline_limitation'})
    for name, app_source in (
        ('timer', 'setTimeout(() => 1, 1);\n'),
        ('promise', 'void Promise.resolve(1);\n'),
        ('normal', 'const value = 1; void value;\n'),
    ):
        add('source-owner.app-' + name, '实际 web-app 源码 ' + name + ' 的 owner=source 可达边界', 'async.source_owner', node,
            profile='web-app', target='browser', case_options={'entrypoint': 'build', 'extras': {'web/app.ts': app_source, 'web/index.template.html': '<!doctype html><html><body><!-- VIBEFLOW_APP_ENTRY --></body></html>\n'},
            'classification': 'baseline_limitation', 'notes': '正式 Application 不生成 source owner；实际 App 源码进入 esbuild closure，不伪造 importPolicy 归属。'})
    for name, examples in (
        ('inputs.normal', [{'inputs': {'parity.value': {'value': 3}}, 'params': {}}]),
        ('outputs', [{'inputs': {'parity.value': {'value': 3}}, 'params': {}, 'outputs': {'result': 4}}]),
    ):
        add('declaration.examples-' + name, '实际 JS Node 合同样例 ' + name, 'declaration.examples', node,
            node_patch={'contract': {'examples': examples}}, case_options={'notes': '验证 JS 正式审查，不将 Python 旧样例规则推定为 JavaScript 已有规则。'})
    return tuple(rows)


def _merge(base, patch):
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _merge(base[key], value)
        else:
            base[key] = value


def _task_route(fixture, root, variant, document, mode):
    """An actual result consumer or detached side call keeps the control valid."""
    if mode == 'result_key':
        declaration = fixture._node_descriptor(variant, 'parity.consume', 'nodes/consume.ts', fixture.Case('consumer', '', 'control'))
        declaration['contract']['requires'][0]['type'] = 'parity.result'
        declaration['contract']['input_semantics'] = {'parity.result': ['Awaited task result.']}
        declaration['contract']['provides'] = [{'key': 'final', 'type': 'parity.final', 'display_name': 'Final'}]
        declaration['contract']['output_semantics'] = {'final': ['Actual task consumer output.']}
        source = 'export function run(inputs: Readonly<{"parity.result": Readonly<{value: number}>}>) {return {final: inputs["parity.result"].value};}\n'
        fixture._write_json(root / 'manifests/data_schemas/final.jsonc', {'kind': 'data_schema', 'type_key': 'parity.final', 'schema': {'type': 'number'}})
        document['pipeline']['outputs'][0]['type'] = 'parity.final'
    else:
        document['pipeline']['nodes'][0].pop('async', None)
        declaration = fixture._node_descriptor(variant, 'parity.consume', 'nodes/consume.ts', fixture.Case('consumer', '', 'control'))
        declaration['contract'].update(requires=[], provides=[], input_semantics={}, output_semantics={})
        source = 'export function run() {return {};}\n'
    fixture._write_json(root / 'manifests/nodes/consume.jsonc', declaration)
    (root / 'nodes/consume.ts').write_text(source, encoding='utf-8')
    call = {'id': 'consume', 'type_used': 'parity.consume', 'display_name': 'Consume actual task', 'description': 'Real task route.'}
    if mode == 'detached':
        call['async'] = 'detached'
    document['pipeline']['nodes'].append(call)
    document['pipeline']['edges'] = [{'from': 'calculate', 'to': 'consume'}]


def run_variants(work_root: Path, variant: str, toolchain: Path, *, fixture: Any) -> list[dict[str, Any]]:
    observations = []
    for index, item in enumerate(variants(fixture)):
        case = item.case
        root = Path(work_root) / f'{index:02d}-{case.id}'
        workspace, config, source = fixture._project(root, variant, toolchain, case)
        document = json.loads(config.read_text())
        _merge(document, item.config_patch)
        _merge(document['pipeline'], item.pipeline_patch)
        _merge(document['pipeline']['nodes'][0], item.call_patch)
        if case.id.startswith('js.variant.task.') and case.id.endswith(('.normal', '.sync')):
            _task_route(fixture, root, variant, document, item.call_patch['async'])
        fixture._write_json(config, document)
        node_path = root / 'manifests/nodes/calc.jsonc'
        descriptor = json.loads(node_path.read_text())
        _merge(descriptor, item.node_patch)
        if case.role != 'node':
            descriptor['implementations'][0]['completion'] = 'immediate'
        fixture._write_json(node_path, descriptor)
        if case.role == 'plugin':
            path = root / 'manifests/plugins/runtime.jsonc'
            declaration = json.loads(path.read_text())
            declaration['implementations'][0]['completion'] = case.completion
            fixture._write_json(path, declaration)
        if item.policy:
            if variant == 'baseline':
                fixture._write_json(root / 'kernel_policy.jsonc', item.policy)
            else:
                project_path = root / 'vibeflow_project.jsonc'
                project = json.loads(project_path.read_text())
                project.setdefault('descriptors', {})['rulesets'] = ['manifests/rulesets']
                fixture._write_json(project_path, project)
                fixture._write_json(root / 'manifests/rulesets/numeric.jsonc', {
                    'kind': 'ruleset', 'id': 'parity.numeric', 'calls': [{'id': 'native', 'ruleset_id': 'vibeflow.process'}],
                    'relations': [{'source': '$self', 'target': 'native/maintainability', 'kind': 'overrides', 'params': {'policy': item.policy}}],
                })
                descriptor['rulesets'] = ['parity.numeric']
                fixture._write_json(node_path, descriptor)
        if variant == 'current':
            import runpy
            runpy.run_path(str(Path(__file__).resolve().parents[3] / 'tests/fixtures/support/code_plugins.py'))['migrate_fixture'](root)
        if (case.entrypoint == 'build' and (item.target != 'node' or item.profile != 'single-esm')) or (case.entrypoint == 'build-run' and case.id.startswith('js.variant.task.')):
            from vibeflow.tooling.application.javascript.build import ProjectBuildRequest, build_project_aot
            try:
                result = build_project_aot(ProjectBuildRequest(workspace, config, root.parent / (root.name + '-build'), item.target, item.profile,
                        html_template=root / 'web/index.template.html' if item.profile == 'web-app' else None,
                        app_entry=root / 'web/app.ts' if item.profile == 'web-app' else None))
                metrics = {'built': True}
                if case.entrypoint == 'build-run':
                    script = f'import {{pathToFileURL}} from "node:url"; const workflow = await import(pathToFileURL({json.dumps(str(result.entry))})); try {{process.stdout.write(JSON.stringify(await workflow.runWorkflowAsync({{value: 3}})));}} catch (error) {{process.stdout.write(JSON.stringify({{code: error.code, message: error.message}})); process.exitCode=1;}}'
                    executed = subprocess.run(['node', '--input-type=module', '--eval', script], cwd=root, capture_output=True, text=True, check=False)
                    payload = json.loads(executed.stdout) if executed.stdout else {'message': executed.stderr}
                    if executed.returncode:
                        actual = fixture._actual('FAIL', fixture._finding_rows(payload), message=payload['message'])
                    else:
                        metrics['business_result'] = payload['result']
                        actual = fixture._actual('CONCERNS' if result.prepared.warnings else 'PASS', list(result.prepared.warnings), metrics=metrics)
                else:
                    actual = fixture._actual('CONCERNS' if result.prepared.warnings else 'PASS', list(result.prepared.warnings), metrics=metrics)
            except Exception as error:
                payload = {'code': str(getattr(error, 'code', None) or getattr(error, 'rule_id', None) or type(error).__name__), 'message': str(error),
                           'details': dict(getattr(error, 'details', {}) or {}), 'diagnostics': list(getattr(error, 'diagnostics', ()) or ())}
                actual = fixture._actual('FAIL', fixture._finding_rows(payload), message=str(error))
        else:
            actual = fixture._observe(case, root, workspace, config, source)
        code = case.current_code if variant == 'current' and case.current_code is not None else case.code
        expected = {'should_accept': not code or item.severity == 'warning', 'codes': [{'code': code, 'severity': item.severity}] if code else [], 'metrics': dict(case.metrics)}
        if code and item.located:
            expected['located_codes'] = [code]
        if item.message_contains:
            expected['message_contains'] = item.message_contains
        observations.append({'id': case.id, 'title': case.title, 'family': case.family, 'classification': case.classification,
                             'expected': expected, 'actual': actual, 'notes': case.notes,
                             'evidence': {'level': case.entrypoint, 'source': str(source), 'config': str(config), 'workspace': str(workspace), 'profile': item.profile, 'target': item.target}})
    return observations


__all__ = ['run_variants', 'variants']
