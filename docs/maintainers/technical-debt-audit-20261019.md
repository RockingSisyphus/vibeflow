# 技术债审查：架构事实、展示与仓库遗留

审查日期：2026-10-19。产品基线为 `e60aba95b1fc0aeff36320d0d756584a06728fe7`，对照此前的 `46337bf`，并对部分遗留使用 `git blame` 追溯来源。预览功能已独立提交，未推送；原有 `tests/fixtures/rule_parity/javascript/variants.py` 修改保留在工作区，没有混入功能提交。

本轮只审查和记录，不修改产品实现、不删除资料、不更新正式发行物。范围包含 src、tests、sandbox、tools、repo_check、distribution 的源码与提示词、当前 docs，以及本地生成物的职责。扫描了 src 中 384 个 Python 文件的定义／引用和导入，核对两端事实与渲染调用链、旧接口关键词、当前 Markdown 相对链接及受 Git 管理的 HTML/SVG/Mermaid 文件。关键词命中和静态未引用只是线索，下列条目另核对了实际入口、消费者或替代实现。

结论是 **16 组问题**，包括实际显示错误、旧机制的兼容残留，以及目录和文档未同步。P1 表示优先处理的协议／行为分歧；P2 表示有具体维护代价或展示缺口；P3 表示边界尚可收紧、当前未造成失败。不是 16 个运行时故障，也不表示动态路径已穷尽证明。

## 清单

| ID | 优先级 | 问题 | 主要位置 |
| --- | --- | --- | --- |
| D01 | P1 | 协同 profile 仍强制 expanded_svg，与默认 HTML 和可选 SVG 冲突 | distribution/profiles.jsonc:42；distribution/profile_config.py:210；distribution/prompts/collaborative.md:5 |
| D02 | P1 | JavaScript SVG 仍按起终点对分类连边，复用了已被替代的角色判断 | src/vibeflow/tooling/application/javascript/review.py:501 |
| D03 | P2 | 原生图的部分连接点仍是包围盒加比例补偿，没有与自身轮廓统一 | tools/workflow-viewer/shapes.js:63 |
| D04 | P2 | 资源卡片仍按调用结构读取外部节点身份，遗漏 type_key／自身 external | tools/workflow-viewer/shapes.js:15 |
| D05 | P2 | JavaScript 公共事实入口之外仍有两套事实后加工 | src/vibeflow/tooling/application/javascript/audit.py:323；build_preview.py:32 |
| D06 | P2 | SVG 分片抽出后，旧模块仍通过替换另一模块的全局函数维持测试兼容 | src/vibeflow/tooling/application/python/presentation/mermaid/review_svg.py:60 |
| D07 | P2 | SVG 公共常量抽出后，旧副本仍保留，甚至覆盖导入值 | 同上 review_svg.py:26、30；tooling/presentation/review_types.py |
| D08 | P2 | 编译记录序列化已独立，但旧 Mermaid 导入口仍被测试依赖 | src/vibeflow/tooling/application/python/presentation/mermaid/__init__.py:2 |
| D09 | P2 | 留有一个孤立源码分析文件和四个无仓库内调用的私有辅助函数 | targets/python/quality/source_analysis/source.py 等，见下文 |
| D10 | P3 | 抽取代码后留下未使用导入和旧 SVG 标签字段 | application/javascript/audit.py:5；presentation/mermaid.py:256 等 |
| D11 | P2 | 事实包仍再导出 Rules 策略，现行沙盒依赖旧入口 | targets/python/quality/source_analysis/__init__.py:3 |
| D12 | P3 | JavaScript 展示子系统尚未独立归目录，文件名仍混淆审查与绘制 | tooling/application/javascript/review.py、architecture_facts.py 等 |
| D13 | P3 | Viewer 安装器手工维护第二份资源 URL 名单 | src/vibeflow/tooling/presentation/viewer.py:28 |
| D14 | P3 | 渲染中立样式仍包含 Mermaid 格式化与词汇转换 | src/vibeflow/tooling/presentation/node_presentation.py:22、68 |
| D15 | P2 | 当前维护／用户导航／沙盒文档与测试字段未完整同步 | docs/maintainers/python-check-sessions.md:33 等，见下文 |
| D16 | P2 | 首页仍展示含已撤销概念的旧生成图 | docs/assets/comprehensive_flowchart.mmd:15；README.md:11 |

