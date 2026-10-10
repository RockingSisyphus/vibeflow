# Python 综合数学沙箱

独立 SDK 项目：插件注册源码 Rule、typed-record 依赖、Node 与多文件 BaseLib，config 组合原生 IO、两层 Nodeset、条件分支、汇合和 while 循环。测试包含真实 checked run、架构 SVG、plan/block/compiled、连续复用、并发以及 warning 的源码修正对照。

完整公式、输入矩阵与通过判定见 [共用案例说明](../../../docs/maintainers/comprehensive-math-sandbox.md)。

```bash
python sandbox/python/comprehensive_math/run_all.py
python sandbox/python/comprehensive_math/run_all.py \
  --renderer-root /path/to/installed/renderer \
  --work-dir /tmp/python-comprehensive-math-new
```

默认使用当前仓库 src，自动准备锁定 Mermaid/Puppeteer 并清理临时目录。保留目录中 `report.json` 列出 13 次数值观察与 warning 数量，`checked/positive` 有 health、architecture、Mermaid、SVG 和 runtime_trace；`repaired-health.json` 是修正源码后的对照。

该 runner 也被 Python integration 调用，无需单独添加完整门禁步骤。

## 目录用途与边界

仅用于：python / comprehensive_math 案例，验证含 Node、BaseLib、Nodeset、Loop 与 I/O 的综合数学流程；保留真实项目输入与 runner。

- 新文件按上述用途归属；新增子目录同时写明职责，不能作为临时收纳箱。
- 一次运行的日志、缓存、依赖安装和候选构建放在仓库外临时工作区，用完清理。
- 已确定过时且不再使用的内容直接删除；需要追溯时使用 Git 历史，不默认另建归档。

完整归位规则见[仓库目录职责](../../../docs/maintainers/directory-layout.md)。
