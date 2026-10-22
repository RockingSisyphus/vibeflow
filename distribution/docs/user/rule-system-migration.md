# 当前配置与接口迁移

当前公开契约为 Workflow ABI v10、Plugin ABI v4、Rule ABI v3、AOT v4，预览快照 v4。旧源码按以下职责重新组织，旧 AOT 必须重新构建；不提供自动转换、兼容别名或双执行路径。

| 旧机制 | 当前方式 |
| --- | --- |
| 无项目、单层 root 或 root path 为点目录 | 项目注册至少一个独立子目录 root |
| 项目 policy、quality_enabled、quality_structure | project_rules.jsonc 与 root_rules.jsonc 中选择 Rule/Ruleset 和参数 |
| Plugin 导出业务 Node | Plugin 导出 NodeType；业务 Node 从 nodes/ 发现，使用 id 和 node_type |
| workflow Node 的 type_used | definition_id 引用业务 Node；调用具有自己的 id 和完整路径 |
| Nodeset 定义与调用混用 | NodesetType 是可复用子图，Nodeset 是一次调用 |
| Plugin 实现分散在 root 各目录 | 所有贡献及其支持代码放在 plugins/包名/ 内，整包选择或移除 |
| 跨 root 引用私有实现 | 提取为项目共享 Node、BaseLib 或 Plugin，并满足共享用途规则 |
| Host Extension、createWorkflowHost | 普通 Node 显式执行打开、接收、关闭；宿主注入 Capability API |
| 原生 io 字段及专属执行路径 | 普通 SDK Node，通过授权的 vibeflow.port Capability 收发 |
| SVG 作为主审核材料 | review 结构化快照与 HTML 定位链接；SVG 为可选附件 |

## 迁移顺序

先建立项目和独立 root，登记 root 的用途、Target 与工具链。把资源分到对应所有者的标准目录，Plugin 内部保持完整，再更新业务 Node 的类型引用与 workflow 的 definition_id。项目共享独立 Node/BaseLib 按真实 workflow 引用统计，不能为了规避检查复制假引用。

将旧质量配置拆入两级治理文件。project/root Rule 使用真正对应的信息视图；graph/node Rule 保留各自检查对象。缺失选择使用默认值，显式列表替换本层默认，[] 仅取消本层可选规则。所有权、可见性与 Plugin 包边界属于加载契约，不受可选规则开关影响。

将宿主关键生命周期画进 workflow，覆盖正常、错误及取消的清理路径。环境 API 的构造不隐式启动业务监听。跨进程生命周期与收发使用 workflow 协同接口，作者负责后台实例清理。

完成源码检查后重新 build。AOT 执行只使用准备好的执行计划与授权结果，不扫描项目、不审图、不生成预览。

## 规则与数据契约

Rule 声明 level 为 project/root/graph/node，scope 仍表示既有调用或源码资料范围，两者不能互相代替。RuleImplementationDescriptor 指定 language 与 source。RuleResult 的 state 必须是 completed/failed/unavailable；finding 的 severity 为 error/warning/info。有效 error finding 不取消有效 records，损坏的结果使依赖它的 consumer 不执行。

JS records 必须是真实 JSON 数据；Map、Date、undefined、非有限数及循环对象不属于合法结果。Python/JS 公共上下文只读，同次检查复用 Target 源码事实。类型检查和业务测试仍由项目自己的工具完成。

所有 pipeline、NodesetType、Loop 及 SDK 契约输入明确声明布尔 required。运行时拒绝未声明键、检查必需键，null 仍表示该键存在。节点输出与路由继续由声明、编译和运行时共同检查，不做业务返回值的静态证明。

详细配置见[项目治理](project-governance.md)、[规则与 Node](rules-and-nodes.md)、[插件](plugins-and-integrations.md)及[workflow 协同](workflow-coordination.md)。
