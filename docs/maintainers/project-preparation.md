# 项目准备与资源事实

一次命令拥有一个 `ProjectPreparation`。它负责清单、声明发现缓存、workflow 资源准备及 project/root Rule 执行；不是运行时、全局缓存或第二套执行器。Core、BlockPlan、执行器与协同协议继续承担原职责，两种语言各自保留源码分析器。

完整审查识别 root 顶层、configs 和 architecture.documents 登记的 workflow。普通输入 JSON 不成为 workflow；显式登记的文件必须满足 workflow 格式，不能因含有 type_key 或架构文档标记而被跳过；声明了 pipeline 的损坏文件必须产生诊断，使项目架构的 inventory_complete 为 false。单 workflow 构建限定检查范围，不覆盖完整项目架构。

资源唯一性基于当前 root 与项目共享声明的完整可见集合，与本次是否调用该 Node 无关。NodeType 解析只针对当前 workflow 声明引用的 Node，不为未使用 Node 隐式加载其他 Plugin。冲突诊断保留两个声明来源及所有者；不同 root 的私有同名声明不互相冲突。

治理政策只在普通 Rule 中裁决。root.resources 检查私有资源、子图、实现附属文件和构建 include 的依赖；project.dependencies 检查项目共享代码反向依赖 root 私有代码。root.nodesets 检查跨 Target 子图；project/root.packages 检查 Plugin 包位置、贡献、支持代码及业务 Node 分离；project.structure 检查 root 拓扑。显式参数、空选择和自定义规则接管有效，SDK/加载器/AOT 路径解析不得重复强制这些政策。格式、ABI、实际绑定和唯一标识仍是执行契约。

`resource_facts.py` 收集解析后的依赖和 Plugin 包事实，不作政策判定；共享 Rule 支持层不读取文件系统。项目包由项目规则检查，root 包由所属 root 规则检查。单 workflow 运行/构建仍执行项目规则，但通过 usage_complete 标识局部清单，默认共享数量检查只在完整项目审查时执行。

Python AOT 使用已检查源码闭包收集获准依赖，同时收集依赖资源声明的 implementation_files，保留源码与附属文件的项目相对路径；部署产物不依赖原工作区，不在运行时扫描或编译。Bundle 固定描述和绑定索引与其生命周期一致，Runtime 保持自己的 Node、参数、Capability 和插件实例。暖调用与源码移除的回归分别由 aot_preparation 沙箱和 test_aot_deployment.py 验证。

项目架构复用准备事实记录资源的 used_by_workflows，关系为声明、依赖或整包选择，路径相对项目目录，statuses 表达 implemented/planned。它说明声明引用，不是实际执行轨迹。缺失占位不计作真实采用；Plugin 的内部实现不作为独立共享资源统计。used_by_roots 继续按不同 root 去重。

质量检查使用统一准备结果与规则引擎。显式规则列表替换默认，空列表取消该层可选检查；不保留旧 CLI 参数转换和独立扫描组装入口。纯测量、依赖算法和源码效果 Rule 仍可通过自己的事实接口测试。

长期验收入口见[开发与验证](development.md)。退役资料直接删除、版本压缩包不覆盖；目录与产物规则见[目录职责](directory-layout.md)。统一错误处理、取消和资源收尾仍按[待实施计划](../design/workflow-error-handling-plan.md)另行设计，现有浏览器包装层收尾在替代机制可用前保留。

政策覆盖与真实执行回归见 `tests/tooling/test_governance_policy_boundaries.py`；资源闭包见 `tests/tooling/test_project_dependency_scope.py`。
