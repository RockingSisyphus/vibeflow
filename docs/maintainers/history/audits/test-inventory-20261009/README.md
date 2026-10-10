# 测试审核与分类记录（2026-10-09）

审核日期：2026-10-09。版本：0.17.0。审核起点：`665e06e71725990be7a83d7e5c65d5897b051e89`，开始时工作区干净。

本记录保留整合前的中文分类、统计口径和阅读工作簿。源码以起点 Git 提交为准，重复机器索引与收集输出已删除。随后新增双 Target 综合数学沙箱并合并重复运行项；当前替代关系、数量与实际运行成绩见 [综合沙箱整合归档](../comprehensive-sandbox-20261009.md)。

本审核回答的是“测试搭了什么场景、运行了哪一层代码、期待什么、如何判定通过”。依据审核当时源码和一次成功的 pytest **仅收集**。没有重新执行测试，也没有把旧日志中的通过成绩搬到当前版本。

## 归档内容与使用方法

- [归档大表](大表.md)：148 个 tests 文件组、217 条沙盒/示例场景说明、11 条 fixtures 独立入口或支持目录说明。文件组逐项解释场景、实际调用范围、通过条件和验证边界。
- [分类小表](分类小表.md)：11 类主要目的及数量；每个测试文件只归一个主类，避免重复计数。混合文件中的其他目的仍在大表中说明。
- [可筛选工作簿](../../../../assets/audits/test-inventory-20261009/测试审核归档.xlsx)：分类概览、归档大表、逐用例、沙盒场景、独立夹具。逐用例共 1,379 行，保留 4,221 个参数展开项的分布，以及输入/修改、调用、assert、raises、内嵌脚本与源码位置。长代码列为明确标注的阅读摘录，完整源码可在起点 Git 提交中按路径和行号查阅；它不是当前实现的源码快照。

所有数量均为本次源码盘点或收集数量，**不是通过数量**。多个 runner 会复用同一 pytest/fixture 场景，不能把各表行数直接相加作为总覆盖。

## tests 与 sandbox 实际怎样工作

`sandbox` 是模拟用户接入的小项目：有公开 SDK 的 Node、BaseLib、Plugin、Rule/Ruleset 和 workflow 配置。实际运行时加载当前仓库 `src`。Python 集成 runner、JS 最小 runner、JS 集成 runner会复制项目并在临时目录准备依赖、生成产物、调用正式接口。部分目录没有自己的 runner，由 pytest 或 `tests/fixtures` 中的脚本复制/修改/执行它们；目录存在不等于这个场景会自动执行。

`tests` 是 pytest 测试和其夹具。`core`、`block_compiler`、`targets`、`tooling`、`conformance`、`integration` 说明主要被测层，不能单凭目录认定“集成”“端到端”或“纯单元”。项目明确收集 `test_*.py`、`strict_*.py`、`vibeflow_strict.py`。例如 `strict_runtime.py` 含真实运行，但 `test_javascript_sandbox.py` 的一组正例只是 **prepare AOT plan**，断言选中库/能力/调用路径正确，并没有把每个正例的生成物运行一遍。

`tests/fixtures` 既有被 pytest 引用的输入、辅助模块和历史冻结项目，也有独立验收脚本。特别是 `test_rule_parity_reporting.py`、`test_rule_gaps_reporting.py` 检查比较器/报告器本身，常由替身提供观察结果；真正的规则场景在对应 `fixtures/.../run_all.py` 中执行。只有比较器测试通过，不能说明那些产品场景已通过。

运行“完整小型工作流”，指真实经过框架和该示例的业务链。例如 JS 的 `receive→math Node→BaseLib→send` 是实际生成物执行，但 receive/send 由用例注入函数提供。它能验证框架调用协议和数值，不能证明实际网络、数据库或其他宿主服务已经接通。同理，Python 的 training 对象例使用小型 `SandboxModel`/`SandboxOptimizer`，检查 loss=6、grad=0.6、weight=0.7 和对象引用，不是一次真实 ML 训练实验。

## 按测试方法再看一遍

这些方法互相重叠，所以此表不重复统计执行项。

