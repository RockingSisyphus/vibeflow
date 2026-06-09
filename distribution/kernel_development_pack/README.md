# Topology Kernel 分发开发包

这个目录是给“使用内核开发业务程序的人或 AI”看的分发材料。它不解释内核内部实现，只说明如何把程序拆成 node、base_lib、plugin、boundary 和 JSONC 配置，并通过内核强制健康检查后运行。

推荐分发方式：

1. 复制本目录的 `docs/` 到新项目。
2. 复制仓库的 `src/topology_kernel/` 到新项目的 `kernel/topology_kernel/`。
3. 复制 `project_template/` 作为新项目骨架。
4. 在新项目里开发 `project/nodes/`、`project/base_lib/`、`project/plugins/`、`project/boundaries.py` 和 `project/configs/*.jsonc`。
5. 用模板里的 `run.py` 启动检查、运行和 Mermaid 导出。

复制后的推荐结构：

```text
my_project/
  docs/
  kernel/
    topology_kernel/
  project/
    nodes/
    base_lib/
    plugins/
    configs/
    registry.py
    boundaries.py
  run.py
  runs/
  reports/
```

核心原则：业务开发者只写小型纯函数 node、纯 helper、必要插件和 JSONC 拓扑配置；运行前由内核自动健康检查，检查不过不执行。

