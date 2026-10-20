# Python 资源与插件 SDK

使用 `vibeflow.targets.python.sdk` 把 Node、Rule 的声明与实现放在一起，再用固定 `Plugin` 列出贡献资源。workflow 显式选择该插件后，其资源进入本次检查和运行范围。

## Node 与固定插件

`plugins/text.py`：

```python
from vibeflow.targets.python.sdk import Plugin, node, data_schema, update_run_info

@node(
    type_key="example.normalize_text",
    display_name="Normalize text",
    description="Normalizes whitespace in supplied text.",
    rulesets=["vibeflow.process"],
    contract={
        "requires": [{"type": "text.raw", "cardinality": "exactly_one", "display_name": "Raw text"}],
        "provides": [{"key": "normalized_text", "type": "text.normalized", "display_name": "Normalized text"}],
        "input_semantics": {"text.raw": ["Text before normalization."]},
        "output_semantics": {"normalized_text": ["Normalized whitespace."]},
    },
)
class NormalizeText:
    def run_pure(self, inputs, params):
        normalized_text = " ".join(inputs["text.raw"]["value"].split())
        update_run_info([{
            "id": "normalize", "characters": len(normalized_text),
            "message": "文本规范化完成",
        }])
        return {"normalized_text": normalized_text}

raw = data_schema(type_key="text.raw", schema={"type": "string"})
normalized = data_schema(type_key="text.normalized", schema={"type": "string"})
plugin = Plugin(id="example.text", resources=[NormalizeText, raw, normalized],
                declaration_rulesets=["vibeflow.plugin_declaration"])
```

workflow 保留 JSONC 和原生连边，下面是插件选择与 Node 调用片段：

```jsonc
{
  "plugins": [{"source": {"kind": "file", "ref": "plugins/text.py"}}],
  "pipeline": {
    "nodes": [{"id": "normalize", "type_used": "example.normalize_text",
      "display_name": "Normalize", "description": "Normalize the input"}],
    "edges": []
  }
}
```

插件 source 的文件路径相对所属项目 root；可通过 `root` 选择另一个已登记 workspace root。默认导出名为 `plugin`，也支持显式 `export` 和已安装模块的 `source.kind: "module"/"package"`。

返回对象的 key 与 `provides[].key` 一致；调用点 `params` 使用声明的参数 schema/defaults。`@node` 保存契约、规则选择、默认展示以及实现类的源码位置。

直接装饰类或检查函数时，该对象决定实际实现和源码位置。通常让 SDK 自动定位即可；显式提供同语言 `source/implementations` 时，它们必须指向同一对象。同文件的导出别名、file/module 的同源定位可以使用。指向其他实际实现对象时，加载返回 `RESOURCE.IMPLEMENTATION.CONFLICT`，并提供声明与实际位置。需要绑定尚未导入的独立实现时，使用下文的延迟源码声明。

默认值支持 JSON 数组、对象及其嵌套组合。SDK 保存只读声明；`run_pure` 每次调用收到原生 `list/dict` 参数副本。默认值和调用点覆盖分别复制，修改本次参数不会影响保存的默认值、调用者的容器或后续运行。

`run_pure` 可以由源码范围内的父类提供。默认规则按 Python 的方法解析顺序检查实际生效的方法，包括其签名和副作用；诊断指向方法所在文件。跨文件父类需按资源归属要求显式登记。Decision 的路由输出可使用 `flow.*` 字段，例如 `flow.backend`，并在原生连边的 `when` 中引用。

纯路径运算可以使用 `from pathlib import PurePath`、`PurePosixPath` 或 `PureWindowsPath`，支持导入别名。默认副作用规则继续检查 Path 的实际 IO 和网络调用；已取得源码的项目 helper 根据函数体检查，reset/close 等名称本身不授予或取消权限。

`contextlib.ExitStack` 可以组织清理操作。默认规则根据源码确认接收对象后检查 `close()`，并按当前资源选择的副作用范围检查可解析的 `callback/push` 回调及其 helper 函数体。空栈清理可用于 Process Node；登记 `print/open` 仍需要相应规则允许，状态恢复需要状态规则允许。BaseLib 按自己的 Ruleset 检查，不继承调用 Node 的更宽权限；文件或连接的 `close()` 继续接受 IO 检查。

Node 通过 `rulesets` 选择审查约束。类型声明提供默认；调用 Config 缺省使用默认，显式列表完整替代，`[]` 仅取消当前调用局部规则；`flow_kind` 表达执行身份。自由 `tags/metadata` 和 `presentation` 由 Node 自己声明，见 [规则与 Node](rules-and-nodes.md)。

## 规则与其他资源

`@rule` 声明普通 `check(context, inputs, params)` 函数；`ruleset` 使用 `RuleCall/RuleRelation` 或同模型的字典组合。把函数及 Ruleset 放入插件的 `resources`。SourceContext 查询、具名 records 和覆盖关系见 [规则接口](rules-and-nodes.md)。

`base_lib`、`data_schema`、`capability` 和 `host_extension` 也产生固定资源定义。HostExtension 的运行协议由 JS/TS Target 提供；Python SDK 可贡献显式 JS 实现声明。

## 多文件实现与辅助库

在 `@node`、`@base_lib` 或生命周期声明中，用 `implementation_files=["support.py"]` 列出支撑文件。路径相对声明模块；同一资源的传递依赖也逐一登记。独立共享库使用 `@base_lib` 声明，由 Node 或生命周期的 `base_libs` 引用。库依赖其他库时使用 `dependencies`。