| 方法 | 模拟条件及实际执行 | 通过依据 | 能说明的范围 |
| --- | --- | --- | --- |
| 局部单元/模型测试 | 人工构造 Graph、Descriptor、质量指标、record、参数、文件集合；调用局部函数 | 值、对象身份、错误类型、序列化和不可变性精确匹配 | 内核局部逻辑；人工质量指标并不验证 AST 提取是否正确 |
| 静态合法/违规对照 | 改写真实源码/声明/config；跑解析、选中 Rule、validate/quality/prepare | 合法代码放行；违规代码出现指定 code/severity/owner/位置；marker 证明尚未导入业务 | 已选规则能发现列出的有限问题；不是任意代码安全证明 |
| 阈值和参数矩阵 | 等于/超过行数、字节、深度阈值；多 effect_scope、alias、语法形态组合 | 临界处精确放行或 warning/error；取消某限制后不误报 | 明确边界；展开项很多不等于等量独立业务功能 |
| 真实运行/集成 | 小型 Node→库→Nodeset/Loop→end；plan/block/compiled；JS build 后 Node.js 调用 | 输出数值、引用、任务/执行顺序、trace、产物一致 | 该示例的完整调用链；不能替代基于框架开发的项目自身业务测试 |
| 真实浏览器/图形 | 真实 Mermaid/Puppeteer 渲染；打开本地页点击按钮或给 Host 发 message | DOM/几何/颜色/形状/展开覆盖正确；加载不自动运行、点击后指定输出 | 真浏览器对应场景；纯 XML、字符串或 mock renderer 是另一层证据 |
| 失败注入/清理/并发 | Node/hook主动抛错、任务挂起/超时/取消、发布中断；同时运行多实例 | 目标错误带根因/路径；不跑后续Node；锁/资源释放；实例不串值；旧产物保留 | 注入故障与有限并发窗口，不是长期自然运行稳定性的证明 |
| 对照/冻结输出/包隔离 | Python与JS共同语义、旧观察与当前、golden/hash、同请求两次构建、包内加载 | 指定语义/字节/身份精确一致；已批准语义变化另有明确预期 | 对照契约与交付物来源；golden 不会自动判断新行为是否更合理 |
| 复用/性能机制 | 大量共享 AST/records、8/32/80 Node，跨workflow/source内容变化 | 解析/绑定/检查的确定性次数；变化失效；共享不扩大权限 | 复用机制正确；耗时对照不构成跨机器固定毫秒承诺 |
| 工具自身 | 给 runner 空观察/重复ID/损坏记录，配置workers或过程异常 | 0/1/2退出码准确；空覆盖不通过；workers有界 | 测试机制可信；本身不执行全部产品验收场景 |

## 通过不一定意味着程序成功运行

正例通常要求指定结果，比如 Python linear 的 `value.final=14`，JS linear 的 `{x:10,a:8,b:3}` 得到 `result=15`，JS stop_when 循环从 1 得到 4，history 为 `[2,3,4]`，迭代数为 3。

负例是“故意给程序错东西”。比如 Node 直接 import 另一个 Node，要出现 `VF_IMPORT_NODE_TO_NODE`；输入类型不对，要在 Node 运行前拒绝；Node 主动抛错，要规范化为 `VF_NODE_FAILED` 并保留路径/根因。若它错接受、报的是另一个无关错误，或清理没完成，测试反而失败。`pytest.raises(...)` 同时约束异常类型，后续 assert 可进一步检查其内容。

也有 warning 对照：程序允许继续，但必须出现对应 warning。`CONCERNS` 在部分正例是允许状态；是否通过由本用例断言决定，不能一律要求字符串 `PASS`。`INVALID_CASES` 和 `negative/` 中还保留了**合法能力对照**，例如当前不再默认禁掉普通字符串求值、部分普通对象/属性：这些用例要求放行，或要求退役诊断不再出现。不能按目录/数组名字推断预期。

两个独立规则观察 runner 另外区分：`0`=所运行观察满足期待，`1`=行为不匹配，`2`=观察进程/环境不正常。空组、重复 ID、缺失记录也不允许冒充成功。JS 集成 runner 的 `--skip-browser` 是明确减量模式，三项浏览器任务记录 SKIP；退出 0 不等于“所有浏览器测试通过”。

## 审核时的入口与验证边界

| 入口 | 实际包含什么 |
| --- | --- |
| `python tools/run_tests.py` | 临时目录、隔离 Python/user-site/pytest 插件，按锁文件准备 TS/esbuild，默认 pytest 主套件；默认多个 worker，按文件分组；它本身不执行全部独立 fixtures runner |
| `python tools/verify_project.py` | repository-quality、compileall、pytest 三步；没有 `--full` 时不运行后续沙盒/包/独立图形步骤 |
| `python tools/verify_project.py --full` | 当前共17步：前述3步，再加Python沙盒、JS最小、JS集成、rule-regressions、browser运行观测、review-layout、resource-sections、review-performance、adaptation-regressions、wheel隔离、生成物清理、distribution、最终quality、clean-tree |
| `tests/fixtures/rule_parity/run_all.py --current-only` | 当前规则真实执行，历史两版读取冻结观察，**不是重放旧版本**；完整门禁使用这个模式 |
| `quality/test.py` | 仓库质量检查工具自己的额外单测，不属于本次 `tests` 的4,221项；完整项目的repository-quality调用 `quality/run.py --profile all`，不能把两者混为同一测试入口 |

普通 pytest 中，部分真实 SVG/Chromium 用例会因缺 renderer 或工具链 skip；完整验证入口显式准备锁定渲染器并调用独立浏览器场景。审核不能把 skip 当作验证成功，也不能把历史“全量通过”当作这次完成。

本次在仓库外临时目录使用等价的仅收集配置：`PYTHONPATH=src:tools` 的绝对路径、禁用 user-site 与 pytest 插件自动加载、禁用 pytest cache，执行 `python -m pytest --collect-only -q -p no:cacheprovider <绝对tests路径>`。没有为收集安装 npm，也没有调用完整 runner、训练或任何产品场景。收集成功只证明当前 Python 环境能发现和导入这些测试模块。

归档校验核对全部148文件、1379函数、4221参数执行项均有对应行，摘要数量与明细一致，源码行号/哈希匹配。工作簿另外验证导出内容和每张表的代表性视觉输出。没有代码覆盖率数据，因此不能据此给出“覆盖了全部框架代码”或“所有使用该框架的项目都正确”的结论。
