# 人机协同开发协议

collaborative profile 适合需要人类在实现前审阅架构变化的任务。

1. 阅读已登记 Architecture 并定位真实 source。
2. 列出复用、修改、删除、新增四类变更清单。
3. 新能力优先以 planned Node 或 Nodeset进入真实 Config。
4. 运行 `review` 生成正式展开 SVG。
5. 等待人类在后续消息中明确批准。
6. 实现获批内容，更新 Architecture，并运行适用的 validate、quality、build 和工作流执行探针。

机器检查结论与人工批准分别报告。profile 协议不改变 Core、契约、副作用或质量规则。