## D01：发行协议仍绑定旧审核产物

[profiles.jsonc](../../distribution/profiles.jsonc) 的 collaborative profile 仍声明 `required_review_artifact: expanded_svg`。[profile_config.py](../../distribution/profile_config.py) 不只是读取它，还限定合法值，并要求 collaborative 的整组值必须包含 expanded_svg。两个发行集成测试也固定这一预期：`tests/integration/strict_distribution_profiles.py:59`、`strict_distribution_release.py:54`。

[协同用户协议](../../distribution/docs/user/profiles/collaborative.md) 第 8、18 行要求普通 review 生成完整展开 SVG；[协同提示词](../../distribution/prompts/collaborative.md) 同样要求。common 提示词第 27—29 行仍把正式审核材料统一描述为旧 SVG 的资源目录、横竖排版及配置 expand 行为，没有区分 HTML 的选项卡、默认折叠和手动展开。

同一用户按新命令手册运行 `review --config ...`，实际拿到 HTML 与快照，却不满足发行协议写死的材料类型。建议保留协同模式的人工审查与批准，只把默认承载材料改成正式 HTML／结构化快照，SVG 保留按需对照，并同步协议解析器、提示词和相关测试。不是删除人工审查机制。

## D02：JavaScript SVG 与新事实的连边角色分歧

[JS SVG 绘制](../../src/vibeflow/tooling/application/javascript/review.py) 仍将 mainline/data_bypass 转成 `(source,target)` 集合，第 523 行先命中 mainline，就将相同端点的另一条数据边也画成实线。新事实出口和 Python SVG 已按完整 EdgeSpec 判断，旧算法在这里仍有效执行。

使用 `tests/tooling/test_parallel_graph_visuals.py` 的真实 GraphCompiler 夹具，在 start → dispatch 上分别加入条件不同的调度边和仅传输边，直接调用两端 Mermaid 文本生成器，实际结果：

| 观察 | 调度边 | 仅传输边 |
| --- | --- | --- |
| 两端 Architecture roles | mainline、schedule | data_bypass、transfer |
| Python SVG 输入样式 | stroke-width:4px | stroke-dasharray:6 4、stroke-width:2px |
| JavaScript SVG 输入样式 | stroke-width:4px | **stroke-width:4px** |

这是文本生成阶段已确认的错误，不需要启动 Mermaid 才能判定；没有在本轮另渲染像素截图。`git blame` 显示该 pair 判断来自旧提交 `e25dd051`，本轮事实修正没有覆盖这条旧渲染路径。建议直接使用同一精确边角色来源，扩展现有回归覆盖原 SVG 对照。

## D03—D04：新绘图器仍有两处未收口

[shapes.js](../../tools/workflow-viewer/shapes.js) 的 connection 对圆、菱形及一组多边形求交；stadium、rounded 等保留矩形包围盒逻辑，cloud/doc/cyl 还分别使用 0.91／0.85／0.98 比例补偿。这些补偿与实际 outline 没有共同几何定义，轮廓或尺寸变化时容易漂移。

纯函数复现：stadium 宽 300、高 100，指向 `(500,-50)`，得到端点 `(300,7.142857)`。相对右端半圆圆心 `(250,50)`，归一化距离为 **1.317078**，不是轮廓上的 1。此处只验证几何，不声称已经用真实浏览器遍历全部形状与布线角度。建议让自己的 outline 与连接点复用同一轮廓几何，保留已经独立绘图的方向，不恢复原 SVG 采样。

同文件 measure 通过 `types[facts.type_used]` 判断 external，而资源节点使用 type_key，且自身就有 external。详情模块刚统一了这两种身份，测量模块仍使用旧字段路径。对同一个 `external:true、flow_kind:process` 类型调用 measure：流程调用的状态行为“外部依赖”，资源事实的状态行为“process”。该对照在 Node VM 中执行真实 model.js／shapes.js，文字测量使用桩；没有启动浏览器。建议与 nodeInfo 共用身份归一化，补充资源节点的对应展示断言。

## D05：事实入口收拢仍不完整

