# Python 正式 SVG 布局回归

这组沙箱使用公开 SDK 声明 Node、BaseLib、compiler/runtime Plugin，通过四个正式 CLI 入口检查布局。它同时包含两层 Nodeset、同一定义的重复调用、Loop，以及 Node 的默认圆角形状和调用点颜色覆盖。所有场景使用新进程和独立项目目录。

```bash
python -B tests/fixtures/python/review_layout/run_all.py \
  --kernel src \
  --work /tmp/vf-review-layout-current \
  --report /tmp/vf-review-layout-current.json \
  --renderer /tmp/vf-adaptation-full-accepted/puppeteer
```

`--kernel` 支持源码目录或含 `src/` 的仓库目录；`--renderer` 使用已有锁定工具链。运行器不会安装依赖。缺少场景、CLI 失败、渲染失败、浏览器观察失败均使整组退出码为 1，不跳过验收。

四个稳定案例在 [cases.json](cases.json) 中登记：

- `layout.review.nested_repeat_loop`：正式 review 更新 Architecture，并生成真实展开 SVG。
- `layout.expanded_svg.nested_repeat_loop`：正式 `export-svg --expand-nodesets`。
- `layout.mermaid.explicit_resources`：普通 Mermaid 导出继续显示调用方明确选择的资源。
- `layout.ordinary_svg.explicit_resources`：普通折叠 SVG 保留明确选择的资源，并检查实际浏览器几何。

展开产物按主 Workflow、`plugins`、`base_lib`、逐个展开的 Nodeset/Loop 面板排列；这份夹具没有 Host，`host_extensions` 列省略。`plugins` 父节点连接当前 config 选中的插件包，`base_lib` 父节点连接实际选择的库。外层流程为 TD；有子 Nodeset 的父流程为 TD；叶子流程为 LR。父流程在左，子面板在右且纵向堆叠。同一定义的重复调用保留调用 ID，合并为同一个详情面板；Loop 保留独立调用分组。

观察器只包装实际渲染函数，保存它们收到的 Mermaid 和标题，继续调用原渲染器。当前每次展开必须观察到 9 个真实 Mermaid 分片、4 列和 2 个嵌套面板；资源目录采用 LR 方向。业务分片不得包含资源图节点；资源目录不得出现文件图、reference、Node type 或 Rule/Ruleset 拓扑，同一插件包不拆成 compiler/runtime 实现卡。最终 SVG 在真实 Puppeteer 浏览器中检查业务方向、资源区域隔离、圆角形状、Node 默认色、调用点覆盖色和资源声明的六边形及颜色。正式 Architecture 同时检查样式值与逐字段来源。截图和逐分片 Mermaid 随报告保存至 `evidence/<report-stem>/`。

初版夹具把 `left/right` 都声明为同一个输出 key `result`，触发原生 duplicate-provider 错误，尚未进入渲染。这份观察保留为 [fixture-initial.json](../../../../docs/maintainers/evidence/index.md#artifact-45516f9c1e535d31)，不属于布局回退的修复前证据。现行夹具为两个 SDK Node 声明不同输出 key，保留全部默认审查规则。

浏览器的节点 ID 含渲染器前后缀，且 Mermaid 保留字 `end` 会被 VibeFlow 转为 `n_end`。定位器按实际分片归属及逻辑节点 ID 识别，方向和颜色期待保持不变。

资源分区改动之前，2026-10-06 的 [before.json](../../../../docs/maintainers/evidence/index.md#artifact-91d5d6e6c8952475) 使用冻结的未修复源码：4 个案例均实际执行，2 个展开入口失败，2 个普通显式资源入口通过，观察错误为 0。两个失败入口均返回退出码 0；失败只来自 Mermaid 与最终 SVG 中的资源泄漏，方向、几何、形状、颜色和 Architecture 对照通过。

[after.json](../../../../docs/maintainers/evidence/index.md#artifact-aac0324fb0daa2cb) 是此前资源泄漏修复的冻结观察，全部四个入口 4/4 通过，观察错误为 0。该阶段的 [展开 SVG](../../../../docs/maintainers/evidence/index.md#artifact-667908139dd54cb0)、[Architecture](../../../../docs/maintainers/evidence/index.md#artifact-ce47c87ebd8b5261)、[浏览器资料](../../../../docs/maintainers/evidence/index.md#artifact-9f0e8867ce0b6284) 和 [截图](../../../../docs/maintainers/evidence/index.md#artifact-ab96f48ecbdf68e3) 保留为历史证据。它们验证独立 VibeFlow 夹具，不替代业务项目自己的产物验收。

重建后的 0.15.1 两个完整包实际解出独立内核，再运行本组四个正式入口：[协同包](../../../../docs/maintainers/evidence/index.md#artifact-bcb395b1e73d0162)与[自主包](../../../../docs/maintainers/evidence/index.md#artifact-ac842f38c49be9a5)均为 4/4，观察错误为 0；浏览器资料和产物保存于 `evidence/collaborative-release/` 和 `evidence/autonomous-release/`。每包另有 79 项隔离 SDK、Rule、compiler、Host 与性能回归通过。

本轮完整 pytest 为 1963/1963、Python 集成为 138/138、性能沙箱为 57/57。原始失败及最终日志、源码指纹、完整构建与发行汇总见[修复验收记录](../../../../docs/maintainers/evidence/index.md#artifact-31e3261df1859ff8)。`review-layout-sandbox` 已进入完整门禁；本轮运行上述检查和发行验收。

历史 [sections-after.json](../../../../docs/maintainers/evidence/index.md#artifact-e4a865869cfb364d) 保存错误的内部实现图分区阶段，不再作为现行展示契约。本次恢复 `f169429` 用户资源目录的阅读层级，四个稳定案例 ID 保持不变；[user-layer-after.json](../../../../docs/maintainers/evidence/index.md#artifact-1dab9c8f6ed0e84a) 对新源码重跑全部入口，代表性 [SVG](../../../../docs/maintainers/evidence/index.md#artifact-9e74cb97aaeccb55) 与 [浏览器资料](../../../../docs/maintainers/evidence/index.md#artifact-75db2e33fe100530) 保存在独立证据目录。Nodeset 折叠、默认值及移除内部图参数的验收见[用户资源目录专项](../resource_sections/README.md)。

历史生成报告和截图已移出夹具目录，原始位置与恢复方法见 [证据索引](../../../../docs/maintainers/evidence/index.md)。上文历史成绩不代替当前运行。
