# VibeFlow 可复制开发包

<!-- VIBEFLOW_DISTRIBUTION_GENERATED_AT -->

这个目录可以整体复制到其他位置作为新项目起点。它包含本地 kernel、内核文档、AI 开发提示词和可运行的示例项目骨架。

开始开发前，AI 和开发者都应先阅读 `AGENTS.md`，并按任务类型工作：

- 新建项目（greenfield）可以从粗粒度 planned 流程开始。
- 修改已有项目（existing）先读 `project/ARCHITECTURE.jsonc`，沿 source 定位真实 workflow config 及其导入 nodeset，然后原位修改。不为审核新建平行 config，不用概念图替代真实 config。

修改后用 `python run.py review` 完成正式架构审核。任务判定、`复用 / 修改 / 删除 / 新增`清单和人类批准门见 `AGENTS.md`。

业务 node、base_lib 和 plugin 分别放在 `project/nodes/`、`project/base_lib/` 和 `project/plugins/`，并在 `project/registry.py` 注册。每个 root 的 `vibeflow_project.jsonc` 声明 registry、quality、可选 runtime 参数和架构文档映射；根目录 `vibeflow_config.jsonc` 声明 workspace roots。

常用命令：

```powershell
python run.py architecture --config project/configs/main.jsonc --output project/ARCHITECTURE.jsonc
python run.py architecture --config project/configs/main.jsonc --output project/ARCHITECTURE.jsonc --check
python run.py review --config project/configs/main.jsonc --output reports/graph.expanded.svg
python run.py validate --config project/configs/main.jsonc
python run.py run --config project/configs/main.jsonc --run-root runs
python run.py mermaid --config project/configs/main.jsonc --output reports/graph.mmd
python run.py ascii --config project/configs/main.jsonc --output reports/graph.txt
python run.py svg --config project/configs/main.jsonc --output reports/graph.svg
python run.py svg --config project/configs/main.jsonc --expand-nodesets --output reports/graph.expanded.svg
python run.py quality --path project
python run.py verify-kernel
```

默认项目把 `project/configs/main.jsonc` 登记到 `project/ARCHITECTURE.jsonc`。这是带固定“生成且不可执行”头注释的单文件架构审查文档，不是 workflow config；AI 和开发者应先用它理解入口流程、nodeset 调用、节点职责、数据契约、资源和配置来源。架构变更必须落到真实 workflow config、相关 nodeset、registry metadata/config schema 或资源声明中。正式 `review` 会自动重新生成登记文档、执行正式 validate，并且只在 canonical expanded SVG 结构检查通过后发布 SVG；失败时不得用 mmdc、手写 SVG 或旧产物补位。

## 读取真实运行结果

自定义 adapter 或启动器调用 `run_workspace_checked(...)` / `run_checked(...)` 后，应从返回的 `CheckedRunResult.context` 读取真实 envelope：

```python
value = result.context.get("response.value")["value"]
```

`input_summary.json`、`output_summary.json` 和 trace 只保存脱敏摘要。其中的 `"scalar": true` 只表示原值是标量，不是业务布尔值 `True`，也无法区分 `True` 和 `False`。不要解析 `output_summary.json` 作为业务输出，也不要对摘要字典做 `bool(...)`。

配置文件分两层：根目录 `vibeflow_config.jsonc` 只声明 workspace roots 和全局 policy；每个 root 的 `vibeflow_project.jsonc` 声明 registry、quality、可选 runtime 参数和 `architecture.documents`。可用的 node/base_lib/plugin 都在同一个 `project/registry.py` 里注册；每个 workflow config 用 id 声明本流程实际使用哪些 base_lib/plugin。单项目模板默认是：

```jsonc
{
  "policy": {},
  "roots": [
    {"id": "project", "path": "project"}
  ]
}
```

多 root 仓库可以改成：

```jsonc
{
  "policy": {},
  "roots": [
    {"id": "vibetrain", "path": "vibetrain"},
    {"id": "project", "path": "project"}
  ]
}
```

