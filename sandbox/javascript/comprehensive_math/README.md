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
