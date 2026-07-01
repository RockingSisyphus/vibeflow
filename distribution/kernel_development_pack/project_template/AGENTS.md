# VibeFlow AI 开发指引

本目录是一个可复制的业务项目开发包，内置 `kernel/vibeflow/` 作为运行和校验内核。AI 默认应按本文开发业务程序。

## 硬性边界

- 不要修改 `kernel/vibeflow/` 下的内核源码。
- 不要修改 `kernel/`、`run.py` 或 `kernel/MANIFEST.sha256`；这些文件由分发包构建脚本生成和校验。
- 如果内核报错或警告，优先修改 `project/` 下的业务代码、registry 或 JSONC 配置来满足内核要求；不要 patch 内核来绕过检查。
- 如果完整性检查失败，不要通过修改 manifest 或 `run.py` 绕过；应从可信来源重新生成或恢复分发包。
- 业务代码只放在 `project/nodes/`、`project/base_lib/`、`project/plugins/` 和 `project/configs/`。
- `project/nodes/` 放业务 node；`project/base_lib/` 放可复用纯 helper；`project/plugins/` 放 policy/compiler/runtime 插件；`project/configs/` 放可运行 JSONC；`project/configs/nodesets/` 放可复用 nodeset JSONC。
- node 默认必须是纯函数：不要读写文件、网络、数据库、浏览器、环境变量或启动外部进程。
- 外部输入输出必须建模为 `io`、`data_store`、`document` 类型节点，或明确的 `external=True` 节点。
- 控制流只写在 JSONC 的 `pipeline.edges` 中；不要用 Python 调用关系隐式表达流程。
- `requires` / `provides` 只表达数据契约，不会自动生成控制流。
- 运行或交付前必须让内核健康检查通过；不要跳过 `python run.py validate ...`。

## 先读文档

- 开始设计或修改业务程序前，先读 `docs/10_Kernel能力与项目开发指南.md`。
- 编写 node 前，读 `docs/01_Node开发规范.md`。
- 注册 node 和配置默认值前，读 `docs/02_注册与配置默认值.md`。
- 修改 pipeline/config 前，读 `docs/03_Config与Pipeline规范.md`。
- 设计或细化 nodeset 前，读 `docs/04_Nodeset规范与用法.md`。
- 编写纯 helper 或处理外部依赖前，读 `docs/05_BaseLib与外部依赖规范.md`。
- 编写 plugin 前，读 `docs/06_Plugin开发规范.md`。
- 运行、导出报告或定位产物前，读 `docs/07_启动命令与报告.md`。
- 不确定约束时，读 `docs/08_给AI开发者的约束清单.md`。

## 推荐开发流程

1. 先把用户希望开发的程序抽象成一个粗粒度标准流程图，只保留几大块。
2. 用 planned nodeset 表达这些大块。例如初始流程是 `a -> b -> c`，就在顶层 config 中定义 `a`、`b`、`c` 三个 `status: "planned"` 的 nodeset，并在顶层 `pipeline.edges` 中连接 `a -> b -> c`。
3. planned node 必须声明 `flow_kind`；planned nodeset 可暂时不补齐内部 pipeline、契约和 exports。这样内核允许把数据传输细节和内部结构暂时留空，但会把它标为 planned，不能运行。
4. 生成流程图给人类审核：优先用 `python run.py mermaid --config project/configs/main.jsonc --output reports/graph.mmd`，需要图片时用 `python run.py svg --config project/configs/main.jsonc --output reports/graph.svg`。
5. 告知人类审核员查看 `reports/graph.mmd` 或 `reports/graph.svg`。不要在粗粒度架构未经确认时直接实现大量 node。
6. 人类审核通过后，再逐个细化 nodeset。比如把 planned nodeset `a` 细化为 `d -> e -> f`，可以先把 `d`、`e`、`f` 也标为 planned，再生成展开图继续审核。
7. 细化可以继续嵌套；任何尚未确定的节点或节点集都应保持 `status: "planned"`，用流程图先暴露结构。
8. 真正实现某个 node 时，必须创建对应 Python node，声明 `NODE_INFO`、`CONTRACT` 和 `run_pure(inputs, params)`，并在 `project/registry.py` 注册。
9. 真正实现某个 nodeset 时，必须补齐 metadata、`requires`、`provides`、`exports`、内部 `pipeline.nodes` 和 `pipeline.edges`，且移除该 nodeset 的 `status: "planned"`。
10. 只有当 nodeset 内部所有子 node / 子 nodeset 都已经 implemented，父 nodeset 才能变成 implemented。implemented nodeset 内含 planned child 会被内核报错。
11. 按同样方式实现后续 nodeset，直到顶层 `a`、`b`、`c` 全部 implemented，最终程序才能运行。
12. 后续修改架构也使用同一模式：先放 planned 占位并导出流程图给人类审核，再逐步实现。

## 常用命令

- 校验配置和健康检查：`python run.py validate --config project/configs/main.jsonc`
- 校验 kernel 完整性：`python run.py verify-kernel`
- 运行程序：`python run.py run --config project/configs/main.jsonc --run-root runs`
- 导出 Mermaid：`python run.py mermaid --config project/configs/main.jsonc --output reports/graph.mmd`
- 导出展开 nodeset 的 Mermaid：`python run.py mermaid --config project/configs/main.jsonc --expand-nodesets --output reports/graph.expanded.mmd`
- 导出 SVG：`python run.py svg --config project/configs/main.jsonc --output reports/graph.svg`
- 质量检查业务代码：`python run.py quality --path project`

## 判断标准

- 内核报错代表架构、配置、契约或实现不满足约束；修业务项目，不修内核。
- planned 内容用于设计审查，不可运行。
- implemented 内容必须完整、可达、可校验、可运行。
- 流程图是人类审核程序结构的主要产物；重大架构变更先出图再实现。