[architecture_facts.py](../../src/vibeflow/tooling/application/javascript/architecture_facts.py) 已提供公共入口，构建也已摆脱临时审查对象，这是有效改进。但 audit 第 323—332 行和 [build_preview](../../src/vibeflow/tooling/application/javascript/build_preview.py) 第 32—36 行仍分别追加 implementation_graph、整理来源和调用 portable_paths；审查还单独追加 rule_selections、rule_checks。

读取本地同一 `preview-javascript:configs/greeting.jsonc` 的真实 review/build 快照：review 有上述两个规则字段，build 没有。这证明出口仍有不同的后加工边界；不同命令的检查内容本可不同，不能仅据此判定构建失败。建议把通用架构事实组装完整收进 Target 事实入口，操作特有的检查结果显式单独传入，避免下一次新增字段又漏接某个命令。

## D06—D08：抽取模块后旧测试接口仍维持耦合

[review_svg.py](../../src/vibeflow/tooling/application/python/presentation/mermaid/review_svg.py) 第 60—78 行保留旧 `_render_fragment` 包装器。调用旧 `_render_nodeset_detail_fragment` 时，会临时替换 `review_fragments._render_fragment`，用完再恢复。`tests/targets/python/strict_plugins.py:696` 仍 monkeypatch 旧模块，布局观察器也同时设置新旧两个位置；这些消费者让兼容层继续存活。实际分片实现已在 [review_fragments.py](../../src/vibeflow/tooling/application/python/presentation/mermaid/review_fragments.py)。这增加跨模块全局状态和理解成本；本轮没有复现并发污染，不能把潜在影响写成已发生故障。此桥的 blame 来自 `e8fd9090`。

同一旧文件第 30—54 行仍留着尺寸、样式、命名空间和引用正则副本。其中 `REVIEW_COLUMNS_MAX_FRAGMENT_WIDTH` 刚从 review_types 导入，就重新赋值 3200，覆盖公共来源；其余大量名称已无该文件内读取。公共实现已使用 [review_types.py](../../src/vibeflow/tooling/presentation/review_types.py) 和 [review_layout.py](../../src/vibeflow/tooling/presentation/review_layout.py)。应移除旧副本并改测试导入，防止修改公共常量后某条路径仍用旧默认。

[compiled_document.py](../../src/vibeflow/tooling/application/python/presentation/compiled_document.py) 已是编译记录序列化的实现，runner 也直接引用它；但 Mermaid 包第 2 行仍再导出 compiled_graph_payload。`tests/tooling/test_plugin_architecture.py:14` 与 `tests/core/strict_compiler.py:1306、1328` 继续从渲染器入口测试序列化，维持了已被拆开的概念依赖。建议迁移内部测试后再决定是否保留有文档承诺的外部兼容入口，不能把转发误说成仍有两份序列化实现。

## D09—D11：源码分析拆分后的残留

仓库内定义／引用核对发现以下五个私有入口只有定义、无使用或注册入口：

| 位置 | 遗留项 | 当前机制 |
| --- | --- | --- |
| [source_analysis/source.py](../../src/vibeflow/targets/python/quality/source_analysis/source.py):11 | _source_info；整个文件已孤立 | source_context 提供快照；rules/node/helpers.py 从文件事实构造 _SourceInfo |
| [source_analysis/bindings.py](../../src/vibeflow/targets/python/quality/source_analysis/bindings.py):57 | _function_bindings | 调用方直接消费 _function_scope_bindings 的完整结果 |
| [source_analysis/helpers.py](../../src/vibeflow/targets/python/quality/source_analysis/helpers.py):24 | _matches_prefix | 当前策略使用其他显式匹配入口；此私有函数无调用 |
| [build/rule_session.py](../../src/vibeflow/targets/javascript/build/rule_session.py):132 | _workflow_blocks | 当前入口直接消费 graph_rule_subjects |
| [mermaid/labels.py](../../src/vibeflow/tooling/application/python/presentation/mermaid/labels.py):78 | _resources_payload 旧转发 | 调用方使用 review_model.resources_payload／实际资源展示入口 |

另有代码抽出后未收走的导入，例如 JS audit 的 selection_data、escape_xml、json、build_architecture_report、mermaid_shape_for_flow_kind，JS review 的 escape_xml、re、mermaid_shape_for_flow_kind，Python architecture_document 的 json、prepared 的 contextmanager。旧 SVG 标签前缀表还保留 async/result_key（[mermaid.py](../../src/vibeflow/tooling/presentation/mermaid.py):256）；它不是旧调度器，只是标签格式化残留。再导出给 __all__ 或其他模块消费的名称没有一概算成未使用。

