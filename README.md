# topology-kernel

面向标准流程图程序的严格拓扑运行时，服务于人机协同开发，尤其是 LLM 深度参与编码和维护的场景。

内核的目标不是让代码更自由，而是把程序约束成可审查、可运行、可视化的 flowchart：

- 每个 node 必须声明 `NodeInfo.flow_kind`，且必须是标准流程图节点类型。
- node 默认必须是纯函数，不能读写文件、网络、数据库、浏览器或环境变量。
- node 之间不能互相导入、调用或隐式依赖。
- 程序控制流只来自 JSONC config 中显式写出的 `pipeline.edges`。
- `requires` / `provides` 是数据契约，只用于运行时取值和健康诊断，不会被推导成控制流。
- 可执行图必须有 `terminal` start/end，所有已实现节点必须从 start 可达并能到达 end。
- 显式 cycle 必须经过 `decision` 节点；运行时用 `max_steps` 作为防死循环护栏。
- 副作用和外部系统通过 `io` / `data_store` / `document` 等节点建模；第三方或外部维护代码用 `NodeInfo.external=True` 标记。

## 标准 flow_kind

当前合法 `flow_kind`：

- `terminal`：开始 / 结束。
- `process`：普通处理。
- `decision`：判断 / 路由，输出 route-like key，分支 edge 必须写 `when`。
- `io`：输入 / 输出动作，不等同于 start/end。
- `predefined`：预定义过程 / nodeset。
- `data_store`：数据存储请求或引用。
- `document`：文档生成或文档结构。
- `preparation`：准备 / 初始化。

`external_dependency` 不是流程图类型。需要包装第三方库或外部维护代码时，使用对应的真实 `flow_kind`，并设置 `NodeInfo.external=True`。

## 冒烟测试

```powershell
python -m pytest tests\unit
$env:PYTHONPATH='src'; python -m topology_kernel --help
```

## 常用命令

```powershell
PYTHONPATH=src python -m topology_kernel validate --config examples/minimal_project/config.jsonc
PYTHONPATH=src python -m topology_kernel export-mermaid --config examples/minimal_project/config.jsonc --output reports/graph.mmd
PYTHONPATH=src python -m topology_kernel export-ascii --config examples/minimal_project/config.jsonc --output reports/graph.txt
PYTHONPATH=src python -m topology_kernel export-svg --config examples/minimal_project/config.jsonc --output reports/graph.svg
PYTHONPATH=src python -m topology_kernel quality-check --path .
```

`export-svg` 使用项目本地 `tools/mermaid-renderer/` 中的 Mermaid CLI。核心运行不依赖 SVG 渲染；渲染失败会被报告为图形产物问题，而不是改变拓扑语义。

首次使用 SVG 渲染前运行：

```powershell
cd tools/mermaid-renderer
npm install
cd ../..
```

## 文档

- `docs/kernel_target_vision.md`：当前目标愿景。
- `docs/current_implementation_status.md`：当前已实现能力。
- `docs/strict_kernel_design.md`：当前严格内核设计。
- `docs/developer_guide.md`：使用者开发指南。
- `docs/strict_flowchart_kernel_redesign.md`：本轮 flowchart redesign 的设计记录。
- `docs/explicit_flow_edges_plan.md`：显式 flow edge 方案记录。
- `docs/flowchart_node_semantics_correction_plan.md`：标准流程图语义修正记录。

## 分发使用方式

面向实际使用者和 AI 开发者的分发文档在 `distribution/kernel_development_pack/`。

如果需要生成一个可直接复制到其他地方的新项目目录，运行：

```powershell
python build_distribution.py
```

脚本会在项目根目录生成 `topology_kernel_distribution/`，其中包含最新内核源码副本、中文开发文档、示例项目骨架和启动器。

推荐项目结构：

```text
project/
  nodes/
  base_lib/
  plugins/
  configs/
  registry.py
run.py
```

启动命令示例：

```powershell
python run.py validate --config project/configs/main.jsonc
python run.py run --config project/configs/main.jsonc --run-root runs
python run.py mermaid --config project/configs/main.jsonc --output reports/graph.mmd
python run.py ascii --config project/configs/main.jsonc --output reports/graph.txt
python run.py svg --config project/configs/main.jsonc --output reports/graph.svg
python run.py quality --path project
```

分发包会携带 `tools/mermaid-renderer/package.json` 和 lockfile。首次使用 `python run.py svg ...` 前，在分发目录执行一次 `cd tools/mermaid-renderer && npm install`。

原则上，使用者只开发 node、base_lib、plugin 和 JSONC config/nodeset；运行前内核会强制健康检查，检查失败则拒绝执行并输出原因。
