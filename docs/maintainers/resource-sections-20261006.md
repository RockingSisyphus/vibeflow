# 资源分区与 Nodeset 展示控制

**展示方案已撤销。** 下文保留当时实现与验收的历史记录；`Node types`、规则图、源码文件和跨区 reference 端点的 SVG 投影及 `--show-rules` 接入已删除。该方案把面向内核扩展开发的声明与分析资料放进了用户项目图，测试通过只证明当时的实现满足其错误的展示期待。当前 SVG 展示真实 Workflow 与配置所选资源目录，见[系统架构](../design/system-architecture.md#架构事实)和[使用文档](../user/multifile-resources.md#图形与-architecture)。Nodeset `expand` 的展示语义继续保留。历史机器报告及产物不覆盖为新结果。

正式审核的资源图使用统一 Architecture 投影，分为 Plugins、BaseLib、Host、Node types；`--show-rules` 将末区扩展为 Node types and rules。Python 与 JavaScript 消费同一分区模型，依次合成 SVG。分区内部保持 LR 方向，工作流、嵌套父流程和叶子流程沿用既有方向规则。

`implementation_graph` 的 resources、files、relations 保持完整。分区只选择主资源及其文件，跨区关系通过明确 reference 端点运输；它们不成为额外源码所有者或运行实例。分区图 ID 有独立命名空间，避免拼入一个 Mermaid 文档后合并同名节点。规则图读取已有有效计划，紧凑 `rule_graph` 引用 owner、phase、index；不复制整套有效计划，也不启动新的编译或审查。

Python 的 prepared 快照属于一次检查。默认正式图使用完整资料；显式 resources 子集或空字典控制本次图的主资源范围，不能由 prepared.resources 覆盖。图形开关不更改快照、资源契约、规则结果或源码归属。正式展示不绑定延迟 Node，不调用 Rule 或生命周期工厂。

Nodeset 的 `expand` 属于定义，默认 true，严格要求布尔值。配置解析、导入与有限图运输保留它；执行计划格式不增加这一展示字段。Mermaid、ASCII 和 SVG 在对应调用处停止递归，但保留调用框；所有定义仍参与编译与所选健康审查。Architecture 持续保存完整定义及 expand，包括图中隐藏的实现。Loop 与重复调用共用目标定义的设置。

回归入口：

- [Python 资源分区专项](../../sandbox/python/resource_sections/README.md)：14 个正式命令案例、健康负例、真实运行和三组浏览器产物。
- [JS/TS 资源分区专项](../../sandbox/javascript/resource_sections/README.md)：14 个正式命令案例、四类资源、AOT 数值执行与三组浏览器产物。
- [原布局回归](../../sandbox/python/review_layout/README.md)：保留四个案例 ID 与历史观察；新分区仅迁移当前区块和列数期待。
- Core 与 Target 测试覆盖严格字段校验、导入、Loop、原生三种执行模式、跨区归属、展示子集和 prepared 资料复用。

以上两组专项进入完整验证门禁；维护者使用手册中的展示开关和源码路径定位产物，历史发行包的结果不代替本轮源码验收。

当前期待迁移有两处：原四个布局案例从单一资源区的 8 个分片、3 列变为 10 个分片、5 列，原 ID 与历史报告不变；严格 Architecture 集成测试接受新增紧凑 `rule_graph`，并逐项核对其索引指向已有有效计划。健康诊断、执行协议和参数阈值的期待没有放宽。

最终验收：完整 pytest **2038/2038**、双语言正式案例 **28/28**、原布局 **4/4**、性能案例 **57/57**、独立质量测试 **46/46**。仓库质检 0 错误、0 警告；代表性 SVG 已在真实浏览器检查并目视核对。源码指纹、原始失败与最终日志见[机器记录](resource-sections-verification-20261006.json)。本轮更新源码、手册及提示词源文件，没有重建现有发布压缩包。
