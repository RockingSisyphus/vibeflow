# Python 源码审查与架构生成性能修复结果

本文面向维护 VibeFlow 内核及测试矩阵的开发者，记录重复工作如何减少，以及复用如何保持诊断、权限和真实绑定事实。

固定源码完成全量覆盖，并通过原失败8项的定向重验；新增性能矩阵全部匹配。
原全量命令退出码仍为1：14个流程中13个通过，资源阶段原观察为672/680。本文分别保留原批结果与重验结果，没有改写原verification.json。

最终性能矩阵：57项观察、51个稳定case ID，57项匹配，0项观察错误。

观察数包含三组代表案例各三次独立进程的重复；带多个配置的案例及预先登记Architecture的步骤会启动额外CLI，因此观察数不等于子进程总数。

## 本轮基线与四批改动

本轮基线已含未提交的 RuleContext._snapshots 派生复用修复：已有只读快照可在 replace 更换 subject/phase 时保留。
该能力用于本轮事实视图复用，列为基线条件；本轮新增成果按用户确定的四批记录。

| 批次 | 实际目的 | 主要私有模块及测试 | 正式沙箱范围 |
| --- | --- | --- | --- |
| 1：架构生成与绑定解耦；Prepared 和子图复用 | 检查完成后，将已确认的实现事实交给展示阶段；同一展示会话复用子图编译，生成架构时无需绑定延迟实现。 | `prepared.py`, `compiler.py`；完整测试对应见机器表 | shared-*, nodeset-*, loop-*, late-export-*；25项观察，25项匹配 |
| 2：PythonCheckSession 共享分析和安全结果复用 | 同一命令复用声明、源码闭包、事实视图、规则图与满足身份条件的源码结果；插件配置、参数、资料、调用和权限变化仍产生对应检查。 | `check_session.py`, `parse_cache.py`；完整测试对应见机器表 | cache-*, relative-*, cross-root-*, source-*；19项观察，19项匹配 |
| 3：Target 内部借用 AST；改写使用局部复制 | 内置只读 visitor 使用 Target 已解析的 AST，复用符号投影和文件指标；公开 tree、node 和 implementation_tree 继续返回隔离副本。 | `source_context.py`, `analysis_metrics.py`；完整测试对应见机器表 | shared-*, source-*, relative-*, cache-shared-symbol-permissions；22项观察，22项匹配 |
| 4：正式命令贯通；review 保留 preflight | validate、quality、review、导出和 checked run 消费同一命令的检查及展示结果；review 继续检查并拒绝失败图，预览不调用业务入口。 | `workspace_service.py`, `prepared.py`；完整测试对应见机器表 | entry-*, invalid-*, late-*, loaded-architecture-validate, relative-run, cross-root-run, nodeset-run, loop-run；19项观察，19项匹配 |

同一案例可同时验证多个批次，因此批次表中的观察次数不可相加作为独立案例数。

## 三组独立进程的耗时与确定性次数

每组以相同固定 SDK 资源启动三次正式 CLI，使用各组墙钟中位数；每个进程结束后命令内缓存即释放。
这些数值是本机固定沙箱的观察结果，不作为跨机器性能阈值。

| Node / 共享 BaseLib | 基线中位数 | 最终中位数 | 倍率 |
| --- | ---: | ---: | ---: |
| 8 / 1 | 0.834s | 0.529s | 1.58× |
| 32 / 4 | 3.998s | 1.425s | 2.81× |
| 80 / 8 | 17.152s | 4.505s | 3.81× |

确定性验收检查每个项目文件解析次数、实际 call Rule 次数、presentation 阶段绑定/规则/编译次数，以及每个子图编译次数。

| 沙箱 | 捕获的 Target AST 完整复制 | 展示绑定 / 规则执行 / 编译 | 调用级自定义Rule perf.call |
| --- | ---: | --- | ---: |
| shared-8-1 | 578→0 | 10→0 / 20→0 / 1→0 | 8 |
| shared-32-4 | 3998→0 | 34→0 / 170→0 / 1→0 | 32 |
| shared-80-8 | 16212→0 | 82→0 / 738→0 / 1→0 | 80 |

下列阶段中位数为inclusive耗时：规则执行可能被准备、检查或展示阶段包含，阶段之间存在重叠。

| Node / BaseLib | 准备prepare | 健康检查health | 规则引擎rule_plan | 架构资料architecture |
| --- | ---: | ---: | ---: | ---: |
| 8 / 1 | 0.178→0.150s | 0.264→0.090s | 0.366→0.064s | 0.191→0.024s |
| 32 / 4 | 0.681→0.496s | 1.441→0.553s | 2.120→0.402s | 1.571→0.087s |
| 80 / 8 | 2.022→1.273s | 5.506→2.488s | 7.459→1.816s | 9.369→0.341s |

