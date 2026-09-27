# Collaborative profile

遵循[`人机协同开发协议`](kernel/docs/user/profiles/collaborative.md)：维护四类变更清单，以 planned 内容生成正式审核图，等待人类明确批准后实施获批变化。机器检查与人工批准分别报告。

正式审核必须沿已登记 Architecture 的 source，在现有真实工作流的实际位置表达 planned Node/Nodeset，并由 `review` 生成完整展开图。不得用局部、概念性或脱离真实生产调用的独立 Config 替代原位审核，也不得以“以后接入生产”或机器 PASS 代替真实接入依据。确需新增独立工作流时，按协同协议说明理由、调用关系及实际构建执行路径。登记库和扩展按真实依赖表达，不为画图虚构 Node 或入口；planned 不等于已实现、已运行。