各资源选择自己的 Ruleset 与 `presentation`。例如，Node 选 `vibeflow.process`，库选 `vibeflow.base_lib`，生命周期选 `vibeflow.plugin`，插件声明选 `declaration_rulesets=["vibeflow.plugin_declaration"]`。默认可维护性规则按每个文件检查 500 行上限。完整登记和样式覆盖见[多文件资源](multifile-resources.md)。

## 延迟源码与加载时机

需要独立模块在检查后才导入时，使用相同接口的显式源码引用：

```python
from vibeflow.targets.python.sdk import node, SourceLocator

late_node = node(
    type_key="example.late", contract={}, rulesets=["vibeflow.process"],
    source=SourceLocator(kind="file", ref="nodes/late.py", export="LateNode"),
)
```

插件入口先加载固定定义，其直接导入按 Python 的模块机制初始化。显式延迟实现接受所选 import 规则后再绑定；检查失败时，尚未加载的实现及闭包保持未加载。完整流程见[插件加载与检查](plugins-and-integrations.md#加载与检查)。

```bash
python run.py validate --config python_project/configs/main.jsonc
python run.py quality --path python_project
python run.py review-rules --config python_project/configs/main.jsonc --json
python run.py inspect-resources --config python_project/configs/main.jsonc --json
```

资源查询和规则预览加载固定定义，框架不调用检查函数、业务执行入口或生命周期工厂。

## 在业务 Node 中更新进度

上例在 `run_pure` 中调用 `update_run_info`，同时照常返回契约声明的输出。函数从当前运行上下文取得状态缓存，Node 的方法签名与 `rulesets` 选择沿用原声明。训练 Node 可以在每轮结束后用同一接口提交轮次和指标。

每次调用替换完整 `info` 数组。需要同时保留训练进度和指标时，在一次调用中提供两个对象；`[]` 清空信息。内核在下一次定时刷新、状态变化或结束时写入最新缓存。默认间隔为 60 秒，命令行用 `--status-interval` 调整。完整数据格式、日志位置和监控配置见[运行日志与状态接口](runtime-observation.md)。

普通节点的并发分发、显式汇合、取消与实际收尾合同见[普通图并发](graph-concurrency.md)。


## AOT 目录部署

开发时运行 `run` 会执行当前源码的静态审查和编译。部署时先构建一次：

```bash
python run.py build --config python_project/configs/main.jsonc --out-dir python_project/build/aot
# 直接使用安装的工具时，显式提供 workspace：
python -m vibeflow build --workspace vibeflow_config.jsonc --config python_project/configs/main.jsonc --out-dir python_project/build/aot
python python_project/build/aot/run.py run --input python_project/probe_input.json --runtime-profile train
```

所属项目选择 Python target，默认 profile 为 `python-package`。输出目录包含匹配的 VibeFlow 框架、共同计划、Python 绑定、预生成块代码和项目实现。整目录可移到另一台机器；目标环境提供 Python 3.11+ 及业务依赖，例如 PyTorch、CUDA。运行无需原 workspace，也不会再次执行源码规则、图编译、计划推导或架构图生成。不适合块执行的图继续使用已准备结构动态调度。

Node、插件及支撑代码按原包路径保留，包内资源随包收集。根目录数据、动态导入所需文件可用重复的 `--include assets --include extra_module.py` 添加，路径相对 workflow 所属 root。外部数据和 checkpoint 由调用者提供。框架拥有的定位会重定位；业务配置中的普通路径字符串不改写，相对路径继续以调用者工作目录为准。

```python
from vibeflow.tooling.application.python import PythonBuildRequest, build_python_aot, load_bundle

build_python_aot(PythonBuildRequest(
    workspace="vibeflow_config.jsonc", config="python_project/configs/main.jsonc",
    out_dir="candidate-bundle", include=("assets",)))
bundle = load_bundle("candidate-bundle")
runtime = bundle.create_runtime(
    run_dir="runs/embedded", runtime_options={"execution": "compiled", "trace": "boundary"},
    global_config={"model": model}, capabilities={"device": device})
result = runtime.run(initial)
# 高层运行自动创建独立 run 目录，返回现有 CheckedRunResult：
checked = bundle.run(initial, run_root="runs", runtime_options={"execution": "plan"})
```

搬迁后也可从 bundle 自带的框架导入 API：将 `<bundle>/_framework` 加入 Python 模块搜索路径，再调用 `load_bundle()`。构建返回的 `PythonBuildResult.health` 保留静态审查的 PASS/CONCERNS；运行沿用 CheckedRunResult/CheckedRunError 和执行报告。

同一 bundle 可创建独立 runtime；节点实例、线程、取消与锁属于运行期。`create_runtime()` 准备结构，在首次 `run()` 中先创建运行时插件，再绑定 Node；复用这个 runtime 会保留 Node 实例，每次执行重新创建和释放运行时插件。输入、全局值和宿主能力保留对象引用，普通 Node 配置按现有规则生成独立容器。编译插件在构建时运行；runtime 插件按每次执行创建并在任务收尾后释放。`plan`、`block`、`compiled` 与 Hook/trace 选项沿用源码 runtime。

声明 delegated CLI 合同的图可运行：

```bash
python candidate-bundle/run.py delegate-cli -- --help
```

业务标准流与退出码使用原 delegated CLI 协议；框架诊断写入 run 日志。构建保留原静态审查的 CONCERNS 和 planned stub 开发标记，不把它们改成 PASS。`--replace` 仅替换仍归本工具所有的完整构建目录。

新计划为 Workflow ABI v9，构建元数据为 `vibeflow.aot-build.v3`；共同头保存工作流、ABI、入口和文件，`target_metadata` 保存该语言的 profile、工具链与绑定定位。旧计划或 manifest 不作兼容解码，请用当前源码重新构建；已有独立 JS 产物仍可继续使用其随附运行代码。
