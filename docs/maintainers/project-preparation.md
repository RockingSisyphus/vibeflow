# 项目准备与资源事实

一次命令拥有一个 `ProjectPreparation`。它负责清单、声明发现缓存、workflow 资源准备及 project/root Rule 执行；不是运行时、全局缓存或第二套执行器。Core、BlockPlan、执行器与协同协议继续承担原职责，两种语言各自保留源码分析器。

完整审查识别 root 顶层、configs 和 architecture.documents 登记的 workflow。普通输入 JSON 不成为 workflow；显式登记的文件必须满足 workflow 格式，不能因含有 type_key 或架构文档标记而被跳过；声明了 pipeline 的损坏文件必须产生诊断，使项目架构的 inventory_complete 为 false。单 workflow 构建限定检查范围，不覆盖完整项目架构。

资源唯一性基于当前 root 与项目共享声明的完整可见集合，与本次是否调用该 Node 无关。NodeType 解析只针对当前 workflow 声明引用的 Node，不为未使用 Node 隐式加载其他 Plugin。冲突诊断保留两个声明来源及所有者；不同 root 的私有同名声明不互相冲突。

治理政策只在普通 Rule 中裁决。root.resources 检查私有资源、子图、实现附属文件和构建 include 的依赖；project.dependencies 检查项目共享代码反向依赖 root 私有代码。root.nodesets 检查跨 Target 子图；project/root.packages 检查 Plugin 包位置及业务 Node 分离，project/root.plugin_ownership 单独检查贡献及项目自有代码的实际归属；project.structure 检查 root 拓扑。显式参数、空选择和自定义规则接管有效，SDK/加载器/AOT 路径解析不得重复强制这些政策。格式、ABI、实际绑定和唯一标识仍是执行契约。

`resource_facts.py` 收集解析后的依赖和 Plugin 包事实，不作政策判定；共享 Rule 支持层不读取文件系统。项目包由项目规则检查，root 包由所属 root 规则检查。单 workflow 运行/构建仍执行项目规则，但通过 usage_complete 标识局部清单，默认共享数量检查只在完整项目审查时执行。

Python AOT 的 `tooling/application/python/build_inputs.py` 统一投影实际 Node、Plugin 声明/运行期工厂、声明依赖和源码闭包，本地文件与外部实现包收集共用该输入。可用集合中的未引用实现不会因此加载或打包，不再整目录复制 Python 源码。依赖资源声明的 implementation_files、包内数据和显式 include 继续保留，保留源码与附属文件的项目相对路径；部署产物不依赖原工作区，不在运行时扫描或编译。Bundle 固定描述和绑定索引与其生命周期一致，Runtime 保持自己的 Node、参数、Capability 和插件实例。暖调用与源码移除的回归分别由 aot_preparation 沙箱和 test_aot_deployment.py 验证。

项目架构复用准备事实记录资源的 used_by_workflows，关系为声明、依赖或整包选择，路径相对项目目录，statuses 表达 implemented/planned。它说明声明引用，不是实际执行轨迹。缺失占位不计作真实采用；Plugin 的内部实现不作为独立共享资源统计。used_by_roots 继续按不同 root 去重。

质量检查使用统一准备结果与规则引擎。显式规则列表替换默认，空列表取消该层可选检查；不保留旧 CLI 参数转换和独立扫描组装入口。纯测量、依赖算法和源码效果 Rule 仍可通过自己的事实接口测试。

长期验收入口见[开发与验证](development.md)。退役资料直接删除、版本压缩包不覆盖；目录与产物规则见[目录职责](directory-layout.md)。统一错误处理、取消和资源收尾仍按[待实施计划](../design/workflow-error-handling-plan.md)另行设计，现有浏览器包装层收尾在替代机制可用前保留。

政策覆盖与真实执行回归见 `tests/tooling/test_governance_policy_boundaries.py`；资源闭包见 `tests/tooling/test_project_dependency_scope.py`。

## 资源使用结果与调用链

`ProjectPreparation.resource_use(workflow_path)` 是资源使用结果接口。`resources/use_facts.py` 收集 workflow 原始选择、Catalog 归属及声明依赖，Core 的 `descriptors/source_members.py` 提供共用源码成员事实；Target 的 `project/resource_facts.py`（Python）和 `build/resource_facts.py`（JavaScript）各自解析实际引用。候选事实包含发现清单中的未调用 Node，但不为它们解析未使用的 NodeType 或加载实现。操作内沿用发现及语法缓存，不增加全局注册表。

`targets/shared/rule_support/resource_use/` 是资源政策的唯一判断入口：归属、可见性、独立引入、Plugin 整包引入、重复声明、声明及实际引用。默认 Rule 通过同层 `requires/bindings` 连接；消费者按输出 Record 类型识别结果，不识别内置 Rule ID。`resources/use.py` 负责结果汇合、冲突诊断及显式无约束解释，失败结果不能授权。

Core 的 `descriptors/resource_use.py` 保存可移植契约及无政策的依赖排序。Python `resource_bindings.py`、JavaScript `source_import_facts` 和构建绑定、Architecture 共同消费结果；它们不再读取原始 `base_lib.modules` 决定准入。源码编译 hook 改变图后，通过 `review_graph` 重走所选 Rule。Python 构建保存于 `python-workflow.json.resource_use`，JavaScript 构建保存于 `resource-use.json`；部署运行不重新执行源工程政策。

旧 Python 选择器、Node 源码归属许可检查、共享结构角色许可检查、JavaScript 驱动本地资源许可检查均已退役。语言解析、外部依赖检查、平台实现绑定和打包算法各自保留职责。不要在这些入口重新实现 workflow 显式选择规则。


## JavaScript 核心文件与业务检查清单

JavaScript Target 的 `resources/identity.py` 复用现有资源清单与本次实际目录确认核心文件身份，匹配规范化后的准确文件，不放行整个目录。源码安装和 ZIP 临时解压使用同一机制；身份在资源生命周期内确认，随分析结果保留，不由项目配置声明。

原始导入事实和插件加载证据保留核心引用。Target 在生成业务资源引用及源码成员清单时排除已确认的核心内部依赖；单次工具链、共享分析会话、插件加载及延迟实现复用这一入口。Core 与共享 Rule 不认识 SDK 文件名或解压路径。用户贡献资源的声明、实现和辅助文件仍独立接受原有归属检查，不因指向核心文件而获豁免。

## 架构文档与启动声明

`tooling/architecture` 消费本次 inventory、资源使用、规则与 Target 准备结果，统一组装两端的公共 workflow/Nodeset 文档和项目索引。project 索引 v2 仅列项目一级目录的完整相对路径和 root/root 容器标记，按 root 列出 workflow 文件名、路径、宏观用途、入口与 architecture.documents 映射；不递归展示普通子目录。发布后刷新文档存在状态复用本次事实，不重复分析。预览目录由保存的项目索引投影，不重新发现 workflow。

Call 的目标、入口和 launch 只在调用节点配置中维护；Kill 声明目标并使用实例 ID；收发可声明预期交互。`workflow_launches` 从准备图提取服务启动声明，构建将其保存为 workflow-launches.json；部署读取声明，不依赖源工程或 architecture 文档。
