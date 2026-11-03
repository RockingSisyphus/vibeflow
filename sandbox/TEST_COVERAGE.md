# 用户行为测试覆盖

所有场景经统一入口运行，sandbox 只保存真实工程。完整验收：

```bash
python tools/verify_project.py --full --workers 4
```

定向运行使用 `python tools/run_tests.py -- tests/e2e/<文件>`。下表路径均相对 tests/e2e；共享输入来自 cases/、applications/ 和 sandbox/。

| 功能域 | 真实入口 | 判据与对照 | 退役内容 |
| --- | --- | --- | --- |
| 配置与 SDK | test_sdk_configuration.py、test_entries.py；SDK 工程→CLI→应用/tsc | 默认类型、覆盖、空值、命名入口、输入输出与实例隔离；缺失/未知输入诊断 | 内部 Config/注册器构造、模拟导入 |
| 图执行 | test_execution.py、test_javascript.py、test_comprehensive.py；源码/正常 AOT | 独立数字、分支、汇合、循环、嵌套、活业务对象；错误输入与修正对照 | 手工 IR、内部执行器与计划身份断言 |
| 资源与插件 | test_resources.py、test_session_behaviors.py、test_failure_reporting.py | 多文件修改/恢复输出、正常 Plugin 生命周期、主错误/清理错误及完成输出 | 工厂替身、内部实例/退出栈探针 |
| Rule | test_source_policies.py、test_rules.py、test_selection.py、test_quality.py；真实声明与检查命令 | 作用域、别名、依赖、覆盖、空选择、误报对照、Node/Library 大小与复杂度、调用链；code/severity/文件/位置 | RuleContext、handler 调用、旧源码检查总包 |
| 项目治理 | test_governance.py、test_quality.py；多 root 工程的 validate/quality/review/run | 私有/共享资源、局部/全工程范围、文件/函数阈值、依赖链/环、重复建议、声明归属及非法引用诊断 | 内部库存/资源闭包伪造 |
| Python 部署 | test_deployment.py、test_execution.py；正常 build→删除源码→搬移运行 | Nodeset、plan/block/compiled、独立预期与错误传播 | 私有 AOT 编译调用、手拼部署描述 |
| JS/TS 构建 | test_javascript.py、test_entries.py、test_resources.py | CLI 构建、原生 Node 应用、TypeScript 正反类型检查、字面文件路径 | 发射器快照、模块加载改写 |
| 协作与取消 | test_cooperation*.py、test_session_behaviors.py；真实产物/HTTP/子进程/浏览器按钮 | 并发公式、独立实例、消息、可重复终态、取消/超时/清理及错误对照 | 假描述、替代 runner、私有取消状态 |
| 运行观察 | test_observation.py、test_concurrency.py、test_execution.py、test_javascript.py；CLI、实际宿主与页面 | 自然状态/日志、三档 trace 的公开输出、业务开始和清理收据、容量/增量补位、断图拒绝 | 内部活动 frame、缓存和调度计数器 |
| 展示架构 | test_preview.py、test_layout.py、test_web_app.py；正常 review→真实 Chromium | 可见资源/计划状态、折叠、详情、顺序、历史、缩放、消息交互 | 合成页面、VFLayout/VFModel 调用、控件脚本赋值与隐藏 getter |
| 交付物 | test_delivery.py；wheel/sdist 安装及两 profile 解压搬移 | 脱离仓库构建/执行、正常审查刷新、独立 AOT 运行 | 重复 smoke 壳、内部包内容模型替代安装 |
| 开发工具 | test_repository_checker.py、test_developer_tools.py、test_process_supervision.py、test_cli.py、test_encoding.py | 实际 CLI 状态/JSON/诊断/文件/进程退出；清理仅在本轮隔离 Git 仓库 | checker 内部 unittest、mock 打印/导入、伪编码补丁 |
| 性能隔离 | test_performance.py；固定工程正常构建及运行 | 冷/重复/编辑/跨工程/恢复正确结果；墙钟、CPU、正常子进程 RSS 观察 | AST 身份、Program/解析次数、加载器探针及任意速度门槛 |

源码案例保留为独立输入数据并按同政策分组，通过真实资源路径和诊断位置区分；加载会中止的错误独立执行。计算期望独立编写，Python 当前输出不作为 JS 的唯一答案。内部依赖方向由现有静态检查和审查确认，端到端不证明内部对象身份或调用次数。

源码场景加载当前工作区；交付场景另行构建到临时目录并隔离安装，不更新正式 dist。完整入口一次准备锁定工具链，必需环境缺失属于失败。Linux Node 22/24 与 Windows Node 24 的 CI 作用见[开发与验证](../docs/maintainers/development.md)。Python 的运行输入值域与 JS JSON Schema 能力按现行各自行为验收。

性能的 RSS 是该 worker 已结束子进程的累计峰值，不能当作每个阶段的独占内存；CPU 使用阶段差值。性能数值用于观测，不据此宣称内部缓存命中或跨机器提速。

## 实际验证记录

2026-11-03，本机 Linux、Python 3.13.13、Node 24.18.0、Chrome 156.0.8078.79。统一工具链为 TypeScript 7.0.2、esbuild 0.28.1、Puppeteer 25.2.1；4 个 worker。验证对象是当前工作树，没有提交或更新正式发行物。

| 冻结批次 | 端到端实际结果 | 处理与边界 |
| --- | --- | --- |
| 首轮 | 630 passed、3 errors，另 2 个 subtest passed；147.21 秒 | 清理时误删多 root 输入造成三项准备错误；其余四个验证阶段通过。批次结束后恢复输入，项目治理定向 8 项通过 |
| 恢复后整批 | 633 passed，另 2 个 subtest passed；145.76 秒 | 五个阶段均通过；随后对照旧语义，继续补齐质量规则、日志和展示判据 |
| 最终整批 | 668 passed，另 2 个 subtest passed；211.75 秒 | 0 failed、0 error、0 skipped；五个阶段全部通过 |

