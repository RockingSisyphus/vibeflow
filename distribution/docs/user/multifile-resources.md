# 多文件资源与所有权

资源的目录位置决定所有者，显式引用决定依赖。项目共享资源位于项目的 `nodes/`、`base_lib/`、`plugins/`，私有资源位于所属 root 的同名目录；其他 root 的私有文件不能被借用。完整布局见[项目治理](project-governance.md)。

## 业务 Node 与 BaseLib

业务 Node 的 SDK 声明放在 `nodes/`，引用 NodeType，并声明自己的契约与实现。可以将实现拆成多个文件，通过 `implementation_files` 登记支持文件，路径相对声明模块。Node 使用独立 BaseLib 时通过 `base_libs` 引用；BaseLib 之间通过 `dependencies` 引用。不要把业务 Node 加进 Plugin 的资源列表。

同一个文件可以声明多个业务 Node；每个声明具有独立 `id`，workflow 调用以 `definition_id` 引用该业务定义。NodeType 只定义外观和默认规则，不承载业务实现。Node 可以替换类型默认规则，调用可以再替换 Node 的规则，显式 `[]` 取消该层可替换默认规则。project/root 治理分别执行。

独立共享 Node 和 BaseLib 必须被至少两个不同 root 的现存 workflow 实际引用。若只服务一个 root，请移入该 root，而不是增加虚假的资源引用。

## Plugin 包

每个 Plugin 在 `plugins/<package>/` 中维护入口、类型、规则、私有库和支持文件。入口使用 `Plugin` 或 `definePlugin` 将贡献作为一个整体导出。所有本地依赖都必须留在包内，标准库、第三方依赖及公开 SDK 除外。不能把 Plugin 的 Rule 放在 root 的其他目录，再单独加载。

Plugin 内部文件可以使用包内相对导入；需要登记的实现入口与支持文件仍明确声明。Plugin 的私有库不属于独立共享 BaseLib，不逐项要求跨 root 使用。Plugin 按整包采用情况统计；治理专用 Plugin 按治理用途判断。

workflow 显式选择 project 或本 root 的 Plugin。治理配置加载 Plugin 不会自动激活到业务 workflow。移除 Plugin 后，业务 Node 文件保留；若它引用该 Plugin 的类型，会得到缺失类型诊断。加载契约中的所有权、可见性和包边界不能通过关闭质量规则绕过。

## 生命周期与环境 API

compiler/runtime 扩展仍使用 Plugin 的相应生命周期声明。关键业务行为在 workflow 中由普通 Node 表达：例如打开监听、等待消息和关闭资源。宿主只注入 Capability API，不在 API 构造时自动启动业务监听；取消与错误路径也应走显式清理。Host Extension 和 `createWorkflowHost` 已删除。

浏览器或 Node.js 宿主直接调用生成模块的 `runWorkflow` 或 `runWorkflowAsync`，传入 Capability 及取消信号。跨程序启动、收发和实例身份见[workflow 协同](workflow-coordination.md)。

## 审查与交付

`review` 输出结构化快照及 HTML 定位链接，并更新已登记的 workflow 架构文档；完整项目审查另生成 `PROJECT_ARCHITECTURE.jsonc`。`review-rules --json` 查看有效规则与参数，`inspect-resources --json` 查看资源及所有者。HTML 的 Plugin 视图每包一张卡片，BaseLib 视图仅显示独立库及其依赖；完整事实保留在快照详情中。

SVG 仅作可选对照，通过 `review --with-svg` 或独立 `export-svg` 生成。HTML 自主绘图，支持节点可变形状、颜色、调用级覆盖和按调用展开，不依赖 SVG 片段。

AOT 包含实际执行所需代码，Rule 和 compiler 专用依赖留在检查与编译环境。当前格式不读取旧配置或旧 AOT；修改版本后重新构建，不使用兼容转换层。
