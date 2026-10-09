# SDK、Rule 与资源装配适配修复

本轮以当前工作区（包含未提交修改）为起点，处理审查报告中的 A01–A10，并同步完成 S01–S03。修复前源码副本位于 `/tmp/vf-adaptation-baseline-20261005/src`；历史审查证据保留在 `adaptation-audit-20261005/`，不会用新结果覆盖旧观察。

实施先建立 `tests/fixtures/adaptation_regressions/`，通过公开 SDK、正式 CLI 和实际 worker 重现问题。Core 共享结构使用公开接口探针，并通过真实 provider/consumer 验证正式规则流程。新案例的期待始终是正确行为；修复前出现不匹配是缺陷证据。

| 批次 | 主题 | 修复边界 |
| --- | --- | --- |
| 1 | A01、S01 | 实际对象与源码声明统一；固定贡献一次收集，各 workflow 独立配置及 Catalog |
| 2 | A08、A03 | Record 共享对象及内部摘要；原生图有限定义和引用 |
| 3 | A04、A05 | 源码查询不发布活动范围；结构规则消费真实所有权和关系 |
| 4 | A02、A06、A07 | 生命周期单次；准备结果共享；inspect 使用所属 workflow 的有效参数 |
| 5 | A09、A10 | 释放异常仍完成清理；Host 闭包在审查前固定 |
| 6 | S02、S03 | JS 单次检查分析会话；删除遗留 raw preflight 旁路 |

Python compiler 保持现有 void hook 签名、优先级和阶段顺序。编译阶段产物保留有效的 after 操作，后续仅同步规则拥有的派生事实。JS compiler 继续提供只读快照与注释，不增加图修改接口。Host disabled/planned/dependency 的既有实例语义保持不变。

每批先运行对应沙箱、受影响单测及前批相关回归。普通测试默认 8 个 worker；确定性性能观察使用独立进程及单 worker。完整验证固定代码版本，安全时尽量跑完并收集全部失败，结束后集中处理。

```bash
npm_config_cache=/tmp/vibeflow-npm-cache python tools/verify_project.py --full
python quality/test.py
```

交付包含机器报告、主题到案例映射、阶段耗时与计数、正式 SVG 和 Architecture、维护及使用文档，以及重建后的两种分发包和隔离安装结果。缓存只属于一次检查，不新增公开 SDK 字段、ABI、持久缓存、审查资格或扫描范围。

## 已完成的定向复现与计数

[主题与稳定案例对应表](adaptation-repair-20261005/case-matrix.md)列出修复接口和夹具纠正原因。首轮稳定清单包含 178 个案例：Core/SDK 57、Python 30、JS 66、源码结构 25。修复前冻结源码运行得到 117 个匹配、61 个不匹配；首轮修复同一清单 178 个全部匹配，观察错误均为零。初始 144 案例的完整观察另外保留，夹具纠正没有覆盖历史记录。

首轮全量验证后增加 20 个 JS 导入归属案例和 9 个特殊路径案例，当前清单共 207 个。补充案例的修复前观察使用首轮修复源码副本：导入归属 20 个中 6 个不匹配，特殊路径 9 个均被误拒。该版本与原始基线分别保存，不把两轮差异相加为独立根因数量。

完整预期、退出码、诊断、计数、marker 与产物路径保存在压缩 JSON 中：

