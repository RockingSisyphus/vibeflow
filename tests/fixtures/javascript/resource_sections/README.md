# JavaScript 分区资源与 Nodeset 展开验收

这一组使用公开 JS/TS SDK 创建 Node、BaseLib、Plugin、Host 和真实 Nodeset/Loop，通过正式 CLI 检查和生成产物。14 个固定案例 ID 见 [cases.json](cases.json)。

```bash
python -B tests/fixtures/javascript/resource_sections/run_all.py \
  --work /tmp/vf-js-resource-sections \
  --report /tmp/vf-js-resource-sections.json \
  --toolchain /path/to/locked/javascript-toolchain \
  --renderer /path/to/installed/mermaid-renderer
```

案例验证用户工作流的 `plugins`、`base_lib`、`host_extensions` 和 `capabilities` 目录：每个分类父节点连接本配置实际启用的资源，沿用左右排列。目录不展开源码、实现归属、跨区 reference、Node 类型定义或 Rule/Ruleset 定义。插件包仅显示一个条目，不把它贡献的 lifecycle 当作另一个选中插件。

`expand: false` 在对应 Nodeset 定义处停止 Mermaid、ASCII 和正式 SVG 的细节展开，保留调用框。案例覆盖两层嵌套、共享调用和 Loop 引用。Architecture 继续记录隐藏定义的完整 body 和 `expand`；隐藏节点的自定义 Rule 仍产生目标错误 `CASE.HIDDEN.SOURCE`。实际 AOT 构建与运行保持输出 `{"number": 6}`。

对应的 Python 场景与命令见 [Python 资源目录专项](../../python/resource_sections/README.md)；统一执行入口见[完整验证](../../../../docs/maintainers/development.md#验证层级)。

## 目录用途与边界

仅用于：resource_sections 专项实现回归的固定输入、预期及 runner；只保留有当前加载方的材料，运行产物写入临时工作区。

- 新文件按上述用途归属；新增子目录同时写明职责，不能作为临时收纳箱。
- 一次运行的日志、缓存、依赖安装和候选构建放在仓库外临时工作区，用完清理。
- 已确定过时且不再使用的内容直接删除；需要追溯时使用 Git 历史，不默认另建归档。

完整归位规则见[仓库目录职责](../../../../docs/maintainers/directory-layout.md)。
