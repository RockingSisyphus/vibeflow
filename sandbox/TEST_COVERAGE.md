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

二次代码审查另发现测试入口会将 `-k tools` 等选项值误当作现有目录改写。现在交由 pytest 解析，仅固定已解析的测试目标；通过真实测试入口，验证串行与并行选择结果，以及测试模块导入和执行时的隔离目录。浏览器依赖链的 [Zod 已知问题](https://github.com/advisories/GHSA-mrhx-c7xc-m3w5)随 Puppeteer 正常升级至 25.16.0 解决，不添加依赖覆盖；锁文件安装审计为零已知漏洞；升级后八项真实浏览器交互测试通过（16.25 秒）。

[修复后第二轮 CI](https://github.com/RockingSisyphus/vibeflow/actions/runs/41572114454) 对应源码 `d1d4e0907afa0fcf124b6e53cd304f5f91615c79`，三个 job 全部成功：Linux Node 22 为 670 passed、2 subtests passed（328.24 秒），Node 24 为 670 passed、2 subtests passed（347.49 秒），Windows 为 131 passed（249.16 秒）。两个 Linux job 的五个阶段均通过，没有失败、准备错误或跳过。Windows 保持原宿主/协作/命名入口覆盖，并增加两项测试入口回归；它不代表 Windows 上运行了完整 Linux 浏览器和交付集合。

最终配置复核发现 setup-node 保存默认 `~/.npm`，而测试入口实际下载缓存位于临时工作区；已让 CI 与入口共同使用 `runner.temp/npm-cache`，不缓存工程或构建结果。功能和测试判据未改。

[最终 CI](https://github.com/RockingSisyphus/vibeflow/actions/runs/41573240624) 使用快照 `9fdcfc6aa51d3e9243e91cad69c843ac9043021c`，三个 job 全部成功。直接下载并解析其 JUnit 与 verification.json，结果如下：

| 最终平台 | pytest 自然输出 | 报告核对 |
| --- | --- | --- |
| Linux / Python 3.11 / Node 22 | 670 passed、2 subtests passed；427.19 秒 | 五阶段全部通过，总计 455.34 秒；JUnit 670 条 testcase，0 failure/error/skipped |
| Linux / Python 3.11 / Node 24 | 670 passed、2 subtests passed；425.05 秒 | 五阶段全部通过，总计 454.78 秒；JUnit 670 条 testcase，0 failure/error/skipped |
| Windows / Python 3.11 / Node 24 | 131 passed；184.64 秒 | JUnit 131 条 testcase，0 failure/error/skipped；宿主范围同第二轮 |

本轮 CI 的 JUnit 没有把子场景展开为额外 testcase，不将终端的两个 subtest 与记录数相加。Linux 日志确认 setup-node 与运行入口均使用 `/home/runner/work/_temp/npm-cache`，缓存成功保存；锁文件安装报告零已知漏洞。耗时是各次 runner 的实际观察，不将批次间差异归因于本次修改或承诺固定速度。

该轮验收结束时只补写本节结果，其他代码保持上述快照；真实索引和本地 main HEAD 未变。远端只更新隔离 CI 分支，未合并 main、发布或部署。该轮临时环境与候选包已清理，仓库 all 检查为零错误、零警告，退役引用审计通过，清理预览为零项。后续补充复核另记如下，不能把该轮通过视为尚未覆盖判据的证明。

### 计算结果与退出码补充复核

用户后续指出三个计算场景只有成功判据、部分诊断未检查退出码，以及生产代码中遗留旧测试探针。前一轮绿色 CI 对这些遗漏没有检错能力，本轮补充以下行为判据：

- free_nodes 独立预期 `value.out = 13`，io_data_store 独立预期 `value.final = 21`；计算案例直接读取必填的 expected_outputs，不再把缺失预期当作空集合。
- 非 JSON batch metrics 经应用收到的 public_outputs 验证 batch 返回同一业务对象、集合仍是 set 且值为 2/4、NaN 未丢失；训练 metrics 同样验证模型引用、标签 set、NaN 与 loss。应用只导出收到的业务结果，没有增加产品采集接口。
- 每个诊断案例明确指定退出码。两个含目标 warning 的旧工程同时含拓扑 error，必须拒绝；另用合法工程的重复逻辑 warning 验证 CONCERNS、无 error 和退出 0。没有弱化规则来制造放行。
- 删除旧私有探针、仅为其维护的保护深度、同步/异步 token 设置及重置，并删除沙箱中无人使用的旧重置函数。实际执行租约、锁栈和锁仲裁保持原职责；同步及显式声明 async 的锁工程覆盖源码/AOT、三种 Python 执行模式。

首轮定向为 258 passed、2 failed，失败揭示了上述混合 error/warning 不能按纯 warning 设置退出预期。执行包补齐对照后为 236 passed、6 failed；六项新增异步输入误用了同步工程声明，修正正常配置的 entry_mode 后，六项定向全部通过（4.45 秒）。其余 25 项并发/协作/会话场景已通过；没有修改产品行为来迎合这些测试准备错误。

在独立源码副本中逐次修改普通业务节点，另两项修改副本的 CLI 返回码；九个错误对照均使对应真实端到端场景失败：

| 故意错误 | 新判据结果 |
| --- | --- |
| free_nodes 输出 999；io_data_store 输出 999 | 分别检出，预期为 13/21 |
| batch metrics 只返回 size=999 | 检出丢失的公开结果字段 |
| set 换成相同元素的 list；NaN 换成 0 | 分别检出类型与数值语义丢失 |
| batch 或模型换成等值的新对象 | 分别检出返回引用改变 |
| error 打印后退出 0；纯 warning 打印后退出 1 | 分别检出错误退出行为 |

错误对照只操作本轮隔离副本，未保留补丁、mock 或产品探针。当前修复待同一 CI 矩阵验收。

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

Linux Node 22/24 全量、Windows Node 24 原有宿主范围及新增两项入口回归已通过最终 CI。Windows 未运行 Linux 的完整浏览器和交付集合。没有在原生 GBK 默认环境进行验收，也不把 UTF-8 mode 切换当作这种证明。Python 的 JSON Schema 输入值域校验按现有能力验证，未扩展为 JS 的同等能力。

内部缓存、AST/框架对象身份、内部调用次数和强行插入的布局竞态不属于本体系的通过结论；依赖方向继续由静态检查与代码审查负责。测试数量和文件数量不能代替功能域判据。临时运行数据在记录上述结论后清理；后续 CI 保留正常 verification.json 与 acceptance.xml。
