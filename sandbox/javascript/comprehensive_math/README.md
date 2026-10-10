# JavaScript 综合数学沙箱

独立 TypeScript SDK 项目，业务公式和 Node/Rule 均有本 Target 的实现。通过 AOT 在 Node.js 与真实 Chromium 中运行，检查规则诊断、typed record、配置覆盖、分支汇合、Nodeset、循环、Port、重复/并发隔离及实际异步等待。

完整公式、输入矩阵与通过判定见 [共用案例说明](../../../docs/maintainers/comprehensive-math-sandbox.md)。

```bash
python sandbox/javascript/comprehensive_math/run_all.py
python sandbox/javascript/comprehensive_math/run_all.py \
  --toolchain-root /path/to/installed/typescript-project \
  --puppeteer-root /path/to/installed/renderer \
  --work-dir /tmp/javascript-comprehensive-math-new
```

默认复制到临时目录，按 package-lock 安装依赖并自动清理。保留目录中 `report.json` 分别记录 Node/browser 的八次观察和 held receive；`health.json` 与 `repaired-health.json` 是源码修正前后的规则反馈。

`--skip-browser` 仅用于显式减量运行，记录 REDUCED。该 runner 已由 JS integration 调用，默认完整模式要求真实浏览器通过。

## 目录用途与边界

仅用于：javascript / comprehensive_math 案例，验证含 Node、BaseLib、Nodeset、Loop 与 I/O 的综合数学流程；保留真实项目输入与 runner。

- 新文件按上述用途归属；新增子目录同时写明职责，不能作为临时收纳箱。
- 一次运行的日志、缓存、依赖安装和候选构建放在仓库外临时工作区，用完清理。
- 已确定过时且不再使用的内容直接删除；需要追溯时使用 Git 历史，不默认另建归档。

完整归位规则见[仓库目录职责](../../../docs/maintainers/directory-layout.md)。