- [修复前摘要](../evidence/index.md#artifact-21b343f43c37c198)、[完整观察](../evidence/index.md#artifact-a36a551b587e9295)。
- [修复后摘要](../evidence/index.md#artifact-2360149194c3112f)、[完整观察](../evidence/index.md#artifact-23bafb01b2ed9c2d)。
- [初始完整基线](../evidence/index.md#artifact-197b7b598a98733e)、[源码清单](../evidence/index.md#artifact-f1c18cf6a2c67040)。
- [修复后源码清单](../evidence/index.md#artifact-ed13e4aeb694ad98)、[阶段耗时及计数](../evidence/index.md#artifact-d10d47ae56da9343)。
- [原始基线源码副本](../evidence/index.md#artifact-4bdbae0fa1b1eec3)、[首轮修复源码副本](../evidence/index.md#artifact-6720105c558d2e7c)：包含当时未提交代码，用于重跑历史观察。
- [补充导入归属修复前观察](../evidence/index.md#artifact-cd6e430080c7d8c8)、[修复后观察](../evidence/index.md#artifact-fd5d0a4b63c13469)；[特殊路径修复前观察](../evidence/index.md#artifact-449f47a86b741bc4)、[身份对照修复后观察](../evidence/index.md#artifact-a41ec9886ce63de7)。

下表为本机新进程、单 worker、各三次运行的中位数。Python 和 JS 数值包含 CLI 启动及本次观察程序开销；Record 单独统计 25 次冻结。它们用于比较本次实现，不是跨机器性能门槛。

| 代表案例 | 修复前 | 修复后 |
| --- | ---: | ---: |
| 深度 12 共享 Record，25 次冻结 | 74.150 ms | 0.569 ms |
| 8 Node、4 共享库、约 350 行源码，inspect-config | 0.904 s | 0.581 s |
| 固定 JS workflow，validate | 4.468 s | 1.483 s |

Record 输出不同 tuple 数由 4095 降为 12，共享身份保留。最终 JSON 仍按现有值树协议输出，其展开成本独立于内部冻结和缓存摘要。Python inspect 的准备、健康检查均由两次降为一次，编译由四次降为一次；调用级 Rule 由重复的 16 次恢复为实际 8 次，每份真实源码解析一次。JS validate 的 driver 和 RuleSession 分别由 23/3 降为 1/1，8 个不同有效 Program 仍分别构造，重复 Program、函数指标和调用图均为零。这些计数不等同于语言后端内部解析次数。

[Python 会话边界](../python-check-sessions.md)和[JS 会话边界](../javascript-check-sessions.md)说明资料发布、缓存、生命周期与释放的维护契约。公开 SDK、配置及 ABI 沿用现有版本。

## 最终完整验收

固定源码下，完整门禁的 15 个阶段全部完成并通过：[阶段报告](../evidence/index.md#artifact-8d9228dfa689b7f5)、[命令与源码对应](../evidence/index.md#artifact-00ed68d6646cd50e)。工具会话在程序输出最终 `PASS` 后返回 143；各阶段报告及完整观察已独立核对，不将工具会话状态写成未经观测的 Python 进程退出码。

| 验收组 | 当前结果 |
| --- | ---: |
| 全量单测 | 1,952 通过 |
| Python 集成沙箱 | 138 通过 |
| JS/TS 集成沙箱 | 67 通过，0 跳过 |
| 历史规则对照 | 1,219 匹配 |
| 规则与资源缺口沙箱 | 680 匹配 |
| 性能与正式展示沙箱 | 57 匹配 |
| 本轮适配回归 | 207 匹配 |
| 独立标准库 quality 测试 | 46 通过 |

历史规则、缺口和适配三组的观察错误均为零。实际浏览器、wheel 隔离、两种发行 profile 及其真实 Python/JS 入口也通过。完整数据见[历史规则](../evidence/index.md#artifact-972f931442ef4109)、[缺口沙箱](../evidence/index.md#artifact-b846caa9fe855a03)、[性能沙箱](../evidence/index.md#artifact-f1104b15d07c1cbf)、[207 项最终观察](../evidence/index.md#artifact-c47846c9f06add35)和[摘要](../evidence/index.md#artifact-6cf87b869c359761)。首轮全量暴露的四组失败保留在[首轮阶段报告](../evidence/index.md#artifact-bcb72a62b1d12245)，修复后重新跑了完整门禁。

正式产物保留原始生成内容及真实源码位置：

- [性能 workflow SVG](../evidence/index.md#artifact-79a4b932f55d8f17)、[Architecture JSONC](../evidence/index.md#artifact-8a2bae3af75d7404)、[浏览器观察](../evidence/index.md#artifact-339096fe14f1d384)。
- [Node、BaseLib、Plugin 与 Host 资源 SVG](../evidence/index.md#artifact-7f7831b0540a4fb3)、[Architecture JSONC](../evidence/index.md#artifact-ef6525f76e514c92)、[样式与来源观察](../evidence/index.md#artifact-655822a4bfd08a36)。

两组截图已目视检查节点、文字、边界和依赖连线；浏览器检查了实际颜色与几何。视图清楚区分业务执行连边、资源贡献和实现文件依赖。

## 正式分发包

通过 `python -B distribution/build.py` 重建协同版和自主版，构建退出码为 0。对两个正式 ZIP 分别解压后执行代表性 SDK、Rule、compiler、Host 和性能验收，每包 **79 项全部匹配，观察错误为零**。必需案例清单单独核对，缺失、额外或重复案例均不能通过。观察子进程只从对应包解压的内核导入 VibeFlow；包内使用手册与 AI 提示词的来源声明说明也已核对。

两个包的内核 ZIP 字节一致，其 348 份源码／资源逐文件与最终源码清单匹配。记录见[发行及 SHA](../evidence/index.md#artifact-d4e1d605fed446f2)、[协同版完整观察](../evidence/index.md#artifact-2f065e0bf1a239ed)与[自主版完整观察](../evidence/index.md#artifact-ec74458e0bc9a7c5)。

- 协同版：`archive/vibeflow-distribution-0.15.0.zip`。
- 自主版：`archive/vibeflow-distribution-autonomous-0.15.0.zip`。

本轮仅使用 VibeFlow 自身源码、沙箱和发行包，保留原工作区修改；没有读取、修改或运行 VibeTrain。