最终命令为 `python tools/verify_project.py --full --workers 4 --scratch <仓库外目录>`，复用首轮准备的同一套锁定依赖，并指定本机 Chrome。完整入口总耗时 226.44 秒（含前后仓库质量、语法编译及清理预览）；源码退役审计与 diff 格式检查另外通过。JUnit 中共 670 条记录，包含上述两个 unittest 子场景，不把它们混算为另两项主用例。表中十三个功能域对应的当前测试文件均在最终同一批次执行。

包含真实 Chromium 操作、Python 三执行模式、正常 AOT/HTTP 协作、wheel/sdist 各自隔离安装、两个发行 profile 的解压/改名/审查刷新与脱离源码运行。候选交付物只在本轮隔离目录构建。另经统一入口完成一次仅 Node 场景的冷工具链准备和真实运行：1 passed，未创建浏览器下载缓存。集合查看为 668 项、0.27 秒，不安装 Node 依赖。

新增质量对照验证了文件/函数阈值、依赖链和环、重复建议、SDK 声明归属、Node/Library 大小和复杂度，以及调用链的允许/warning/error/恢复。补测发现并修正 JS SDK `run` 缩写、显式属性与方法绑定的质量入口解析，避免遗漏实际调用链；Python 源码投影同时修正嵌套函数被移到外层导致的词法作用域误报。两处均通过正常工程和命令验证。

### CI 二次复查

首轮实际 GitHub Actions 使用独立分支 `ci/e2e-review-20261103`，源码快照 `a8b696119ebd589d52a0f8edf5d9fa0cdfda8e47`；[运行记录](https://github.com/RockingSisyphus/vibeflow/actions/runs/41569848465)。未合并 main，也未构建或发布正式发行物。

| 平台 | 首轮实际结果 | 根因与处理 |
| --- | --- | --- |
| Linux / Python 3.11 / Node 22 | 666 passed、2 errors，另 2 subtests passed；540.05 秒 | 文档链接指向 Git 忽略的本机旧 ZIP，干净检出质量检查失败并阻止两个 profile 构建；改为明确的本机产物记录，保留校验值 |
| Linux / Python 3.11 / Node 24 | 666 passed、2 errors，另 2 subtests passed；540.49 秒 | 同上；未上传历史产物或绕过质量检查 |
| Windows / Python 3.11 / Node 24 | 113 passed、6 failed、10 errors；258.69 秒 | JSON 路径断言未解码反斜杠；独立构建驱动遗漏子进程输出编码。改为解析后的路径比较，并复用共享 CLI 驱动 |

批次结束后集中修复。三个相关测试文件的 53 项定向验证通过，父环境设为 cp1252；它用于复现驱动编码问题，不替代真实 Windows 验收。仅导出已入快照的源码、不带本机 ZIP，仓库 all 检查为零错误，四项 wheel/sdist/两 profile 交付测试通过（71.79 秒）。

二次代码审查另发现测试入口会将 `-k tools` 等选项值误当作现有目录改写。现在交由 pytest 解析，仅固定已解析的测试目标；通过真实测试入口，验证串行与并行选择结果，以及测试模块导入和执行时的隔离目录。浏览器依赖链的 [Zod 已知问题](https://github.com/advisories/GHSA-mrhx-c7xc-m3w5)随 Puppeteer 正常升级至 25.16.0 解决，不添加依赖覆盖；锁文件安装审计为零已知漏洞；升级后八项真实浏览器交互测试通过（16.25 秒）。修复后的完整 CI 尚待验收。

### 样板与成本观察

以下为完整批次后、依赖已经准备好的单次串行样板，单位秒。基础准备是复制示例或写入基础 SDK 声明；命令时长包含各自正常进程启动、加载与检查开销，未拆分内部解析或编译阶段。

| 样板 | 基础输入准备 | 真实操作 |
| --- | --- | --- |
| 规则拒绝与误报对照 | 0.0003 | 拒绝 0.329；合法遮蔽对照 0.327 |
| Nodeset 搬迁 AOT | 0.0010 | 构建 0.831；删除源码后的应用启动与运行 0.279 |
| 真实预览 | 0.0007 | review/发布 0.937；浏览器启动与实际交互合计 0.923 |

独立 CLI 启动并显示帮助测得 0.042 秒。首轮锁定 Node 依赖安装由 npm 报告约 4 秒，使用现有系统 Chrome，没有测量下载浏览器或安装 Python 环境的成本。

最终批次的固定工程“构建＋运行”五阶段（冷/重复/编辑/另一工程/恢复）为 Python 1.198/1.128/1.140/1.213/1.089 秒，JS 1.438/1.521/1.525/1.515/1.685 秒；它们在四 worker 批次中运行。数值属于本机观察，不与历史 22–28 分钟直接计算提速比例，也不是下一台机器或下一轮运行的耗时承诺。

### 尚未验证的边界

Linux Node 22/24、Windows Node 24 已实际执行首轮 CI；修复后的完整 CI 尚待通过，本机完整入口通过不等于 CI 全平台通过。没有在原生 GBK 默认环境进行验收，也不把 UTF-8 mode 切换当作这种证明。Python 的 JSON Schema 输入值域校验按现有能力验证，未扩展为 JS 的同等能力。

内部缓存、AST/框架对象身份、内部调用次数和强行插入的布局竞态不属于本体系的通过结论；依赖方向继续由静态检查与代码审查负责。测试数量和文件数量不能代替功能域判据。临时运行数据在记录上述结论后清理；后续 CI 保留正常 verification.json 与 acceptance.xml。