AST copy 计数包裹 source_context 模块使用的 deepcopy，观察 Target 公开 AST 视图的完整复制；它不统计所有模块的 deepcopy。
内置 visitor 借用原树，类外壳或指纹归一化所需的局部复制继续保留，公开 getter 仍通过深层隔离测试。
inclusive_seconds 包含嵌套阶段，阶段之间有重叠，不能相加解释为总耗时；整体耗时使用 CLI 的 seconds。
ast.parse 总次数也含生成代码及指纹解析；实际项目文件是否重复解析以 parsing_counts 为准。

## 正确性与缓存身份

参数不同的同文案诊断、不同 Ruleset 的同名局部调用、合法 error finding 携带 records、failed/unavailable 阻断 consumer、共享源码权限及插件配置隔离，均有独立正式 validate 案例。
JSON资料可按完整内容复用；包含dataclass、frozenset等原生对象的records保守重检，保留consumer实际可见的类型。JSON输入1/2/2保持只执行两次source consumer。

| 基线独立重跑 | provider执行次数 | consumer执行次数 | 实际marker内容 | 对照当前期待 |
| --- | ---: | ---: | --- | --- |
| cache-changing-input-records | 3 | 2 | `["1", "2"]` | 匹配 |
| cache-native-dataclass-records | 3 | 1 | `["first"]` | 基线已有缺陷 |
| cache-native-set-records | 2 | 1 | `["tuple"]` | 基线已有缺陷 |

基线重跑来源：`9c443f3111e65e6f99842d86d983416a745d391b`；冻结源码清单匹配：`True`。
本轮新增确认两个原生records场景：不同dataclass类型及其字典投影、tuple与frozenset原先被相同JSON展示形状合并，导致源码consumer少执行。
两个场景共享缓存身份丢失实际类型的机制，不能据此计作两个独立根因；冻结基线重跑证明它们是已有缺陷。本轮保留观察并修复。

基线与最终批共同案例：46；其中18项可比较结构化健康诊断，差异0项。
比较只归一化临时项目路径前缀，诊断码、严重度、源码行列、原因、details及重复次数均保留。新增case逐项按自己的固定期待验收。

## 原始完整批与定向验收

首轮验证保留全部失败，后续逐项修复并进行定向回归，再启动最终完整验证。

| 首轮失败阶段 | 保留证据 |
| --- | --- |
| pytest | [首轮原报告](../../sandbox/python/review_performance/evidence/first-verification.json)，原始命令及错误未改写 |
| python-sandbox | [首轮原报告](../../sandbox/python/review_performance/evidence/first-verification.json)，原始命令及错误未改写 |
| rule-regression-sandboxes | [首轮原报告](../../sandbox/python/review_performance/evidence/first-verification.json)，原始命令及错误未改写 |

资源沙箱旧断言将Node产物含node:fs视为检查代码泄漏；运行日志和心跳实际需要它。
原case ID保留，改为断言Rule/compiler专用sentinel及marker路径不进入产物；浏览器继续要求node:fs完全不存在。

| 第二轮完整批原流程 | 原状态 |
| --- | --- |
| repository-quality | passed |
| compileall | passed |
| pytest | passed |
| python-sandbox | passed |
| javascript-minimal | passed |
| javascript-integration | passed |
| rule-regression-sandboxes | failed |
| runtime-observation-browser | passed |
| review-performance-sandbox | passed |
| wheel-isolation | passed |
| generated-artifact-cleanup | passed |
| distribution | passed |
| repository-quality-final | passed |
| clean-tree | passed |

原完整命令返回1，14流程仍记为13通过/1失败；资源原观察672/680，8项差异和原始错误保存在verification.json及规则沙箱报告中。

资源差异包括7个图形case的9次浏览器观察失败，以及1个Plugin导入case的-122写失败。图形case的正式review、Architecture与Mermaid检查通过，浏览器失败发生在viewport、导航或截图；-122对应EDQUOT，未取得目标导入规则诊断。
这些原始结果保留为执行失败观察，不能直接作为图形或导入规则的健康结论。定向重验使用相同冻结源码、完整case流程及原期待，7个图形case包含两个编辑case各自的登记、修改、恢复三阶段检查/运行/渲染；Plugin重验仍要求精确目标诊断。

| 原失败case的独立定向验收 | 匹配 | 原期待差异 |
| --- | --- | --- |
| `resources.display.host_extension.colours` | True | [] |
| `resources.display.host_extension.override` | True | [] |
| `resources.display.host_extension.shape.circle` | True | [] |
| `resources.display.host_extension.shape.dbl-circ` | True | [] |
| `resources.display.host_extension.shape.trap-b` | True | [] |
| `resources.edits.javascript.base_lib.colour` | True | [] |
| `resources.edits.javascript.base_lib.shape` | True | [] |
| `resources.ownership.javascript.plugin.host_layer.imported` | True | [] |

