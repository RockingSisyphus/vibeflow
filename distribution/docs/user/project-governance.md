# 项目、root 与资源归属

一个项目由 `vibeflow_config.jsonc` 标识，必须至少登记一个独立子目录 root。root 的 `vibeflow_project.jsonc` 声明 Target、工具链、运行环境和架构文档登记。项目目录不能同时充当 root，root 之间不能嵌套或重叠。

```text
workspace/
  vibeflow_config.jsonc
  project_rules.jsonc
  PROJECT_ARCHITECTURE.jsonc       # 完整审查生成
  nodes/                          # 多个 root 实际共用的业务 Node
  base_lib/                       # 多个 root 实际共用的独立 BaseLib
  plugins/                        # 项目共享或项目治理 Plugin 包
    conventions/
      plugin.py
      rules/
  desktop/
    vibeflow_project.jsonc
    root_rules.jsonc
    nodes/
    base_lib/
    plugins/
    configs/
      main.jsonc
      nodeset_types/
  backend/
    vibeflow_project.jsonc
    nodes/
    base_lib/
    plugins/
    configs/
```

项目配置示例：

```jsonc
{
  "purpose": "桌面界面与后台计算协同",
  "roots": [
    {"id": "desktop", "path": "desktop", "purpose": "交互与输入", "config": "vibeflow_project.jsonc"},
    {"id": "backend", "path": "backend", "purpose": "数据计算"}
  ]
}
```

root ID 的 `@` 前缀保留给项目作用域引用。共享资源的文档路径以 `@project/` 表示；其他 root 的文档引用使用 `@<root-id>/`。这类路径用于说明来源，不是 Python 或 JavaScript 的导入语法。

## 类型、业务声明与调用

- **NodeType** 声明外观和默认局部 Rule/Ruleset。Plugin 通过 Python `node_type(...)` 或 JavaScript `defineNodeType(...)` 贡献它。
- **Node** 在 `nodes/` 中通过普通 SDK 声明，使用 `id` 标识业务定义，`node_type` 引用 NodeType，声明契约、参数及实现。
- **调用** 在 workflow 中使用 `id` 标识调用点、`definition_id` 引用业务 Node。同一业务 Node 可被多次调用，每次参数、样式和授权分别处理。
- **NodesetType** 是一个 JSONC 文件中的可复用子图与契约，使用 `type_key` 标识。通过 `nodeset_imports` 导入所属 root 的定义。**Nodeset** 是图中对它的一次调用，不另建业务实例文件。

局部规则的选择顺序是 NodeType 默认、Node 显式替换、调用显式替换。省略表示继承；显式 `[]` 取消该层可替换规则。所属图、root 和项目的规则分别执行，不受这个列表影响。形状、颜色或名字不授予框架功能；Capability 与有效 Rule 授权决定可用接口。

## Plugin 必须是完整的包

文件 Plugin 放在 `plugins/<包名>/` 下，入口及其贡献的 NodeType、Rule、Ruleset、私有库、生命周期实现和支持代码均在包内。Python 使用包内相对导入，JavaScript 使用相对模块引用。标准库、第三方依赖及公开 SDK 无需复制进包。

业务 Node 只引用 Plugin 的类型 ID，不属于 Plugin。移除 Plugin 选择会移除它的全部贡献；业务文件保留，并报告所需 NodeType 缺失。不能单独选择 Plugin 内部贡献，也不能借用另一个 root 的私有文件来拼装包。

workflow 通过 `plugins` 显式选择资源：

```jsonc
{
  "plugins": [
    {"scope": "root", "source": {"kind": "file", "ref": "plugins/layout/plugin.py"}},
    {"scope": "project", "source": {"kind": "file", "ref": "plugins/common/plugin.py"}}
  ]
}
```

省略 `scope` 时为当前 root；项目治理配置中的默认作用域为项目。治理配置加载的 Plugin 不会自动激活到 workflow。root 私有资源只在本 root 可见，跨 root 的独立程序调用应使用 workflow 协同接口。

项目共享的独立 Node/BaseLib 由默认规则检查是否至少被两个不同 root 的现存 workflow 实际引用；Plugin 按整包采用情况统计，包内资源不单独计算。专门提供项目/root 治理规则的 Plugin 按其治理用途判断。planned 调用对真实资源的引用可计入；没有真实资源的占位不计入。任何损坏的 workflow 都会明确报告分析不完整。

## 四级规则

Rule 的 `level` 为 `project`、`root`、`graph` 或 `node`。这与 `scope: call/source` 的结果复用范围不同。等级决定检查对象和可读信息：项目规则读取项目清单、root、workflow 声明与资源关系；root 规则只读取所属 root 的文件清单、workflow 和资源事实；graph/node 保持各自图和调用上下文。不能把 project Rule 选入 Node 后取得项目事实。

`project_rules.jsonc` 与 `root_rules.jsonc` 使用相同选择结构：

```jsonc
{
  "plugins": [],
  "rulesets": ["vibeflow.project.default"],
  "rule_params": {
    "vibeflow.project.layout": {
      "directories": [{"path": "exports", "purpose": "人工导出的交付文件"}]
    }
  }
}
```

root 对应默认集合为 `vibeflow.root.default`。没有配置文件或省略 `rulesets` 时使用本层默认；显式列表替换默认，`[]` 只取消本层可选检查。`rule_params` 按 Rule ID 配置参数；单次 Rule 选择仍可携带自己的参数。自定义 Rule/Ruleset 与普通规则一样由 Plugin 贡献。

默认项目规则检查目录用途及共享使用情况；默认 root 规则检查目录用途、资源位置及源码文件、依赖、结构和重复。额外目录应在对应 layout Rule 的 `directories` 中说明用途。Plugin 包边界、资源可见性和声明冲突属于加载契约，关闭可选检查也不能绕过。

完整 `review` 和项目 `quality-check` 检查项目与所有 root，并更新 `PROJECT_ARCHITECTURE.jsonc`。构建与 Python 源码运行只检查所属 root、当前 workflow 及使用的资源，局部操作不会把项目架构文档覆盖成残缺版本。AOT 执行不扫描项目、不审图、不生成报告。

## 架构与预览

`PROJECT_ARCHITECTURE.jsonc` 说明目录用途、root 职责、workflow 和资源关系；登记的单 workflow Architecture 文档继续分别生成和检查。

HTML 的 Plugin 视图每包一张卡片，BaseLib 视图显示独立库及库间依赖，不展示 Plugin 私有实现邻居。快照详情保留完整来源事实，区分 NodeType、业务 Node 和调用。流程、历史、planned、展开、搜索及跨 workflow 查看保持原有用途。默认审查交付快照与 HTML；SVG 是显式请求的对照附件。

## 本次迁移

旧项目需拆出独立 root；旧质量配置移入两级治理文件，删除 `policy`、`quality_enabled`、`quality_structure` 等旧字段。将业务 Node 移到 `nodes/`，Plugin 改为贡献 NodeType，并把 Plugin 自身代码放回包内。

Host Extension 已退役。宿主只提供 API；监听建立、接收及关闭由普通 workflow Node 显式调用，通过 Capability 与规则授权。独立程序之间使用 workflow 协同协议。compiler/runtime Plugin 仍用于其各自的框架扩展，不替代图中的关键业务生命周期。

本版本一次切换配置、快照及 ABI，不读取旧格式，也不提供转换或兼容执行路径。旧 AOT 必须重新构建，旧预览重新生成；业务输出、运行日志、trace 与发布归档不属于预览清理范围。
