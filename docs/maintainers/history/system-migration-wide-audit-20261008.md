# VibeFlow 多轮系统迁移全范围审计

审计日期：2026-10-08。对象是当前 **0.16.0 未提交工作树**，HEAD 为 `9c443f3`，包含 457 项既有文件变更。本文回答的是当前实际文件中的新旧机制是否继续耦合，不能把 HEAD 或历史发行包当成当前工作树。

**主要迁移已经发生，没有证实两个完整的旧、新注册或校验系统仍作为正式主入口并行运行；但仍有 11 类明确的局部残余。** 其中三类涉及正式审查行为或 Rule 参数没有完整接入，六类是产品中的旧辅助代码、死分支或协议碎屑，一类是活动测试仍转换旧输入，一类是维护检查器保留过期版本政策。另有明确保留的原生执行、兼容格式和薄转发入口，它们确实使部分旧表达或文件不能直接删除，但不能全部称为迁移失败。

本轮只增加本报告、证据和文档索引，没有修改产品代码、活动测试、发行输入或删除旧文件。原 R01–R19、S01–S04 及修复记录继续作为历史证据保留。

## 历史系统及当前调用链

| 阶段 | 入口和信息来源 | 组件如何相互作用 | 当前核对结果 |
| --- | --- | --- | --- |
| 初始 topology_kernel 与早期扁平 VibeFlow | 类元数据、Registry、Context、BaseLib 扫描，CLI 与 quality/runtime 混在扁平包中 | Registry 同时承载声明与绑定；health/purity 直接调用内置检查；目录和模块名参与角色推断 | 这些旧根目录和根业务模块已退出当前源码；没有 root facade 恢复旧主入口 |
| 0.6 系列的包拆分 | config、health、purity、runtime、rendering、workspace 等包 | 职责开始拆分，但 Python 类元数据、自动库扫描和固定检查仍延续 | 当前早期 scanner、少量 runtime helper 的历史可追到这里，不能只审最近一次重建 |
| 0.9 至 0.14 系列的分层与多 Target | Core、Python/JavaScript Target、Tooling；JS WorkflowSpec 与 descriptor/registry 装配 | Core 保存图和契约，Target 负责语言绑定；JS 有独立前端解析/校验，Python 仍有旧资源适配 | 分层已完成；旧 JS 前端、Python 资源模型及主要适配桥已实质退役 |
| 0.15 系列的 Rule 和 SDK 重建 | 完整 Node/Rule/Ruleset、代码插件贡献、workflow 选择插件 | Catalog 合并资源；RulePlan 选择与执行审查；源码 ownership 替代目录身份 | 正式入口已经使用新链；部分 Rule 内部仍沿用旧遍历或没有消费新事实/参数 |
| 当前 0.16 开发树 | canonical Descriptor、统一贡献/绑定、新配置契约 | 原生图与语言执行继续保留；旧公开模型及额外 scanner/validator/facade 已集中清理 | R/S 原具体问题已关闭；本轮新发现见 M01–M11 |

