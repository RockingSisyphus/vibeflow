# 项目模板

使用方法：

1. 把仓库的 `src/vibeflow/` 复制到本项目的 `kernel/vibeflow/`。
2. 把本目录内容复制到新项目根目录。
3. 在 `project/nodes/` 中开发业务 node。
4. 在 `project/registry.py` 中注册 node。
5. 在 `project/configs/main.jsonc` 中用显式 `pipeline.edges` 组织拓扑。
6. 运行：

```powershell
python run.py validate --config project/configs/main.jsonc
python run.py run --config project/configs/main.jsonc --run-root runs
python run.py mermaid --config project/configs/main.jsonc --output reports/graph.mmd
python run.py ascii --config project/configs/main.jsonc --output reports/graph.txt
python run.py svg --config project/configs/main.jsonc --output reports/graph.svg
```

如果要使用 `svg`，确保项目根目录存在 `tools/mermaid-renderer/`，并先执行：

```powershell
cd tools/mermaid-renderer
npm install
cd ../..
```

模板中的最小 flow 是：

```text
terminal start -> process seed -> process add -> terminal end
```
