# 项目模板

使用方法：

1. 使用 `build_distribution.py` 生成包含 `kernel/vibeflow-kernel.zip` 的完整开发包。
2. 把本目录内容复制到新项目根目录。
3. 在 `project/nodes/` 中开发业务 node。
4. 在 `project/registry.py` 中注册 node，并在 `project/vibeflow_project.jsonc` 声明 registry、base_lib、plugins 和 quality 开关。
5. 根目录 `vibeflow_config.jsonc` 声明 workspace roots；单项目模板默认只包含 `project/`。
6. 在 `project/configs/main.jsonc` 中用 `id` / `type_used` 调用 node 或 nodeset，并用显式 `pipeline.edges` 组织拓扑。
7. 运行：

```powershell
python run.py validate --config project/configs/main.jsonc
python run.py run --config project/configs/main.jsonc --run-root runs
python run.py mermaid --config project/configs/main.jsonc --output reports/graph.mmd
python run.py ascii --config project/configs/main.jsonc --output reports/graph.txt
python run.py svg --config project/configs/main.jsonc --output reports/graph.svg
python run.py svg --config project/configs/main.jsonc --expand-nodesets --output reports/graph.expanded.svg
```

配置文件分两层：根目录 `vibeflow_config.jsonc` 只声明 workspace roots 和全局 policy；每个 root 的 `vibeflow_project.jsonc` 声明 registry、base_lib、plugins 和 quality 开关。单项目模板默认是：

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

每个 root 下都需要自己的 `vibeflow_project.jsonc`。`registry`、`base_lib.paths` 和 plugin 文件路径都相对所属 root 目录解析。`quality.structure` 使用 warning/error 双阈值治理 root 代码布局，默认允许最多 120 个 `.py`，但单个代码目录超过 16 个 `.py` 会失败，用来推动 `nodes/`、`base_lib/`、`plugins/` 按功能拆分。pipeline config 不再声明 `policy`、`base_lib` 或 `plugins`；跨 root nodeset import 使用：

```jsonc
{
  "nodeset_imports": [
    {"root": "vibetrain", "path": "configs/nodesets/train_step.jsonc"}
  ]
}
```

`run` 会在 `runs/<run_id>/` 自动写出快速图 `graph.svg` 和详细审查图 `graph.expanded.svg`。`svg` 默认会为 Mermaid CLI 放大渲染上限：普通图使用 `maxTextSize=200000`、`maxEdges=2000`；`--expand-nodesets` 使用 `maxTextSize=500000`、`maxEdges=5000`，并固定采用 `review-columns` SVG composer，把主流程、plugins、base_lib 和展开 nodeset 分列展示。SVG 保持 `htmlLabels=false`，但内核会对原生 SVG 文本做标题加粗、字段名前缀加粗和字段行左对齐增强。超大图可用 `--mermaid-max-text-size`、`--mermaid-max-edges` 和 `--review-fragment-max-width` 覆盖。

注意：`python run.py mermaid --expand-nodesets --output reports/graph.expanded.mmd` 只导出 Mermaid 源码，供调试源码使用。详细审查 SVG 必须用 `python run.py svg --expand-nodesets --output reports/graph.expanded.svg` 生成，不要把 `graph.expanded.mmd` 直接交给 Mermaid CLI/mmdc 转成 SVG，否则会绕过 VibeFlow 的 review-columns/detail-panel composer。

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
terminal start -> process seed -> process add -> terminal end
```

可复用 nodeset 放在 `project/configs/nodesets/` 的独立 JSONC 文件中，根对象声明 `type_key`；主 config 通过 `nodeset_imports` 导入，并在调用点把该 `type_key` 写进 `type_used`。