历史核对包括四个 Git 快照：`9d5a76e`、`2feb215`、`5a20ee5`、`8926a87`；实际打开并解包七个发行包，覆盖 0.10 系列两个阶段、0.11、0.12、0.13、0.14.2、0.15.2。重建的关键提交为 `f169429` 基线、`788a1ab` Rule graph、`28ebb58` Target 迁移、`3ee7396` SDK 与插件选择。逐包精确版本和文件数量见[历史清单](../evidence/index.md#artifact-ae95df6f727d132a)。

当前正式资源装配链是：Application 读取 workspace/workflow → Target SDK 加载选中插件 → ContributionBuilder 冻结贡献 → 内置和外部资源合并为 Catalog → 解析有效调用契约。Rule 按 import/static/run 阶段与编译、绑定及执行穿插；编译也会先生成供静态 Rule 使用的图事实。例如 JS audit 先做 import 审查，再生成 Core/portable plan，随后执行 static workflow Rule。Python preparation 也有编译、validate、最终编译的阶段。Target 最后运行或 AOT，共享展示消费本次实际完成的事实。Python NodeRegistry 保存 canonical Descriptor 与实际绑定，已经不是旧类元数据的另一份权威。

## 当前确认清单

| 编号 | 当前残余 | 性质与影响 |
| --- | --- | --- |
| M01 | BaseLib 继续使用旧 AST scanner，效果遍历没有统一 | 正式 CLI 对同一效果代码产生 BaseLib PASS、Plugin FAIL |
| M02 | Plugin 效果分支未接入真实调用解析事实 | 纯函数仅因叫 write 而失败，改名 identity 即通过 |
| M03 | JS 内置效果和导入 Rule 接受新参数，仍使用旧 driver 固定策略 | policy 进入执行计划却不传入判定；import Rule 还完全不消费 effect_scope |
| M04 | 旧诊断映射的耦合分支被先前 node 前缀分支遮蔽 | 三个 NODE.COUPLING 返回分支永久不可达，实际仍得到 METADATA 名称 |
| M05 | Python runtime 两个旧输入转换 helper 无当前消费者 | 早期引入后长期搬迁保留的私有死链 |
| M06 | 旧资源路径和模块搜索 helper 无当前消费者 | 旧加载器已删，局部 sys.path 修改代码仍留在产品包 |
| M07 | JS 成对发布 Architecture 与 SVG 的旧事务仅剩单测 | 测试保护了正式 review 已不使用的流程 |
| M08 | 旧单浏览器首选 helper 仅剩三个单测 | 正式渲染已改用 Puppeteer 与浏览器候选序列 |
| M09 | JS source driver 仍传旧 ownership topic，并保存未读取的 owner effectScope | 无效果协议残片；不能证明旧 ownership 判定仍执行 |
| M10 | 两个活动测试模块仍先转换旧契约输入，再调用新 parser | 测试输入看似旧接口仍有效；需要迁移测试 authoring 层 |
| M11 | 仓库文档检查器仍硬编码推荐改为 0.15.0，并把历史对照当过期说明 | 过期维护政策与当前开发/发行状态不一致 |

### M01 旧 BaseLib scanner 仍决定正式效果审查

位置：[effects.py](../../../src/vibeflow/targets/python/quality/rules/effects.py#L27) 的 BaseLib 分支与 [base_lib_effects.py](../../../src/vibeflow/targets/python/quality/rules/base_lib_effects.py#L22)。同一个 `vibeflow.no_side_effects`，BaseLib 进入 `_BaseLibAstScanner`；普通源码和 Plugin 进入 ModulePurityVisitor，Node 及其 helper 使用相关共享 visitor。

旧 scanner 的 `visit_ImportFrom` 没有传入具名导入信息，只特殊处理 sys.argv；`visit_Assign` 主要维护 alias，没有共享 visitor 的进程状态赋值检查；`visit_Attribute` 缺少 terminal stream 引用检查。虽然底层部分效果分类函数共用，**决定访问什么、把什么信息交给分类器的 AST 遍历仍是两套**。

本轮正式 `validate --workspace --config --json` 只检查独立临时项目，不执行效果函数。BaseLib 和 Plugin 的 effects 参数均为 scope=none；代码放入各自显式声明的支撑文件，并关闭调用者 Node 的规则以隔离被检查资源。

| 同一代码片段 | BaseLib | Plugin |
| --- | --- | --- |
| `from sys import stdout` | PASS | FAIL，效果导入 |
| `from io import open as file_open` | PASS | FAIL，效果导入 |
| `from http import client` | PASS | FAIL，效果导入 |
| 函数中读取 `sys.stdout` | PASS | FAIL，效果调用 |
| 函数中执行 `sys.path = []` | PASS | FAIL，全局状态 |

这些不是普通源码与资源默认 warning/error 等级差异：对照的两种已声明资源都选择同一个效果 Rule、同一个 scope，却遗漏了不同检查。历史多个发行中这三个 visitor 方法与当前 AST 相同；早期包拆分时就已有其原型。新版把它移入 Rule，补了 ownership、scope 与解析调用，但没有统一这些遍历。详见[历史 AST 核对](../evidence/index.md#artifact-03e2b6602a4a25d7)、[13 项正式 CLI 对照](../evidence/index.md#artifact-ecbffd78769b6a1a)。

收敛方向是共用效果遍历和事实，保留 BaseLib 自己的显式规则、纯库顶层约束及支撑文件审查；不能直接删整个 Rule 或停止检查库。

### M02 Plugin 分支仍用旧名称猜测效果

位置：[effects.py](../../../src/vibeflow/targets/python/quality/rules/effects.py#L51)。分支取得了 source_context，却没有向 ModulePurityVisitor 传 `resolved_calls`；Node、BaseLib、普通源码分支已传入它。[effects 分类器](../../../src/vibeflow/targets/python/quality/source_analysis/effects.py#L339) 已实现“真实可见函数体优先于名称猜测”，Plugin 没有接上。

Plugin 支撑文件中的 `def write(value): return value`，由 lifecycle hook 调用时，正式 CLI 报 `NODE.EFFECT.CALL_FORBIDDEN`。只把定义和调用改名为 identity，其他声明、参数和函数体不变，就 PASS；同一个 write helper 在 BaseLib 也 PASS。旧 Module visitor 的名称猜测因此仍支配一条新系统正式链。

应接入当前闭包的真实调用事实，同时继续检查 helper 函数体。给 write/read/close 加名字白名单会保留根因。详见[CLI 对照](../evidence/index.md#artifact-ecbffd78769b6a1a)及[Python 完整分层报告](../evidence/index.md#artifact-507020f317dc2c48)。

### M03 JS Rule 参数进入新计划但没有完整进入判定

位置：[共享 Rule 声明](../../../src/vibeflow/builtin/effects.py#L7)、[JS 内置绑定](../../../src/vibeflow/targets/javascript/quality/builtin_plugin.py#L21)、[_source_check](../../../src/vibeflow/targets/javascript/build/rule_session.py#L248)。共享声明允许 `policy` 和 `effect_scope`。JS effects 只用 scope 选择 module_state/host_io topics；JS imports 完全不读取 params，固定选择 purity/imports/ownership。

正式 SDK Ruleset 参数覆盖进入 Core RulePlan 的有效参数和执行记录，实际 driver 请求仍只取得上下文 importPolicy 与固定 topics，没有 Rule 的 policy。scope=none 改为 terminal，effects 确实取消 host_io 并改变 console.log 诊断；imports 的 effect_scope/policy 覆盖则不改变其请求。这不是整个参数仲裁系统失效，是新接口最后一段仍靠旧 driver 策略。

本轮没有为任意 policy 键杜撰 JS 应有的效果语义。明确证实的是：共享公开 Rule 接受这个对象并记录它，JS 实现没有读取、验证或传输它；未知/不支持参数也没有清楚报错。应明确 JS 支持的参数并接入同一有效判定，或收紧声明契约，不能用计划中出现参数代替实际生效。见[正式计划及 driver 观察](../evidence/index.md#artifact-3b91e4d8148b3a58)。

### M04 旧诊断映射保留不可达分支

位置：[source_analysis/types.py](../../../src/vibeflow/targets/python/quality/source_analysis/types.py#L194)。任何 node_ 前缀先返回 NODE.METADATA，后面的 node_direct_call、node_import、node_internal_read → NODE.COUPLING 分支永远到不了。本轮三个 PurityViolation 对照均返回 METADATA；重建前也是同样顺序。

这是旧诊断命名和死分支，不是 NodeInfo 重新成为声明权威。当前回归仍断言实际 METADATA 码。可直接定位的清理对象是不可达映射；若改变有效对外诊断码，需同步明确诊断兼容和测试。见[映射和原生输入观察](../evidence/index.md#artifact-63eb03154ad0ab6f)。

### M05 早期 Python 输入转换死链

[runtime/values.py](../../../src/vibeflow/targets/python/runtime/values.py#L11) 的 `_inputs_to_initial` 和第 136 行的 `_copy_input_item`，只剩定义、前者内部调用及 `__all__` 字符串。当前 src/tests/sandbox/tools/distribution 没有实际消费者，也没有该模块的 star/dynamic table 读取这些名字。

`2feb215` 加入时，Nodeset 已使用 `_nodeset_inputs_to_initial`；之后 runtime 拆包和 Target 分层把两函数原样搬过来。删除边界仅为两函数及相关导出，不能整删活跃 values 模块或 Nodeset/Loop 转换函数。这是较早清理遗漏，不能归因于最近 Rule 重建。

### M06 旧资源加载器退役后仍留路径 helper

[resource_helpers.py](../../../src/vibeflow/tooling/project/resource_helpers.py#L10) 的 `_resolve_paths`、`_module_search_path` 原为旧 base_lib.paths/module 注册搜索服务。当前旧 resources.py 已删，新 SDK loading/source_paths 不用这两函数；精确符号和 AST 核对只剩本模块定义、导出。

可以定位两函数、专用 imports 和导出项；同文件 `_finding` 仍用于诊断，不能整删。私有名字曾在 `__all__` 出现，仓内没有消费者不能证明所有外部直接导入也不存在。详见[Core 与 Tooling 报告](../evidence/index.md#artifact-5f37aa3132969e57)。

### M07 JS 旧 review 事务由悬空单测保留

[JS CLI](../../../src/vibeflow/tooling/application/javascript/cli.py#L954) 的 `_publish_review_pair` 仍保存约 70 行两文件 staging/backup/rollback。`3ff4c0a` 的 handle_review 正式调用它；`e25dd05` 改成先写 Architecture、后渲染发布 SVG，正式调用退出。

当前唯一消费者是[test_javascript_review_publish.py](../../../tests/tooling/test_javascript_review_publish.py#L71) 直接调用私有 helper 的测试。它不会把正式入口回退到旧事务，但测试仍证明正式入口不再提供的成对回滚承诺。清理应针对旧函数/直接测试，或让测试观察当前 handle_review；不能借清理静默恢复旧流程。

### M08 旧浏览器首选函数由三个测试保留

[共享 mermaid renderer](../../../src/vibeflow/tooling/presentation/mermaid.py#L398) 的 `_find_chromium` 只返回系统候选首项。正式渲染已在 `e553628` 改为 Puppeteer bundled browser 与全部合适候选，当前走 `_puppeteer_launch_options` 和 `_system_browser_candidates`。

只有[strict_mermaid_cli.py](../../../tests/tooling/strict_mermaid_cli.py#L9) 的三个直接测试还调用旧函数。可迁移这三个测试后删除函数；不能把活跃 renderer、候选 fallback 或可用性 API 一起删除。

### M09 JS driver 的无效果旧协议残片

[builtin_plugin.py](../../../src/vibeflow/targets/javascript/quality/builtin_plugin.py#L32) 的 imports 仍发送 ownership topic；[toolchain_driver.mjs](../../../src/vibeflow/targets/javascript/resources/toolchain_driver.mjs#L2225) 已没有它的消费者，只消费 imports/purity/completion/module_state/host_io。实际 ownership-only 请求无诊断，completion 对同一异步片段仍有诊断，不能把无诊断误认为旧 ownership 审查通过。

driver 的 normalizeImportPolicy 还保存 owner.effectScope，当前没有读取；这个字段在 Rule 重建阶段加入，不能说成早期旧 engine 仍执行。两者是失效传输值或字段，清理不会取消当前显式 ownership 关系和实际其他 topic 检查。详见[JS driver 对照](../evidence/index.md#artifact-e87307d1a005ebd5)与[JS 分层报告](../evidence/index.md#artifact-2764afcb6e3d9ddb)。

### M10 活动测试仍转换旧调用点契约

[strict_node_purity.py](../../../tests/targets/python/strict_node_purity.py#L20) 与 [strict_plugins.py](../../../tests/targets/python/strict_plugins.py#L21) 本地定义同名 parse_graph_config，深拷贝输入、补展示字段，并删除 implemented 非系统 Node 的 requires/provides 后才调用 canonical parser。[strict_support.py](../../../tests/fixtures/support/strict_support.py#L147) 的 `_node_call` 也接受这些旧字段并丢弃；strict_plugins 末段还有当前图重建时的字段删除。

本轮将同一带调用点 requires/provides 的 implemented Node 输入交给三者：canonical parser 拒绝“derived from type_used”；两个本地 wrapper 接受，返回空调用点契约。见[直接输入对照](../evidence/index.md#artifact-124574a868c6c0c1)。

这层只在测试中，不恢复产品旧 parser；相关测试仍可证明转换后算法的行为，不能证明原输入被当前公开 parser 接受。两模块也有直接 raw parser 的负例，不能反过来说全部契约回归均缺失。债务是活动测试长期保留旧 authoring 语义与转换重复，应让普通测试直接写当前形状，把必要的迁移对照单独标明。

已经退役的 code_plugins/source_membership/contributions 三个桥没有复活。本项不是推翻它们已删除的事实，而是更广范围找到的另两种局部转换。

### M11 维护文档检查器保留过期版本政策

[quality profiles](../../../quality/src/vibeflow_quality/profiles.py#L93) 对两个旧版本号仍固定建议“改为 0.15.0”。当前源码为 0.16.0，默认发行目录为 0.15.2，这个建议两边都不准确；字符串检查还不区分历史对照与当前安装说明。

本轮独立临时 README 明确写“当前开发版本为 0.16.0；旧版仅作历史对照”，仍得到 error 和改为 0.15.0 的建议。见[准确输入及诊断](../evidence/index.md#artifact-e25884ae95429fab)。这是旧维护政策，不是旧业务执行系统；应从实际版本来源取得建议，并区分历史叙述。独立仓库 quality 的标准库实现边界本身有意保留，不能据此要求它迁成业务插件。

## 明确保留或尚不足以判缺陷的历史依赖

这些内容确实会让部分历史表达、文件或内部路径不能直接删除。把它们列出来，是为了明确保留理由和收口条件，并非声称所有兼容都必须永久保留。

| 内容 | 当前真实作用及具体边界 |
| --- | --- |
| Python `PipelineInputSpec.required=None` | 明确的 legacy Python 合同；一个输入为 None 时原生 runtime 跳过整个 closed-input 检查，包括同组 required=True 和 unknown keys。实际探针确认；JS AOT 拒绝 None。若目标统一所有语言输入合同，需要先调整兼容承诺 |
| `node.async` 与 `vibeflow.io` | 前者是任务调度，经 Python线程执行/portable schedule/JS scheduler；后者是receive/send宿主通信与completion。使用同一规范 parser 与执行系统，未发现第二个旧 scheduler |
| Python ExecutionPlan 与 portable WorkflowPlan | 前者保存 native frames/callable/实例，后者为传输与AOT投影；BindingPlan补语言实现。当前迁移明确保留原生对象和执行，不是双声明 Registry。正式 build 不用低层输入 override；JS低层手造冲突plan/binding时允许sidecar覆盖completion/executor，正式两者来自同一descriptor，本轮未复现正式链路冲突，见[低层观察](../evidence/index.md#artifact-11ff86f661804aad) |
| 四个 Python presentation 薄入口 | `style.py`、`mermaid/render.py`、`mermaid/review_layout.py`、`mermaid/review_types.py`仍有runner/export/review生产消费者，但全部转发共享Tooling实现；需先迁调用者才可整删，无第二renderer/style/composer |
| 模型和格式别名 | NodeSpec.name/node_type、NodesetSpec.name/exports；HealthFinding/QualityFinding与报告alias；Host name/settings及scope values/override_child_config均规范成同一模型。没有第二份存储权威；删除会改公开或内部合同 |
| 默认Rule主题及纯算法 | flow/join/planned/Nodeset/duplicates/结构算法继续复用；综合主题并非每个细检查的可覆盖子Rule图，builtin仍可原生callable绑定。这是明确组合边界，旧文件中仍有纯算法不等于旧引擎 |
| 通用结构命名政策 | distance_exempt_stems仍含runtime/runner/health/cli等旧命名，确实按名字豁免距离诊断，但可配置且文档/对照明确保留；不赋Node/BaseLib身份，不是S01复发 |
| 无owner的低层project目录查找 | 祖先名project仍用于低层根推断；正式owner路径走workspace，缺owner时明确拒绝custom plugins。尚未证实它改变当前SDK身份，不能仅凭目录词复报S01 |
| 公开native plan的低引用字段 | NodeFrame.export_keys及ExecutionPlan.block_for/block_by_entry/compiled_blocks/compiled_block_by_entry/compiled_node_to_block未找到仓内实际读取；属于公开native模型，仓内无调用不能证明外部可删。具体生产与引用在Python附件 |
| 公共事实和schema facade | JS quality.source只重导出事实采集API，schema_resources提供打包schema文本，均有测试/API用途；无src静态入边不是整文件死代码证据 |
| 历史资产 | 446份冻结resource_migration夹具、历史发行包、旧审计及失败日志用于对照；本轮没有发现产品从它们恢复旧注册/解析系统 |

## 源码与默认发行目录的版本边界

两个默认 `dist/vibeflow-distribution*` 目录实际仍为 **0.15.2**，各有 348 个产品文件；当前源码有 **333 个产品文件，其中 314 个 Python 文件**。两端有 199 个相同文件、114 个同路径不同文件、35 个旧端独有文件、20 个新端独有文件。两个目录逐字节匹配实际 0.15.2 发行包，见[完整差异清单](../evidence/index.md#artifact-787cd9aff7fa89f3)。

发行 run.py 使用本包 kernel；因此从这些旧目录启动，得到的是旧发行行为。当前源码正式 module/wheel 入口没有依赖这些旧kernel。这个现象属于发布版本与开发树并存，**不是当前代码隐式调用旧系统**。本轮没有得到重发发行包的指令，也没有把旧发行资产删除或覆盖。

此前补修构建的 0.16 wheel 位于隔离 /tmp。独立核对其 333 个产品文件与当前源码全部逐字节相同，无缺失/额外/差异。在新增本次审计索引前，此前完整验收记录的 2379 个输入与当前文件全部匹配；报告收尾再核对时，唯一变化是本次新增一条链接的 docs/README.md，产品、活动测试和发行输入仍一致。见[本轮独立核对](../evidence/index.md#artifact-0e0073aab11e7faa)。这证明记录和包对应所述输入，**不能替代本轮新增行为探针，也不能证明潜在残余已经清零**。

## 原审计问题及本轮覆盖

原 R01–R19 的主要旧模型、自动发现、重复parser/validator、quality循环桥、31个退役文件、5个旧内置路径、3个旧活动测试桥已经实际退出源码。当前精确退役核对为 PASS，检查66个指定符号及9个退役诊断码，见[当前结果](../evidence/index.md#artifact-ee8350d888c7901d)。这些计数只证明指定项退出，不证明所有残余不存在。

S01–S03 原始复现程序本轮重新运行：六种目录各以 workspace/path 两入口共12次均退出0；退役 Host 字段的preview/validate均退出1并报同一共享配置码；普通源码open在python_io无诊断，none/terminal/trusted仍有诊断。S04精确退役项核对亦通过。见[原始程序本轮重放](../evidence/index.md#artifact-f55438c158ef1b89)。M01/M02位于其他资源分支，不代表S03普通源码修复没有发生。

覆盖当前整个产品树333个文件、314个Python模块的导入/导出及静态候选；人工按Core/SDK/Rules、Python、JS、Application、Tooling、发行/quality/测试分工追踪正式入口与消费者，并用历史多版本核对来源。Python层单独记录144个模块清单；静态无入边候选逐一排查了模块入口、动态plugin加载、atexit、公开事实和schemaAPI，未确认新的整文件闲置产品模块。可以删除的已确认项主要在仍活跃模块内部，不能因此整删它们所在文件。

本轮没有重跑17步全量验收，没有执行带副作用的业务函数，也没有证明全部第三方公开API用法或Python/JS动态构造均正确。所谓全范围，是已说明的仓库和历史范围内的系统追踪与发现清单；不是以有限静态检查担保永无其他问题。各层详细证据与排除项保留在[Python报告](../evidence/index.md#artifact-507020f317dc2c48)、[JS报告](../evidence/index.md#artifact-2764afcb6e3d9ddb)、[Core与Tooling报告](../evidence/index.md#artifact-5f37aa3132969e57)及[结构化总清单](../evidence/index.md#artifact-0f1e5e57d7c49bca)。

可复现程序保留为[Python资源效果CLI对照](../evidence/index.md#artifact-bc054699bb8f1b48)、[JS正式Rule参数对照](../evidence/index.md#artifact-f2a0aff112f55e08)、[JS driver对照](../evidence/index.md#artifact-70d12a1fc81789e9)和[JS低层绑定边界](../evidence/index.md#artifact-8aa342909defd781)。程序只在/tmp构造项目；JS程序使用本轮已存在的临时TypeScript工具链路径，重放前需提供该工具链或调整脚本中的路径。原始观察已另存于本仓库，不依赖临时项目继续存在。

## 收敛顺序与验收依据

先处理 M01–M03 的有效事实与参数接入，使用本轮同规则、同scope、同函数体对照验收，避免改目录、改函数名或补白名单掩盖。再清理 M04–M09 的死分支/helper/传输值以及保活它们的测试；涉及对外诊断码和公开native API时明确兼容边界。随后把 M10 的普通活动测试写成当前接口，保留独立历史迁移对照；更新 M11 的版本建议与历史语境判定。

原生输入兼容、完整替换Python engine、每个细检查独立可覆盖、所有薄facade的公开路径退役，都带来不同于本轮局部清理的用户行为或公开合同变化。本次只列明机制与后果，未替用户扩大整改目标或执行这些变更。
