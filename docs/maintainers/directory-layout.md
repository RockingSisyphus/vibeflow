# 仓库目录职责

| 位置 | 所有者与内容 |
| --- | --- |
| 根目录 | 项目入口、许可证、构建与 Git/CI 元数据；不保存临时脚本；离线预览入口 vibeflow-preview.html、用户配置 vibeflow-preview.config.js 和历史目录 vibeflow-preview/ 是默认生成例外，已 Git ignore |
| .github | GitHub Actions、Issue 和 Pull Request 模板 |
| src/vibeflow | Core、BlockCompiler、Python/JavaScript Target、Target 共用支持、Coordination 与 Tooling 的核心源码及运行资源 |
| distribution | 构建器、profile 配置、提示词、项目模板、最小项目和 distribution/docs 用户文档原稿 |
| dist | 版本明确的发行 ZIP 和校验清单；展开目录只用于当前构建/验证，用完清理 |
| archive | 被替换的历史发行 ZIP；同版本不同构建可保存在 history 下 |
| sandbox/python、sandbox/javascript | 公开 SDK/CLI 与真实宿主环境中的使用项目，直接加载工作区 src |
| tests | 非沙盒功能、代码、集成、一致性和实现回归；fixtures 保存输入、基线和独立回归 runner |
| repo_check | 独立的仓库质检工具及其自身测试，不进入产品发行包 |
| references | 外来参考项目，不作为生成产物仓库 |
| tools | 开发、验证、清理和辅助工具，以及独立只读 workflow-viewer 源码；浏览工具由发行构建显式打包 |
| docs | 当前设计、维护说明及待执行计划；图片及长期阅读工作簿等正文资源放在 assets |

## Rule 与 Node 的源码边界

Core 的 `core/rules/` 负责公共 Rule/Ruleset 模型、资源选择、范围规划、依赖组合、执行与结果复用，不提供具体内置规则、阈值或质量检查算法。

Python 和 JavaScript Target 分别维护 `rules/`、`rulesets/`；Python SDK 代码位于 `sdk/`，JavaScript SDK 与运行脚本位于 `resources/`：

- `rules/graph/` 定义和实现图级检查；`rules/node/` 定义和实现节点源码检查；`rules/source_quality.py` 提供 Target 源码检查声明；project/root 治理声明及其公共算法归 shared/rule_support/governance.py。
- `rulesets/` 定义组合、依赖、阶段入口、Workflow 默认；各 Target 自己表达支持范围，不在装配时修改另一语言的 Ruleset。
- `sdk/` 与 `resources/` 按语言保存公开 SDK 及运行支持；NodeType 定义外观和默认规则，业务 Node 从 project/root 的 nodes/ 发现，Plugin 不能贡献业务 Node。
- Target 的 `quality/` 提供事实、上下文、执行组织和报告，具体规则判断归 `rules/`。
- `targets/shared/quality_support/` 和 `rule_support/` 提供共用算法、事实数据、Record 契约与装配辅助，包含共用纯算法与 project/root 治理声明，不依赖具体 Target。

`tooling/project/` 按清单、resources 准备与 governance 编排组织项目准备；模型不执行文件 IO。完整项目审查生成 PROJECT_ARCHITECTURE.jsonc，workflow 架构登记由 architecture_registration 单独处理。

CLI 的结果范围与内置检查说明由 `tooling/application/result_scope.py` 维护，不进入 Core。

资源声明来源和实现来源分别记录：图检查可复用共用算法，但声明的来源仍是对应 Target 的 `rules/`；Ruleset 的来源是对应 `rulesets/`。

## 产物与证据

### 路径引用约定

- 仓库内 Markdown 文件链接以所在文档目录为基准使用相对路径，保留需要的锚点或行号；不写维护者电脑的绝对路径。
- 运行时代码和工具参数以各自所属的项目根目录、配置文件目录或资源目录为基准解析路径；只在同一模块或工具边界内复用路径计算，不建立所有组件都依赖的全局路径表。
- 外部工作区、依赖缓存由工具参数提供，不以本机绝对路径作为运行或测试依赖。

测试、依赖安装和临时构建使用自动清理的仓库外工作区。已退役的代码、文档、计划、报告、测试和展开的旧发行副本直接删除；仍有效的知识先并入当前规范。历史溯源使用 Git，唯一归档例外为版本明确的压缩分发包及其校验清单。不能将旧文档压缩成包规避删除。业务输出、用户日志和 trace 不属于代码文档清债范围。

测试使用的 `tests/fixtures/rule_parity/reference.json` 是输入基线，必须随代码保留；它与一次运行生成的报告有不同用途。不能只根据扩展名认定文件可删。

## 发行

默认构建的两个目录及 ZIP 都进入 dist。正式替换时，被替换的 ZIP 进入 archive；已有同名历史包的内容不覆盖。同版本重建也保存先前字节。生成、验证或事务发布失败时，恢复先前正式产物。

版本号以 pyproject.toml 和发行包元数据为准。目录维护不自动更新正式产物；候选包在仓库外构建，正式更新使用 distribution/build.py。

源码全文摘录、pytest 收集输出和一次运行的盘点使用仓库外临时目录，完成用途后删除。当前失败必须如实说明，不能用定向成功或后续通过改写此前批次；有效复现迁入现有测试后，删除退役任务材料。

## 各层目录说明

仓库自行维护的每层目录用 README.md 说明唯一用途、禁止混入的内容和生成物去向。现有案例的 README 保留运行方法与验收说明，并补充目录边界；新增子目录时同步维护说明。目录职责随实际架构调整，不能把目录名当作自动判断文件用途的依据。

`.github/` 的目录说明使用 `DIRECTORY.md`：GitHub 优先展示该目录的 README，保留此例外才能让仓库首页展示根目录的项目说明。其子目录仍可使用 README.md。

dist 中的发行树、archive/history 中的版本资产和 references 中的第三方项目由其上层说明约束，不逐层添加维护者文件。Git 内部目录、工具缓存和临时工作区也不属于源码目录说明的覆盖范围。

新增的维护者目录说明以 `<!-- vibeflow-directory-purpose -->` 开头。发行构建跳过带此前缀的 README，避免将开发路径或维护要求带入内核和用户模板；原有用户指南及 distribution/docs 中被 profile 选中的正文仍正常分发。

目录说明是维护约定，不增加新的运行或发布准入检查。现有仓库 quality 检查接受 dist、archive 和 archive/history 的目录 README，并继续识别明确放错位置的生成物。
