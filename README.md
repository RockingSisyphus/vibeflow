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
