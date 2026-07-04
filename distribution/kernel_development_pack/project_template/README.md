# 项目模板

使用方法：

1. 使用 `build_distribution.py` 生成包含 `kernel/vibeflow-kernel.zip` 的完整开发包。
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
python run.py svg --config project/configs/main.jsonc --expand-nodesets --output reports/graph.expanded.svg
```

`run` 会在 `runs/<run_id>/` 自动写出快速图 `graph.svg` 和详细审查图 `graph.expanded.svg`。`svg` 默认会为 Mermaid CLI 放大渲染上限：普通图使用 `maxTextSize=200000`、`maxEdges=2000`；`--expand-nodesets` 使用 `maxTextSize=500000`、`maxEdges=5000`，并固定采用 `review-columns` SVG composer，把主流程、plugins、base_lib 和展开 nodeset 分列展示。超大图可用 `--mermaid-max-text-size`、`--mermaid-max-edges` 和 `--review-fragment-max-width` 覆盖。

注意：`python run.py mermaid --expand-nodesets --output reports/graph.expanded.mmd` 只导出 Mermaid 源码，供调试源码使用。详细审查 SVG 必须用 `python run.py svg --expand-nodesets --output reports/graph.expanded.svg` 生成，不要把 `graph.expanded.mmd` 直接交给 Mermaid CLI/mmdc 转成 SVG，否则会绕过 VibeFlow 的 review-columns/detail-panel composer。

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
