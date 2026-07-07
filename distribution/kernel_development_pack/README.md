# VibeFlow 分发开发包

这个目录是给“使用内核开发业务程序的人或 AI”看的分发材料。它不解释内核内部实现，只说明如何把程序拆成标准流程图 node、纯 `base_lib`、可选 plugin 和 JSONC 配置，并通过内核强制健康检查后运行。

推荐分发方式：

1. 在仓库根目录运行 `python build_distribution.py`。
2. 复制生成的 `vibeflow_distribution/` 作为新项目骨架。
3. 在新项目里开发 `project/nodes/`、`project/base_lib/`、`project/plugins/` 和 `project/configs/*.jsonc`。
4. 用模板里的 `run.py` 启动检查、运行和图形导出。

复制后的推荐结构：

```text
my_project/
  AGENTS.md
  README.md
  vibeflow_config.jsonc
  run.py
  kernel/
    vibeflow-kernel.zip
    MANIFEST.sha256
    README.md
    docs/
    tools/
      mermaid-renderer/
    THIRD_PARTY_NOTICES.md
  project/
    vibeflow_project.jsonc
    nodes/
    base_lib/
    plugins/
    configs/
    registry.py
  runs/
  reports/
```

核心原则：根目录 `vibeflow_config.jsonc` 只声明 workspace roots 和全局 policy；每个 root 的 `vibeflow_project.jsonc` 声明 registry、base_lib、plugins 和 quality 开关。`quality.structure` 默认用 warning/error 双阈值治理 root 代码布局，允许 root 总文件数增长到 120，但单个代码目录超过 16 个 `.py` 会失败，促使 `nodes/`、`base_lib/`、`plugins/` 按功能拆分。业务开发者只写小型纯函数 node、纯 helper、必要插件和 JSONC 拓扑配置；控制流只写在显式 `pipeline.edges` 中；运行前由内核自动健康检查，检查不过不执行。运行时只审计流程和 key，node 间可按引用传递普通 Python 对象。`kernel/docs/`、`kernel/tools/` 和 `kernel/THIRD_PARTY_NOTICES.md` 是随内核分发的只读参考材料；根目录 `README.md`、`AGENTS.md` 和项目自己的文档可以按项目定制。

常用命令：

```powershell
python run.py validate --config project/configs/main.jsonc
python run.py run --config project/configs/main.jsonc --run-root runs
python run.py mermaid --config project/configs/main.jsonc --output reports/graph.mmd
python run.py ascii --config project/configs/main.jsonc --output reports/graph.txt
python run.py svg --config project/configs/main.jsonc --output reports/graph.svg
python run.py svg --config project/configs/main.jsonc --expand-nodesets --output reports/graph.expanded.svg
```

`run` 会在 `runs/<run_id>/` 自动写出快速图 `graph.svg` 和详细审查图 `graph.expanded.svg`。`svg` 默认会为 Mermaid CLI 放大渲染上限：普通图使用 `maxTextSize=200000`、`maxEdges=2000`；`--expand-nodesets` 使用 `maxTextSize=500000`、`maxEdges=5000`，并固定采用 `review-columns` SVG composer，把主流程、plugins、base_lib 和展开 nodeset 分列展示。SVG 保持 `htmlLabels=false`，但内核会对原生 SVG 文本做标题加粗、字段名前缀加粗和字段行左对齐增强。超大图可用 `--mermaid-max-text-size`、`--mermaid-max-edges` 和 `--review-fragment-max-width` 覆盖。

注意：`python run.py mermaid --expand-nodesets --output reports/graph.expanded.mmd` 只导出 Mermaid 源码，供调试源码使用。详细审查 SVG 必须用 `python run.py svg --expand-nodesets --output reports/graph.expanded.svg` 生成，不要把 `graph.expanded.mmd` 直接交给 Mermaid CLI/mmdc 转成 SVG，否则会绕过 VibeFlow 的 review-columns/detail-panel composer。

`svg` 命令依赖 `kernel/tools/mermaid-renderer/` 中的 Mermaid CLI。首次使用前运行：

```powershell
cd kernel/tools/mermaid-renderer
npm install
cd ../../..
```

不要求系统预装 Google Chrome。正常执行 `npm install` 后，Puppeteer 会安装并使用自己的浏览器缓存；如果该缓存不可用，VibeFlow 会再尝试非 snap 的系统 Chrome/Chromium。`/snap/bin/chromium` 会被跳过，因为它在 Puppeteer/mermaid-cli 下常见 profile lock 启动失败。

分发包不内置 `.gitignore`，忽略策略由项目自行决定。常见建议包括忽略 `kernel/tools/mermaid-renderer/node_modules/`、`runs/`、`reports/`、`__pycache__/` 和 `*.pyc`。
