# 项目模板

使用方法：

1. 把仓库的 `src/topology_kernel/` 复制到本项目的 `kernel/topology_kernel/`。
2. 把本目录内容复制到新项目根目录。
3. 在 `project/nodes/` 中开发业务 node。
4. 在 `project/registry.py` 中注册 node 和 boundary。
5. 在 `project/configs/main.jsonc` 中组织拓扑。
6. 运行：

```powershell
python run.py validate --config project/configs/main.jsonc
python run.py run --config project/configs/main.jsonc --run-root runs
python run.py mermaid --config project/configs/main.jsonc --output reports/graph.mmd
```

