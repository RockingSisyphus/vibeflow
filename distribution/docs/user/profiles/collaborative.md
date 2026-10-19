# 人机协同开发协议

collaborative profile 适合需要人类在实现前审阅架构变化的任务。

1. 阅读已登记 Architecture 并定位真实 source。
2. 列出复用、修改、删除、新增四类变更清单。
3. 修改现有流程时，在其真实 Config 的实际位置标记或新增 planned Node、Nodeset，保留原流程上下游。
4. 对受影响的完整工作流运行 `review`，生成正式 HTML 预览与结构化快照。
5. 等待人类在后续消息中明确批准。
6. 实现获批内容，更新 Architecture，并运行适用的 validate、quality、build 和工作流执行探针。

机器检查结论与人工批准分别报告。此 profile 使用与 autonomous 相同的 Core、原生契约和所选 Ruleset。

## 正式审核图与真实流程

正式材料围绕实际构建和执行的 Config 组织，提供以下内容：

- 由 `review` 生成的 HTML 预览、结构化快照及对应的 Architecture JSONC；在流程视图按需展开受影响调用，资源视图核对依赖。需要静态对照时使用 `review --with-svg` 或显式 `--output FILE.svg`，SVG 不作为默认必需材料。
- 既有工作流的真实入口、Nodeset、变更调用点和未修改部分。跨多个工作流时，分别提供各自完整图。
- planned 变化的输入输出、控制流、资源依赖和预期实现位置，并分别标明规划、实现和执行状态。
- 新增独立工作流的用途、现有流程难以承载的原因、真实调用方、接入关系及构建执行路径。既有环节的变化仍在原流程位置审核。
- BaseLib、Plugin 或 Host 的真实声明与源码依赖。多文件入口和支撑文件通过 HTML 资源视图及 JSONC 来源定位。
- 当次 `review` / `validate` 结果与生产调用依据；实现后的执行探针和业务验收分别记录。

人类依据这些材料作出明确批准，再进入获批内容的实现。