每个 root 下都需要自己的 `vibeflow_project.jsonc`。`registry` 相对所属 root 目录解析；`runtime.async_max_workers` 控制该 root 内每个 Runtime 自有线程池的并发数（默认 4），`runtime.async_flush_timeout` 控制 detached task 的收尾等待时间，`runtime.nodeset_max_depth` 控制普通 nodeset 与 loop body 的最大静态嵌套深度（默认 4）。`architecture.documents` 用 root-relative `workflow` / `document` 登记需要强制保持新鲜的架构文档。`build_base_lib_registry()` / `build_plugin_registry()` 中的 module 或文件路径也按该 root 解析。`quality.structure` 使用 warning/error 双阈值治理 root 代码布局，默认允许最多 120 个 `.py`，但单个代码目录超过 16 个 `.py` 会失败，用来推动 `nodes/`、`base_lib/`、`plugins/` 按功能拆分。pipeline config 不再声明 `policy`，但必须声明本 workflow 实际使用的资源：

```jsonc
{
  "base_lib": {"modules": [{"id": "math_tools"}]},
  "plugins": [{"id": "project_policy", "config": {"level": "strict"}}],
  "pipeline": {"nodes": [], "edges": []}
}
```

审查图和 `health_report.json.info.resources` 只展示当前 workflow 实际引用的资源；`available_resources` 才展示 root registry 中可用但未必使用的资源。跨 root nodeset import 使用：

```jsonc
{
  "nodeset_imports": [
    {"root": "vibetrain", "path": "configs/nodesets/train_step.jsonc"}
  ]
}
```

`run` 会在 `runs/<run_id>/` 自动写出快速图 `graph.svg` 和详细审查图 `graph.expanded.svg`。VibeFlow 命令内部使用 bundled Mermaid CLI 渲染 SVG；Mermaid CLI/mmdc 是实现细节，不是公开审核入口。普通单项 `svg` 命令保留图形导出/诊断参数，正式架构审核则使用参数固定的 `review`。

`run` 还会在当次运行目录写出预期的 `architecture.jsonc` 供审计，但不会替你覆盖 root 中登记的 `project/ARCHITECTURE.jsonc`。

注意：`python run.py mermaid --expand-nodesets --output reports/graph.expanded.mmd` 只导出 Mermaid 源码，供调试源码使用。不要把 `graph.expanded.mmd` 直接交给 Mermaid CLI/mmdc 转成 SVG；正式审核使用 `python run.py review --config ... --output ...`。

如果要使用 `svg`，确保项目根目录存在 `kernel/tools/mermaid-renderer/`，并先执行：

```powershell
cd kernel/tools/mermaid-renderer
npm install
cd ../../..
```

不要求系统预装 Google Chrome。正常执行 `npm install` 后，Puppeteer 会安装并使用自己的浏览器缓存；如果该缓存不可用，VibeFlow 会再尝试非 snap 的系统 Chrome/Chromium。`/snap/bin/chromium` 会被跳过，因为它在 Puppeteer/mermaid-cli 下常见 profile lock 启动失败。

`kernel/docs/`、`kernel/tools/` 和 `kernel/THIRD_PARTY_NOTICES.md` 是随内核分发的只读参考材料；根目录 `README.md`、`AGENTS.md` 和项目自己的说明可以按项目定制。分发包不内置 `.gitignore`，建议项目自行忽略 `kernel/tools/mermaid-renderer/node_modules/`、`runs/`、`reports/`、`__pycache__/` 和 `*.pyc`。

模板中的最小 flow 是：

```text
terminal start -> process seed -> process add -> io output -> terminal end
```

可复用 nodeset 放在 `project/configs/nodesets/` 的独立 JSONC 文件中，根对象声明 `type_key`；主 config 通过 `nodeset_imports` 导入，并在调用点把该 `type_key` 写进 `type_used`。

implemented nodeset 必须包含完整 pipeline。planned nodeset 可以只保留契约占位，也可以带 planned body 逐步细化；body 会出现在 `ARCHITECTURE.jsonc` 和展开图中并参与适用的静态检查，但不会按 implemented body 执行。`python_stub` planned nodeset 始终作为单个 stub 执行。
