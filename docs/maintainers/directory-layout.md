# 仓库目录职责

| 位置 | 所有者与内容 |
| --- | --- |
| 根目录 | 项目入口、许可证、构建与 Git/CI 元数据；不保存临时脚本或运行输出 |
| .github | GitHub Actions、Issue 和 Pull Request 模板 |
| src/vibeflow | Core、BlockCompiler、Python/JavaScript Target、Target 共用支持与 Tooling 的核心源码及运行资源 |
| distribution | 构建器、profile 配置、提示词、项目模板、最小项目和 distribution/docs 用户文档原稿 |
| dist | 最新正式发行目录、对应 ZIP 和校验清单 |
| archive | 被替换的历史发行 ZIP；同版本不同构建可保存在 history 下 |
| sandbox/python、sandbox/javascript | 公开 SDK/CLI 与真实宿主环境中的使用项目，直接加载工作区 src |
| tests | 非沙盒功能、代码、集成、一致性和实现回归；fixtures 保存输入、基线和独立回归 runner |
| repo_check | 独立的仓库质检工具及其自身测试，不进入产品发行包 |
| references | 外来参考项目，不作为生成产物仓库 |
| tools | 开发、验证、清理和辅助工具 |
| docs | 当前设计、维护说明、执行计划、历史结论与证据索引；图片及长期阅读工作簿等正文资源放在 assets |

## Rule 与 Node 的源码边界

Core 的 `core/rules/` 负责公共 Rule/Ruleset 模型、资源选择、范围规划、依赖组合、执行与结果复用，不提供具体内置规则、阈值或质量检查算法。

Python 和 JavaScript Target 分别维护 `rules/`、`rulesets/`、`nodetypes/`：

- `rules/graph/` 定义和实现图级检查；`rules/node/` 定义和实现节点源码检查；`rules/project.py` 定义项目源码质量检查。
- `rulesets/` 定义组合、依赖、阶段入口、Workflow 默认；各 Target 自己表达支持范围，不在装配时修改另一语言的 Ruleset。
- `nodetypes/` 保存现有节点声明与语言接口；SDK 保持原公开入口，节点仍经 Plugin 贡献资源，不新增隐式默认。
- Target 的 `quality/` 提供事实、上下文、执行组织和报告，具体规则判断归 `rules/`。
- `targets/shared/quality_support/` 和 `rule_support/` 提供共用算法、事实数据、Record 契约与装配辅助，不登记 Rule 或 Ruleset，也不依赖具体 Target。

CLI 的结果范围与内置检查说明由 `tooling/application/result_scope.py` 维护，不进入 Core。

资源声明来源和实现来源分别记录：图检查可复用共用算法，但声明的来源仍是对应 Target 的 `rules/`；Ruleset 的来源是对应 `rulesets/`。

## 产物与证据

### 路径引用约定

- 仓库内 Markdown 文件链接以所在文档目录为基准使用相对路径，保留需要的锚点或行号；不写维护者电脑的绝对路径。
- 运行时代码和工具参数以各自所属的项目根目录、配置文件目录或资源目录为基准解析路径；只在同一模块或工具边界内复用路径计算，不建立所有组件都依赖的全局路径表。
- 外部工作区、依赖缓存及证据原件的根位置由对应工具的参数或配置提供。历史原件的定位与可访问状态记录在[证据索引](evidence/index.md)；链接到索引不表示原件已随仓库提供。

测试、依赖安装和临时构建默认使用自动清理的仓库外工作区。显式保留的工作目录由调用者负责结束后清理，不能放在 dist、archive 或案例源码目录中。

历史审核材料保存于仓库旁的 `VibeFlow-evidence/directory-remediation-20261009`；[索引](evidence/index.md) 记录原位置、大小、SHA-256 和恢复方法。该索引说明上次整改保留的历史材料。本轮用户确认：已过时且不再使用的材料直接删除，不默认建立副本或归档；旧版已由 Git 保存时直接通过提交追溯。只有仍有明确用途的资料才继续保留。

测试使用的 `tests/fixtures/rule_parity/reference.json` 是输入基线，必须随代码保留；它与一次运行生成的报告有不同用途。不能只根据扩展名认定文件可删。

## 发行

默认构建的两个目录及 ZIP 都进入 dist。正式替换时，被替换的 ZIP 进入 archive；已有同名历史包的内容不覆盖。同版本重建也保存先前字节。生成、验证或事务发布失败时，恢复先前正式产物。

版本号以 pyproject.toml 和发行包元数据为准。目录维护不自动更新正式产物；候选包在仓库外构建，正式更新使用 distribution/build.py。

源码全文摘录、pytest 收集输出和重复机器盘点使用仓库外临时工作区，完成用途后删除；中文结论及有阅读价值的工作簿保留在 history 和 assets。outputs 与 output 都不是根目录的持久资料位置。

本轮原则和验收见 [目录清理记录](directory-cleanup-20261010.md)。

## 各层目录说明

仓库自行维护的每层目录用 README.md 说明唯一用途、禁止混入的内容和生成物去向。现有案例的 README 保留运行方法与验收说明，并补充目录边界；新增子目录时同步维护说明。目录职责随实际架构调整，不能把目录名当作自动判断文件用途的依据。

`.github/` 的目录说明使用 `DIRECTORY.md`：GitHub 优先展示该目录的 README，保留此例外才能让仓库首页展示根目录的项目说明。其子目录仍可使用 README.md。

dist 中的发行树、archive/history 中的版本资产和 references 中的第三方项目由其上层说明约束，不逐层添加维护者文件。Git 内部目录、工具缓存和临时工作区也不属于源码目录说明的覆盖范围。

新增的维护者目录说明以 `<!-- vibeflow-directory-purpose -->` 开头。发行构建跳过带此前缀的 README，避免将开发路径或维护要求带入内核和用户模板；原有用户指南及 distribution/docs 中被 profile 选中的正文仍正常分发。

目录说明是维护约定，不增加新的运行或发布准入检查。现有仓库 quality 检查接受 dist、archive 和 archive/history 的目录 README，并继续识别明确放错位置的生成物。
