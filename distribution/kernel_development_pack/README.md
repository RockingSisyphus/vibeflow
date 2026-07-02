# VibeFlow 分发开发包

这个目录是给“使用内核开发业务程序的人或 AI”看的分发材料。它不解释内核内部实现，只说明如何把程序拆成标准流程图 node、纯 `base_lib`、可选 plugin 和 JSONC 配置，并通过内核强制健康检查后运行。

推荐分发方式：

1. 复制本目录的 `docs/` 到新项目。
2. 复制仓库的 `src/vibeflow/` 到新项目的 `kernel/vibeflow/`。
3. 复制 `project_template/` 作为新项目骨架。
4. 在新项目里开发 `project/nodes/`、`project/base_lib/`、`project/plugins/` 和 `project/configs/*.jsonc`。
5. 用模板里的 `run.py` 启动检查、运行和图形导出。

复制后的推荐结构：

```text
my_project/
  docs/
  kernel/
    vibeflow/
  project/
    nodes/
    base_lib/
    plugins/
    configs/
    registry.py
  tools/
    mermaid-renderer/
  run.py
  runs/
  reports/
```

核心原则：业务开发者只写小型纯函数 node、纯 helper、必要插件和 JSONC 拓扑配置；控制流只写在显式 `pipeline.edges` 中；运行前由内核自动健康检查，检查不过不执行。运行时只审计流程和 key，node 间可按引用传递普通 Python 对象。

常用命令：

```powershell
python run.py validate --config project/configs/main.jsonc
python run.py run --config project/configs/main.jsonc --run-root runs
python run.py mermaid --config project/configs/main.jsonc --output reports/graph.mmd
python run.py ascii --config project/configs/main.jsonc --output reports/graph.txt
python run.py svg --config project/configs/main.jsonc --output reports/graph.svg
```

`svg` 命令依赖 `tools/mermaid-renderer/` 中的 Mermaid CLI。首次使用前运行：

```powershell
cd tools/mermaid-renderer
npm install
cd ../..
```
