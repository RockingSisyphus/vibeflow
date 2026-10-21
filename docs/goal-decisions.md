# 项目结构与规则范围决定

## 项目容器与 root 分离（2026-10-21）

目标：为整个 VibeFlow 项目和单个 root 提供独立规则范围，同时明确项目共享资源与 root 私有资源的目录归属。

现有部分项目将 root 登记为 `path: "."`，与工作区共用目录。新增项目级 `nodes/`、`base_lib/` 和 `plugins/` 后，同一路径无法同时表达项目共享和 root 私有这两种目录职责。

讨论过保留同目录并增加归属声明，以及将项目容器与 root 分目录两条路线。用户明确选择后者：不允许单层项目；必须显式登记至少一个位于独立子目录中的 root。不保留通过同目录声明来区分两种归属的兼容路径。只有一个 root 的项目仍然合法。

预期目录形态：

```text
project/
  vibeflow_config.jsonc
  project_rules.jsonc
  PROJECT_ARCHITECTURE.jsonc
  nodes/                    # 可选：跨 root 共享节点
  base_lib/                 # 可选：跨 root 共享库
  plugins/                  # 可选：项目规则及共享插件
  app/                      # 显式登记的 root
    vibeflow_project.jsonc
    root_rules.jsonc
    configs/
    nodes/                  # app 私有业务节点
    base_lib/
    plugins/
```

验收依据：项目自身不能成为 root；现有同目录例子和发行模板迁移到 root 子目录；旧布局给出具体迁移诊断；工作流逻辑不因文件归位改变。是否允许项目外 root、嵌套 root 等其他路径关系，应在加载边界设计时核对，不从这项决定推导未经讨论的额外限制。

相关已确认需求：

- `project_rules.jsonc`、`root_rules.jsonc` 分别控制项目及 root 的 Rule/Ruleset 选择和参数，沿用显式选择覆盖默认的语义；旧的对应质量配置及执行路径应迁移、删除。
- 项目资源可供所有 root 使用；root 私有资源默认仅供所属 root 使用，相关 project/root 隔离规则允许用户通过显式配置绕过（见下方后续决定）。项目共享业务资源的使用情况需调查所有 root 中的现有 workflow，不能只依据当前选择的 workflow 或插件注册列表计数。
- 项目目录规范通过规则参数显式登记额外目录和用途；生成面向 AI 的项目架构说明，记录各目录和 root 的职责。
- HTML 资源画布保持资源边界：插件包一张卡片，不显示其内部 Node、compiler/runtime 或使用的 BaseLib；BaseLib 视图不自动加入消费者和所属插件。完整审查事实仍保存在快照。

当前准备层职责与回归入口见[项目准备](maintainers/project-preparation.md)。

## 审核后的范围与清理决定（2026-10-21）

用户明确确认以下要求，后续清理按本节解释此前方案与审核结论：

- 跨 root 资源隔离等 project/root 规则本就允许用户显式配置绕过。显式放开后的跨 root 使用不是缺陷，不能以不可关闭的加载限制恢复同等禁止；默认检查与显式覆盖都需验收。该决定不等于取消所有格式、ABI 和标识唯一性约束。
- Python 源码可运行而对应 AOT 缺失获准依赖，属于独立的打包一致性问题，应修正依赖收集，不通过禁止用户已允许的访问解决。
- 项目尚未统一设计报错处理。浏览器异常/取消后的收尾归入[未来异常处理计划](design/workflow-error-handling-plan.md)，不作为本轮改造漏项；在新机制能够承担职责前，不删除现有实际有效的宿主收尾。
- 退役文档和代码直接删除，唯一允许归档的是带版本标识的压缩分发包。仍有效的知识先合并至当前权威文档，再删除旧文件与引用；不再建立或迁入历史文档目录，也不将旧文档压缩来规避删除要求。

技术债清理将这些约束落实到[项目准备规范](maintainers/project-preparation.md)、[目录职责](maintainers/directory-layout.md)与当前行为回归。正式发行身份仍按[发行规范](maintainers/release.md)另行处理，本轮不授权发布。未来异常处理计划保持待实施状态。

## 治理限制统一进入标准 Rule（2026-10-21）

用户进一步明确：逻辑统一、维护便利与有序优先；即使取消 Plugin 整包约束或跨 Target 子图限制会偏离默认能力要求，也应把可表达为治理政策的限制移入既有 project/root Rule 体系。本节将此前“完整 Plugin 包始终由加载契约强制”的表述改为默认规则，不取消默认目录规范。

准备层解析与绑定资源，提供只读路径、所有者、导入、包贡献及依赖事实。默认 Rule 保持原有治理要求；显式选择和参数覆盖有效，加载器、SDK、AOT 路径解析不得再硬编码同等禁止。项目共享代码的反向依赖由 project.dependencies 负责，root.resources 负责私有资源边界；跨 Target 子图与 Plugin 包政策分别由 root.nodesets 和 project/root.packages 负责。项目拓扑由 project.structure 负责。

关闭政策不创造新的执行器或跨语言转换能力。实际文件缺失、格式错误、资源 ID 冲突、缺失 NodeType、ABI/绑定不兼容仍按真实错误报告。子图是声明，放行后使用消费方 Target 和资源集合；不会隐式激活另一 root 的全部资源。单工作流运行/构建也执行项目治理，完整共享使用数量仅在全项目清单上评估。

验收以默认拒绝、参数放行、空选择、自定义 Plugin Rule 接管及实际源码/AOT 执行为依据。既有 1.3.0 压缩包不在本次源码修改中覆盖。
