# 产品职责边界整改结果（2026-10-09）

依据 product-boundary-refactor-spec-20261009.md、已批准执行计划，以及两次明确批准的测试迁移清单实施。版本为 0.17.0，Workflow ABI v5、AOT manifest v2。本报告记录首次整改：full-4 的 17 个验收步骤全部通过，4020 项 pytest 通过，无跳过；后续源码/包审计和 autonomous 包独立运行也通过。但独立审核随后发现五项缺陷，这些历史成绩不能作为无缺陷或整改全部完成的证明；本目录的旧包保留作审计证据。修正与新交付请看 [审核修正记录](product-boundary-review-fixes-20261009.md)，不要将这里的旧包当作修正后的交付物。

## B01—B11 落地情况

| 项目 | 实现和保留边界 |
|---|---|
| B01 | Python 有限直接输入写入、简单直线别名、重绑定及共享词法身份；退役参数污染、异常出口、闭包和生成器消费证明。JS 显式选择该 Python 规则报告 unavailable。 |
| B02 | 退役静态返回 Mapping/输出键构造证明；实际 Runtime Mapping 和精确输出键要求保留。 |
| B03 | runtime_dispatch 分析器、缓存、模型、序列化和展示退出活动源码；真实执行锁、调度与全局状态协调保留。 |
| B04 | 私有 while/递归不再默认拒绝；真实工作流图环、Nodeset/Loop 结构和显式复杂度阈值保留。 |
| B05 | 删除任意属性和资源字段名称猜测；使用真实资源身份检查跨 Node 导入、调用与内部访问。 |
| B06 | 效果检查限于所选导入政策、明确外部操作及共享状态；退役未知方法叶名猜测、FFI/动态代码安全黑名单与静态 ExitStack 补偿。真实 cleanup、无人收尾定时任务、实际导入协议保留。 |
| B07 | JS Date/performance/Math 不承担默认确定性证明；实际宿主与进程操作仍按所选效果政策处理。 |
| B08 | 同名输入类型/输出键、自定义 Decision 端口名及示例 outputs 放行；声明和真实接口形状仍检查。 |
| B09 | 工具链报告只记录实际 Node/TypeScript/esbuild 版本；没有 npm lock、yarn/pnpm lock 形态不作准入条件。 |
| B10 | architecture/input_writes/effects/interface 是可独立选择的 Rule，复用现有 SourceContext；JS architecture 在导入阶段接入；空 Ruleset 不暗中恢复可选限制。 |
| B11 | 退休源码、测试、消费者及格式迁移，checked 来自实际完成的 Rule；明确不检查业务正确性、安全、通用执行语义、确定性或全部副作用。 |

## 实践复核与成本

完整批次 full-2 收集到 9 项 JS 集成问题和 1 项 Python 共享声明误报后继续跑完，17 步中 15 步通过。修复保留真实违规期待，只更新已退役字段和 Rule 归属。full-3 的 16/17 步通过，但共享文件例外范围过宽，导致多 Node 文件未使用的非法导入漏报；随后将特殊处理限定于声明的 Plugin entry。Plugin 注册导入不自动归于 Node；Node 实际使用，以及没有 Plugin entry 的实现文件中的非法导入，仍报告。三个真实耦合反例、合法分支输出 6、42 项定向回归通过后才进入 full-4。

动态求值残留通过真实工具链及生成 Runtime 验证：eval/Function 工作流输出 answer=3，因此按已批准 B06 补齐安全禁令退役，保留真实定时器生命周期反例。实践没有要求扩大或改变产品目标，不引入新的证明服务。六个主要分析文件总文本行数从 3612 降至 1046；共享词法事实与 Runtime 保留，不以行数作为正确性依据。

最终完整批次记录的步骤耗时合计 1538.43 秒，约 25.6 分钟。使用既有 8 workers 后 pytest 耗时从此前约 149 秒降至 97.10 秒，但规则对照及渲染组仍用时 744.1 秒，并未因增加并发显著加快。验证成本因此仍以真实场景、浏览器和 SVG 为主；没有为缩短验收引入新缓存准入或恢复已退役机制。

## 最终验收结果

验收期间未修改源码；结束后复核 2388 个输入文件的 SHA-256，无漂移。完整步骤结果见 [full-verification-4.json](product-boundary-remediation-20261009/full-verification-4.json)，过程见 [完整日志](product-boundary-remediation-20261009/full-verification-4.log)。

| 验收项 | 实际结果 |
|---|---|
| 仓库质量、compileall、结束质量与生成物清理 | 全部通过；质量 0 error / 0 warning，清理预览 0 项 |
| pytest | 4020 passed，无跳过 |
| Python / JavaScript | Python 138/138；JS 最小 AOT 真实执行、集成 67/67 |
| 规则对照 | 历史 parity 1219/1219；当前职责边界 680/680；无进程错误 |
| 浏览器、SVG、资源、性能与适配 | 真实浏览器、4 个布局案例、Python/JS 资源展示、性能场景通过；适配 207/207 |
| wheel 隔离、两种本地发行包 | 全部通过；包源码与当前 335 个源文件逐字一致，退役文件/字段无残留 |
| autonomous 独立补验 | Python 工作流 PASS；JS 构建 PASS，生成工作流执行探针 PASS |

源码和 wheel 的退役审计见 [final-retirement-audit.json](product-boundary-remediation-20261009/final-retirement-audit.json)，双发行包内核及文档核对见 [final-content-audit.json](product-boundary-remediation-20261009/final-content-audit.json)。两份审计中记载的临时输入路径已在保存正式交付物后清理；保留文件路径和 SHA-256 见 [交付清单](product-boundary-remediation-20261009/local-distributions/manifest.json)。

## 本地交付与临时环境清理

- [vibeflow 0.17.0 wheel](product-boundary-remediation-20261009/local-distributions/vibeflow-0.17.0-py3-none-any.whl)
- [collaborative 发行包](product-boundary-remediation-20261009/local-distributions/vibeflow-distribution-0.17.0.zip)
- [autonomous 发行包](product-boundary-remediation-20261009/local-distributions/vibeflow-distribution-autonomous-0.17.0.zip)

用户提出及时清理临时目录后，先审计活动进程、挂载与资产归属，再删除 107 个已结束目录，目录占用约 12.27 GiB。原始源码、测试及必要历史证据归档保留，可重建依赖缓存不长期留存。第三批次和最终批次的生成证据、主要报告及辅助脚本另行保存后，清理对应 scratch、共用渲染/npm 环境和本次 pytest 临时副本；最终这轮又清理 17 个目录或辅助文件，目录占用约 2.07 GiB。逐项路径与清理结果见 [历史清理记录](product-boundary-remediation-20261009/temp-cleanup-receipt.json)、[最终清理记录](product-boundary-remediation-20261009/final-temporary-cleanup.json)。独立 JS 探针在仓库生成的成功状态保存为 autonomous-javascript-status.json 后清理；最终仓库质量为 0 error / 0 warning，清理预览为 0 项，git diff --check 通过。

## 证据与迁移限制

证据目录为 product-boundary-remediation-20261009。baseline* 保存最初已含未提交工作的源码；七文件、十一文件及最后修复原文分别归档。冻结历史 parity 不改，只更新当前产品职责对应验收。旧 Workflow/Architecture/AOT 资料需要重新生成，不提供旧分析器或格式兼容层。

yarn/pnpm 案例验证已解析工具链及 lock 形态的真实构建、运行和本地 publish，没有验证这些包管理器的安装过程。PASS 不表示业务正确、安全或所有未知副作用已排除。整改仅本地实施，未推送或远端发布。