冻结源码保持相同：`True`；336个源码文件，变化列表为`[]`；独立acceptance记录：`True`。
定向复验末尾的BaseLib shape恢复阶段曾再次截图超时，该失败记录继续保留。相同SVG随后由完全不变的原browser helper重新读取并截图成功，acceptance使用这次原helper观察；软件probe只用于定位，没有替代正式期待。
没有调整case期待、浏览器超时、内核实现或质量阈值；EDQUOT与浏览器失败的具体环境来源及共同因果尚未确证。

定向结果与原批位置见[独立acceptance报告](../../sandbox/python/review_performance/evidence/acceptance.json)。
固定源码的全部流程覆盖与8项定向重验已验收；这不改变原全量命令的退出码或原资源阶段状态。

仓库回归：第二轮pytest共1880项通过。


| 完整发行ZIP及独立安装wheel的真实入口probe | 匹配数 / 观察数 | 是否全部匹配 |
| --- | ---: | --- |
| collaborative | 18 / 18 | True |
| autonomous | 18 / 18 | True |
| installed_wheel | 18 / 18 | True |

独立仓库质量工具：`python quality/test.py`，46项测试通过；该工具继续使用标准库，与被检查的VibeFlow内核分离。

## 使用和后续验收边界

本轮增加的是私有分析会话、解析缓存和展示快照；SDK、资源声明、规则判断、质量阈值及原生Node/Nodeset/Loop执行协议沿用既有契约。
复用局限于本次命令及其已确定资料，跨workflow的解析复用继续区分各自声明与权限；没有持久检查资格或跨运行结果缓存。
当前证据来自VibeFlow独立沙箱、正式入口与完整发行包。未读取、修改或运行VibeTrain，也未进行MNIST或训练验收。下游工作流的实际耗时与业务结果仍由其自身环境复查。

## 机器报告位置

- [冻结基线性能观察](../../sandbox/python/review_performance/evidence/before.json)；已有观察。
- [最终性能观察](../../sandbox/python/review_performance/evidence/after.json)；已有观察。
- [第二轮完整验证原始结果](../../sandbox/python/review_performance/evidence/verification.json)；已有观察。
- [固定源码覆盖与八项定向重验](../../sandbox/python/review_performance/evidence/acceptance.json)；已有观察。
- [首轮完整验证](../../sandbox/python/review_performance/evidence/first-verification.json)；已有观察。
- [原生records基线复现](../../sandbox/python/review_performance/evidence/records-baseline.json)；已有观察。
- [协作版ZIP入口观察](../../sandbox/python/review_performance/evidence/release-collaborative.json)；已有观察。
- [自主版ZIP入口观察](../../sandbox/python/review_performance/evidence/release-autonomous.json)；已有观察。
- [独立安装wheel入口观察](../../sandbox/python/review_performance/evidence/installed-wheel.json)；已有观察。
- [七个图形case完整定向重验](../../sandbox/python/review_performance/evidence/resource-graphics-rechecks.json)；已有观察。
- [Plugin导入目标诊断重验](../../sandbox/python/review_performance/evidence/resource-plugin-recheck.json)；已有观察。
- [第二轮浏览器失败原始审计](../../sandbox/python/review_performance/evidence/browser-failure-audit.json)；已有观察。
- [最终比较](../../sandbox/python/review_performance/evidence/comparison.json)与[批次案例表](../../sandbox/python/review_performance/evidence/case-matrix.json)。
- [冻结源码清单](../../sandbox/python/review_performance/evidence/after-source.json)与[发行来源核对](../../sandbox/python/review_performance/evidence/release-validation.json)。
- 正式图示例：[Architecture](../../sandbox/python/review_performance/evidence/ARCHITECTURE.jsonc)、[SVG](../../sandbox/python/review_performance/evidence/ARCHITECTURE.svg)、[Mermaid](../../sandbox/python/review_performance/evidence/architecture.mmd)与[浏览器截图](../../sandbox/python/review_performance/evidence/architecture.png)。
- 可保留的原始证据：[CLI 与重验产物归档](../../archive/review-performance-observations.zip)、[修复前源码归档](../../archive/review-performance-before-source.zip)；[原始产物清单](../../sandbox/python/review_performance/evidence/raw-artifacts.json)记录归档校验值。

原始产物路径用于追踪未归档的CLI输出和运行文件：

- before: `/tmp/vf-perf-before-final.json`
- final: `/tmp/vf-review-performance-full-final/review-performance.json`
- verification: `/tmp/vf-review-performance-full-final/verification.json`
- acceptance: `/tmp/vf-review-performance-full-final/acceptance.json`
- first_verification: `/tmp/vf-review-performance-full/verification.json`
- native_baseline: `/tmp/vf-records-baseline-reproduction/report.json`
- collaborative: `/tmp/vf-release-review-collaborative.json`
- autonomous: `/tmp/vf-release-review-autonomous.json`
