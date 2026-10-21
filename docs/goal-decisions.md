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
- 项目资源可供所有 root 使用，root 私有资源仅供所属 root 使用。项目共享业务资源的使用情况需调查所有 root 中的现有 workflow，不能只依据当前选择的 workflow 或插件注册列表计数。
- 项目目录规范通过规则参数显式登记额外目录和用途；生成面向 AI 的项目架构说明，记录各目录和 root 的职责。
- HTML 资源画布保持资源边界：插件包一张卡片，不显示其内部 Node、compiler/runtime 或使用的 BaseLib；BaseLib 视图不自动加入消费者和所属插件。完整审查事实仍保存在快照。

状态（原型阶段的历史记录，已由方案 B 实施更新取代）：本次先完成独立的 HTML 资源投影调整；真实离线浏览器验证例子中 Plugin、BaseLib 各一张卡片，页面错误和网络请求均为空。相关模型和数据导出定向测试 2 项通过，不代表完整回归。

后续在首个多 root 原型、共享使用统计及发行模板迁移完成时复核：目录分离是否消除了归属歧义，默认审查成本是否可控，项目规则插件自身与跨 root 共享业务资源能否按明确职责检查。若需要改变已确认的目录隔离或资源可见范围，按 critical-fork 先说明实际证据，再请用户判断。

当前项目准备层、四级治理、类型分离及 Host 退役的实施与验收进展见[项目治理实施记录](maintainers/project-governance-refactor.md)。该记录逐批区分失败、定向通过和最终完整门禁；原型阶段数字不代表当前版本验收。
