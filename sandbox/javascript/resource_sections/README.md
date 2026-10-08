# JavaScript 分区资源与 Nodeset 展开验收

这一组使用公开 JS/TS SDK 创建 Node、BaseLib、Plugin、Host 和真实 Nodeset/Loop，通过正式 CLI 检查和生成产物。14 个固定案例 ID 见 [cases.json](cases.json)。

```bash
python -B sandbox/javascript/resource_sections/run_all.py \
  --work /tmp/vf-js-resource-sections \
  --report /tmp/vf-js-resource-sections.json \
  --toolchain /path/to/locked/javascript-toolchain \
  --renderer /path/to/installed/mermaid-renderer
```

案例验证用户工作流的 `plugins`、`base_lib`、`host_extensions` 和 `capabilities` 目录：每个分类父节点连接本配置实际启用的资源，沿用左右排列。目录不展开源码、实现归属、跨区 reference、Node 类型定义或 Rule/Ruleset 定义。插件包仅显示一个条目，不把它贡献的 lifecycle 当作另一个选中插件。

普通 Mermaid 保持只画工作流的默认行为；`--mermaid-layout review-columns` 显示资源目录。旧案例 ID `js.sections.review.rules` 和 `js.sections.mermaid.rules` 保留，当前期待改为拒绝已删除的 `--show-rules` 参数（退出码 2，未发布图）。`after.json`、`browser-audit.json` 及 `evidence/after` 是修改前的冻结观察，不代表当前图格式；新观察保存在 `user-view-after.json`。

`expand: false` 在对应 Nodeset 定义处停止 Mermaid、ASCII 和正式 SVG 的细节展开，保留调用框。案例覆盖两层嵌套、共享调用和 Loop 引用。Architecture 继续记录隐藏定义的完整 body 和 `expand`；隐藏节点的自定义 Rule 仍产生目标错误 `CASE.HIDDEN.SOURCE`。实际 AOT 构建与运行保持输出 `{"number": 6}`。

[user-view-after.json](user-view-after.json) 为当前目录格式的 14/14 通过，观察错误为 0；[user-view-browser.json](user-view-browser.json) 为两个实际 SVG 的浏览器通过记录。它们核对目录父子关系、实际颜色/形状、隐藏 Nodeset、内部实现内容不进入用户图。

- [当前用户资源目录 SVG](evidence/user-view-after/js.sections.review.default/graph.svg) · [截图](evidence/user-view-after/js.sections.review.default/graph.png) · [Architecture](evidence/user-view-after/js.sections.review.default/ARCHITECTURE.jsonc)
- [当前折叠外层 SVG](evidence/user-view-after/js.expand.outer.false/graph.svg) · [截图](evidence/user-view-after/js.expand.outer.false/graph.png)

## 历史观察

以下产物冻结了原先的实现与期待；其中的源码/reference/Node 类型分区已从正式图生成逻辑删除。

[before.json](before.json) 使用修复包中冻结的 0.15.1 内核，来源及全部 348 文件指纹见 [source-before.json](source-before.json)。内核 SHA256 为 `22eff16e77cd4de81c6e9fdfc895b85b2081b826e3cfccfff5d27dddd22ae2f0`。同一夹具的 14 个案例全部实际运行，5 个符合新期待、9 个不符合，观察错误为 0：旧 CLI 拒绝 `--show-rules`（退出码 2）；旧图使用合并资源区，忽略 Nodeset 的 `expand`，Architecture 未记录这个字段。旧实现已经保持的业务执行和审查对照继续通过。这些差异表示本次新增功能的基线，不是将全部差异归为已有缺陷。

[after.json](after.json) 的 14/14 通过，观察错误为 0。首轮调查夹具使用小写 `rule:` 检查合法的 `Rule:` 标签，已改为大小写无关检查；旧 Architecture 未带 `expand` 记录为缺失值 `null`，不将缺失字段误当观察器崩溃。案例目标和产品期待没有放宽。

另外，三个正式 review 产物在真实 Puppeteer 浏览器加载并保存 DOM、计算样式和截图，[browser-audit.json](browser-audit.json) 为 3/3 通过。它们覆盖默认分区、显式规则和隐藏外层 Nodeset；核对四区顺序、Node/BaseLib/Host 的实际颜色及形状、业务分片的资源隔离和隐藏后模型调用框的消失。截图已目视检查区域、文字、连边和裁切。

- [默认分区 SVG](evidence/after/js.sections.review.default/graph.svg) · [截图](evidence/after/js.sections.review.default/graph.png) · [Architecture](evidence/after/js.sections.review.default/ARCHITECTURE.jsonc)
- [规则分区 SVG](evidence/after/js.sections.review.rules/graph.svg) · [截图](evidence/after/js.sections.review.rules/graph.png)
- [隐藏外层 SVG](evidence/after/js.expand.outer.false/graph.svg) · [截图](evidence/after/js.expand.outer.false/graph.png)

这些观察来自独立 VibeFlow 夹具；实际业务程序的运行仍需在其自己的环境验收。