[source_analysis/__init__.py](../../src/vibeflow/targets/python/quality/source_analysis/__init__.py) 一面宣称只提供事实和类型，一面从 rules.node.policy 再导出 PurityPolicy。现行 `sandbox/python/integration/run_all.py:1150、2044、2117、2143` 仍从这个旧分析包导入策略，令事实包反向依赖具体 Rule 策略。建议现行消费者改到策略所属模块，基线生成器／冻结 reference 按其历史用途单独处理，不批量改历史输入。

## D12—D14：目录与独立工具边界

JavaScript 的 review.py 实际包含 Mermaid、ASCII、分片与资源绘制；architecture_facts.py、presentation_status.py、preview.py 和 build_preview.py 同属展示／展示编排，却全部平铺在 application/javascript。Python 已有 presentation 子目录，两侧职责表达不对称。建议按真实责任收拢展示适配器和渲染实现，命令与构建编排保留在应用层。目录调整本身不要求改 Core 或建立统一大服务。

[viewer.py](../../src/vibeflow/tooling/presentation/viewer.py) 第 30—32 行手工列出 HTML 中需改写 URL 的样式、引擎和脚本名。新增 inspector.js 已同时修改 index.html 和 Python 清单。当前资产没有漏项，但未来增加／重命名工具模块仍须跨两个维护位置联动；未列出的文件虽被复制，HTML 引用却可能保留错误根路径。建议从统一入口资源引用生成安装布局，避免再维护第二份手工名字表；无需增加完整性门禁。

[node_presentation.py](../../src/vibeflow/tooling/presentation/node_presentation.py) 的中立有效样式仍带 mermaid_style，并将公开 diamond 改为 Mermaid 的 diam；shape_semantics 同样输出 diam。HTML 因而同时接受 diamond/diam。没有 Mermaid 启动或性能开销，当前也能正确绘图；这是词汇和格式化职责的轻量遗留。可把规范形状保留在事实层，将 Mermaid 方言和颜色属性序列化移至 SVG 适配器。

## D15：文档、提示与测试命名未同步的具体位置

除 D01 的发行协议外，当前还存在以下遗漏：

| 位置 | 与当前行为的差异 |
| --- | --- |
| [python-check-sessions.md](python-check-sessions.md):33 | 把 review 描述为始终渲染并原子发布 SVG；现在默认发布数据，可选附件另走结果 |
| [system-architecture.md](../design/system-architecture.md):63 | 架构事实章节仍围绕 JSONC/SVG，没有描述快照存储、独立 Viewer 和资源视图边界；旧 SVG 专属说明本身仍可保留 |
| [sandbox/python/comprehensive_math/README.md](../../sandbox/python/comprehensive_math/README.md):3、14 | 声称 checked 运行包含 Mermaid/SVG；实际 run_all.py:84 检查预览 architecture.jsonc 和 snapshot.js |
| [sandbox/python/workflow_math/README.md](../../sandbox/python/workflow_math/README.md):3 | 声称 checked run 每配置渲染一次 SVG；实际已读取快照 |
| [sandbox/python/piecewise_math/README.md](../../sandbox/python/piecewise_math/README.md):20 | 声称 checked run 检验实际 SVG，实际产物检查已迁移 |
| [comprehensive-math-sandbox.md](comprehensive-math-sandbox.md) 的运行与效率章节 | 仍描述 Python 首次渲染和复用 SVG；与当前 runner 不一致 |
| [workflow_math/run_all.py](../../sandbox/python/workflow_math/run_all.py):93、同目录 expectations.json 及 integration/run_all.py 的消费者 | expected_svg_text_contains 仍叫 SVG 检验，实际只搜索 Architecture JSON；是有效事实断言，但不能据名称声称验证了绘图 |
| [README.en.md](../../README.en.md):19 | 中文首页已增加离线预览，英文能力列表和导航仍遗漏 |
| [directory-layout.md](directory-layout.md):5 | 根目录“不保存运行输出”没有说明已授权的 HTML、用户配置和快照目录例外，容易在后续清理时误判 |

