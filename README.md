# topology-kernel

面向纯函数节点的严格拓扑运行时原型，服务于人机协同开发，尤其是 LLM 深度参与编码和维护的场景。

本仓库目标是成为一个可迁移内核，可被 Paperflow 和其他项目复用。它有意保持严格：

- 每个 node 必须是纯函数。
- node 之间不能互相调用。
- 配置拥有全部拓扑组织权。
- 环路必须显式声明并具备执行上限。
- 大型行为应通过嵌套式 nodeset 组合。
- 副作用只能存在于框架级全局边界，不能进入 node。

更严格的目标是让架构和代码质量由内核自身强制执行，使 LLM 协助开发的大型项目始终由小型、可审计、低耦合的单元组成，而不是逐步滑向巨型函数、隐式依赖和补丁堆叠。

## 冒烟测试

```powershell
python -m pytest tests\unit
$env:PYTHONPATH='src'; python -m topology_kernel --help
```

## 文档

- `docs/kernel_target_vision.md`：目标设计和长期愿景。
- `docs/current_implementation_status.md`：当前已实现能力和缺口。
- `docs/strict_kernel_design.md`：从 Paperflow 迁移出的详细设计草案。

## 分发使用方式

面向实际使用者和 AI 开发者的分发文档在 `distribution/kernel_development_pack/`。

如果需要一个可直接复制到其他地方的新项目目录，运行：

```powershell
python build_distribution.py
```

脚本会在项目根目录生成 `topology_kernel_distribution/`，其中已经包含最新内核源码副本、中文开发文档、示例项目骨架和启动器。生成后可以直接复制整个 `topology_kernel_distribution/` 到其他目录开始开发。

任何新项目都可以只复制两部分开始使用：

1. 将 `distribution/kernel_development_pack/docs/` 复制到新项目的 `docs/`。
2. 将本仓库 `src/topology_kernel/` 复制到新项目的 `kernel/topology_kernel/`。

然后复制 `distribution/kernel_development_pack/project_template/` 作为项目骨架，按需新建或修改：

```text
project/
  nodes/
  base_lib/
  plugins/
  configs/
  registry.py
  boundaries.py
run.py
```

启动命令示例：

```powershell
python run.py validate --config project/configs/main.jsonc
python run.py run --config project/configs/main.jsonc --run-root runs
python run.py mermaid --config project/configs/main.jsonc --output reports/graph.mmd
python run.py quality --path project
```

原则上，使用者只开发 node、base_lib、plugin、boundary 和 JSONC config/nodeset；运行前内核会强制健康检查，检查失败则拒绝执行并输出原因。
