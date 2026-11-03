# 项目、root 与资源归属

一个项目由 `vibeflow_config.jsonc` 标识，至少登记一个 root；默认 `vibeflow.project.structure` 要求 root 位于独立子目录。root 的 `vibeflow_project.jsonc` 声明 Target、工具链和运行环境。默认规则要求项目目录与 root 分离，root 之间不能嵌套或重叠；这些拓扑政策可由项目规则替换。

```text
workspace/
  vibeflow_config.jsonc
  project_rules.jsonc
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

## root 注册与改名

`vibeflow_config.jsonc` 的 `roots` 是实际 root 注册来源。`id` 是逻辑身份，`path` 是目录位置，两者不必同名。发行模板中的 `python_project`、`javascript_project` 及其 ID 都是示例，没有必须保留的名称或语言组合。

只改目录名时，移动目录并更新注册项的 `path`，再同步业务脚本和配置中的实际路径。改 root ID 时，更新注册项的 `id` 以及跨 workflow 引用中的 `root`。已有架构文档记录了 root 身份，应通过正常命令重新生成，例如：

```bash
python run.py architecture --config worker/configs/main.jsonc --output worker/ARCHITECTURE.jsonc
```

命令中的 `worker` 替换为实际 root 路径；按该 root 的 `architecture.documents` 登记更新受影响的 workflow。项目总览可用 `python run.py preview --workspace vibeflow_config.jsonc` 更新。

## 发行身份记录

`DISTRIBUTION.json` 是构建器生成的只读发行记录，仅包含：

| 字段 | 含义 |
| --- | --- |
| `schema` | 该记录自身的格式标识 `vibeflow.distribution.v3` |
| `version` | 原始分发包的发行版本 |
| `development_profile` | 原始分发包的类型：collaborative 或 autonomous |

这些信息供版本识别和发行维护使用，不注册 root，也不决定当前业务项目的 Target、资源、开发协议或自动化行为。业务开发规范由项目 `AGENTS.md` 及其引用的文档说明。

业务改名、增删 root 和调整配置均无需修改发行记录或重封 `kernel/MANIFEST.sha256`。启动器每次运行都会检查受保护发行文件；如果校验失败，应按报错中的 Changed / Missing 文件定位实际改动。root 注册配置、业务目录和业务架构文档不在内核清单的保护范围内。

## Plugin 的默认整包规则

默认 `vibeflow.project.packages` / `vibeflow.root.packages` 要求文件 Plugin 放在 `plugins/<包名>/` 下。独立的 `vibeflow.project.plugin_ownership` / `vibeflow.root.plugin_ownership` 检查入口、贡献声明、实现、支持文件和导入的项目自有代码均在该包内；检查使用规范化后的实际路径，因此相对路径和符号链接不会绕过归属。Python 使用包内相对导入，JavaScript 使用相对模块引用。标准库、第三方依赖及公开 SDK 无需复制进包。

默认规则要求业务 Node 只引用 Plugin 的类型 ID，不加入 Plugin。关闭或替换 packages 规则后，Plugin 可以贡献业务 Node，并应用相同的 NodeType 解析。移除 Plugin 选择会移除它的全部贡献；业务文件保留，并报告所需 NodeType 缺失。不能单独选择 Plugin 内部贡献，也不能借用另一个 root 的私有文件来拼装包。

workflow 通过 `plugins` 显式选择资源：

```jsonc
{
  "plugins": [
    {"scope": "root", "source": {"kind": "file", "ref": "plugins/layout/plugin.py"}},
    {"scope": "project", "source": {"kind": "file", "ref": "plugins/common/plugin.py"}}
  ]
}
```

省略 `scope` 时为当前 root；项目治理配置中的默认作用域为项目。治理配置加载的 Plugin 不会自动激活到 workflow。root 私有声明只进入所属 root 的绑定集合；默认 root.resources 拒绝导入其他 root 的私有源码，默认 project.dependencies 禁止项目共享目录（`nodes`、`base_lib`、`plugins`）反向依赖任何 root 的私有代码。因此 `app → 共享库 → backend 私有库` 同样会被报告。跨 root 的独立程序调用使用 workflow 协同接口。

需要有意共享源码时，可以在 root_rules.jsonc 的 `rule_params` 中设置 `"vibeflow.root.resources": {"allow_cross_root_imports": true}`，也可以显式替换本层规则选择。该设置放开该 root 的源码、Nodeset、实现附属文件和 `--include` 跨 root 依赖。共享目录的反向依赖单独在 project_rules.jsonc 中配置 `"vibeflow.project.dependencies": {"allow_cross_root_imports": true}`。跨 Target 子图和 Plugin 私有子图仍分别受 root.nodesets、root.packages 规则控制；需要时显式替换对应规则选择。获准导入的源码依赖进入 AOT 构建闭包；Python 还携带这些依赖资源声明的 `implementation_files`，产物可脱离原项目运行。这不会把其他 root 的全部声明自动激活到当前 workflow，也不替代资源引用 Rule：引用代码仍须属于已声明的资源或 `implementation_files`，或由自定义引用 Rule 明确允许。

项目共享的独立 Node/BaseLib 由默认规则检查是否至少被两个不同 root 的现存 workflow 实际引用；Plugin 按整包采用情况统计，包内资源不单独计算。专门提供项目/root 治理规则的 Plugin 按其治理用途判断。planned 调用对真实资源的引用可计入；没有真实资源的占位不计入。任何损坏的 workflow 都会明确报告分析不完整。

## workflow 的资源使用

独立 BaseLib 必须在 workflow 的 `base_lib.modules` 中显式声明；当前 root 和项目共享库采用相同写法。省略 `base_lib`、`{}` 或 `{"modules":[]}` 都不会启用独立库。假设 Node 声明依赖 `d`，而 `d` 又声明依赖 `e`，workflow 必须同时列出两者：

```jsonc
{"base_lib":{"modules":["d","e"]}}
```

Node 的 `base_libs` 与 BaseLib 的 `dependencies` 描述源码资源关系；workflow 的选择决定本次是否允许使用。配置和实际源码引用都会检查。一个 workflow 的声明不会授权另一个 workflow。

选择 Plugin `a` 后，它贡献的资源整体可用。若 `f` 属于 `a`，只在 `plugins` 中选择 `a`，不能再把 `f` 填入 `base_lib.modules`。独立引入规则、Plugin 整包引入规则和重复声明规则分别负责这些判断。禁用或 planned 的 Plugin 不提供实现。可用集合不会自动执行 Node，也不会强制为不使用的平台加载所有实现。

默认 root Ruleset 包含 `resource_visibility`、`resource_independent`、`resource_plugins`、`resource_duplicates`、`resource_use` 和 `resource_references` 六个调用（Rule ID 均带 `vibeflow.root.` 前缀）。前三者提供集合，`resource_use` 显式组合成 `vibeflow.resource_use.v1` Record，引用规则只检查该结果及资源关系。替换 `resource_independent` 的输出即可改变独立库引入方式，无须修改 Python、JavaScript、AOT 或展示代码。

自定义 Ruleset 可包含 `RuleCall("defaults", ruleset_id="vibeflow.root.default")`，再通过 `RuleRelation("$self", "defaults/resource_independent", "overrides", replace_rule="your.rule")` 替换引入规则。替代 Rule 的输出端口 `resources` 类型必须为 `vibeflow.resource_set.v1`，值为 `{"workflows": {"root-id:configs/main.jsonc": [{"kind":"base_lib","id":"d","reason":"custom"}]}}`。

显式取消相关规则后，资源使用结果记录为无约束。规则执行失败、依赖不可用、输出损坏或最终 Record 冲突时，检查报告对应错误。

## project/root 规则配置

项目治理读取项目清单、root、workflow 声明与共享关系；root 治理读取所属 root 的目录、workflow 和资源事实。

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

默认项目规则检查目录用途及共享使用情况；默认 root 规则检查目录用途、资源位置、跨 root 导入及源码文件、依赖、结构和重复。额外目录应在对应 layout Rule 的 `directories` 中说明用途。格式、ABI、声明标识冲突不会随可选规则关闭而取消；未调用 Node 的重复 ID 也会报告，未调用 Node 的类型则不强制激活其 Plugin。

## 治理政策与加载错误

| Rule | 默认职责 |
| --- | --- |
| `vibeflow.project.structure` | root 为独立项目子目录、不重叠、配置位于所属 root |
| `vibeflow.project.dependencies` | 共享代码不能反向依赖 root 私有代码 |
| `vibeflow.project.packages` / `vibeflow.root.packages` | Plugin 目录、贡献及支持文件的包归属、业务 Node 分离；root 规则还检查 Plugin 私有子图 |
| `vibeflow.root.resources` | 资源位置、跨 root 源码/子图/实现文件/构建 include 依赖 |
| `vibeflow.root.nodesets` | 导入子图与消费方使用相同 Target |

运行和构建当前 workflow 时也执行项目规则。此时 `usage_complete=false`，默认共享使用数量规则不拿局部清单推断全项目引用次数；完整项目检查才统计全部 root。

自定义治理 Rule 可以读取对应 facts 下的 `packages`、`nodeset_imports`、`resource_dependencies`，项目规则还取得 `shared_imports`。准备阶段不会提前执行默认包隔离政策，因此自定义治理 Plugin 本身也可由替换后的政策检查。

取消限制不会引入跨语言执行能力：获准子图仍由消费方 Target 编译，所引用 Node 必须能在消费方解析和绑定。文件不存在、配置格式错误、重复标识和实际 ABI 不兼容继续产生错误。

## 相关文档

- [架构阅读与维护](architecture.md)：项目、root 与 workflow 的架构资料。
- [Rule 与 Node](rules-and-nodes.md)：检查等级、局部及图级规则选择。
- [Plugin 与集成](plugins-and-integrations.md)：资源包声明与生命周期。
- [多文件资源](multifile-resources.md)：实现文件和库依赖。
- [本地预览](local-preview.md)：项目总览和资源展示。
- [迁移说明](rule-system-migration.md)：旧目录、配置与接口升级。
