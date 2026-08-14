# 无人值守开发协议

autonomous profile 适合在任务授权和运行环境允许的范围内自动完成开发闭环。

1. 阅读已登记 Architecture 并定位真实 source。
2. 根据任务选择 Python Runtime 或 JavaScript AOT root。
3. 直接实现所需变更并更新 Architecture。
4. 运行适用的 validate、quality 和 build。
5. 对每个可运行的已修改项目执行工作流执行探针。
6. 按命令的 `checked`、`not_checked` 和运行证据报告结果。

外部副作用 workflow 仍服从任务授权和环境限制。profile 协议不改变 Core、契约、副作用或质量规则。
