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