**还有实际的旧测试依赖，不止文字：** [comprehensive_math/run_all.py](../../sandbox/python/comprehensive_math/run_all.py):157—169 和 [addition_sandboxes.py](../../tests/fixtures/support/addition_sandboxes.py):64—78 仍处理 renderer-root，并在没有渲染器时执行 npm ci 安装 Mermaid/Puppeteer。后者被 Python addition／数学沙盒复用，其对应产物检查已改为快照。独立运行这些数据／运行测试仍可能因不必要的 Node/npm/下载条件失败。应从不再渲染的 runner 移除这段准备和参数；真正的 SVG／浏览器验收继续保留自己的依赖。JS 业务构建所需的 TypeScript/esbuild 安装也继续保留，不能一并删除。

## D16：首页长用图已失去当前性

[中文](../../README.md)和[英文](../../README.en.md)首页第 11 行都直接展示 [comprehensive_flowchart.svg](../assets/comprehensive_flowchart.svg)，其源 [Mermaid](../assets/comprehensive_flowchart.mmd) 仍包含 runtime_dispatch 与旧 effect_scope: terminal。解析 SVG 可见文本实际找到 **12 次 runtime_dispatch**，不是只在不可见元数据中残留。

当前对应 Runtime Dispatch 分析模块已撤销；同名真实 workflow 仍在 sandbox/python/integration，因此建议从当前工作流重新生成展示图，并维护实际来源／更新说明。该图片有明确首页读者，不应直接按“旧生成物”删除；它与无人再使用的 demo 不同。

## 没有归为技术债的项目

- 新版快照没有继续携带原 SVG 图元、边界采样或旧 body.facts 负载；Viewer 内部局部投影对象仍叫 facts，不等于保留旧快照协议。
- 默认 review/build 和 Python 源码运行不启动 Mermaid；显式 export-svg、review --with-svg、旧显式 --output，以及对应 SVG 专项测试仍有承诺用途，应保留。
- 本轮沿入口核对并结合现有 retired architecture 审计，未发现旧 TaskManager 执行器或旧源码路径仍参与执行。迁移拒绝报错中的 async/result_key、普通局部变量 result_key，以及测试负例不等于旧机制复活。
- 流程／资源视图和 AOT 执行没有因为这轮审查被改动。此前 AOT 隔离回归是有效已有证据，但不拿它代替每条新审查结论的复现。
- 受 Git 管理的 HTML 主要是独立工具入口和真实浏览器项目模板；未发现源码树中的 .bak/.orig/.rej 或散落旧 demo。多文件资源案例的登记 SVG 仍是使用资料。
- 根目录 vibeflow-preview、HTML、配置是刚交付的有效历史，已经 Git ignore；不是应清理的临时目录。早期会话 demo 位于仓库之外的宿主可视化交付目录，没有把它当成本仓源码。
- docs 的 history、测试 reference.json、references 与 archive 有明确历史／基线／外来参考／正式发行用途，不因包含旧名称就删除。
- 本机 dist 保存的是 1.0.0 发行物，当前源码元数据为 1.0.2，且还包含新提交功能。它们不能代表当前源码构建结果；按现有目录约定，源码提交不自动替换正式发行物。这是发布时需明确的版本差异，不在本轮直接删除或当成测试临时包。

## 验证边界与处理优先级

本轮 `tools/audit_retired_architecture.py` 返回 PASS；当前 docs 与 distribution/docs 中的普通相对文件链接扫描没有缺失目标。它们只能说明各自检查范围通过，不能证明语义文档都已更新，也没有覆盖 D02—D04。D02 使用真实编译器和 Mermaid 文本生成器复现；D03—D04 使用真实前端纯函数复现，未以桩测量冒充真实浏览器验收。

上一实施阶段的 18 步门禁和最终 549 项定向检查通过，不改写历史结果；本轮发现的遗漏说明现有通过范围并未覆盖所有角色组合、曲线连接方向和资源身份。审查期间没有再启动昂贵完整门禁，因为没有修改产品代码。

建议先处理 D01—D04 的材料协议和可观察显示分歧，再收拢事实出口、迁移旧测试入口并删除死副本／死文件，最后整理目录和同步文档、首页图与沙盒依赖。目录移动与删除应以本清单的真实消费者为依据，避免保留新的路径桥或顺手清掉有效历史。本文件是审查清单，不是已批准的重构实施计划。
