# Collaborative profile

遵循[`人机协同开发协议`](kernel/docs/user/profiles/collaborative.md)：维护四类变更清单，以 planned 内容生成正式 HTML 审查快照，等待人类明确批准后实施获批变化。机器检查与人工批准分别报告。

沿已登记 Architecture 的 source，在现有工作流的实际位置表达 planned Node/Nodeset，并由 `review` 生成保留上下游关系的 HTML 审查快照，交付当次快照的 HTML 定位链接，请用户在浏览器中查看并按需展开调用，再等待明确批准。新增独立工作流时，按协同协议说明理由、调用关系和实际构建执行路径。BaseLib、Plugin 的变更使用真实资源与源码依赖表达；分别标明 planned、已实现和已运行状态。
