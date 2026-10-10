# javascript plugin_addition

默认 2+3=5，局部覆盖 b=4 得到 6；helper 修改和恢复后 5→6→5。检查 manifest、active/planned、编译钩子、同步 ABI、运行钩子与重复调用隔离。

```bash
python sandbox/javascript/plugin_addition/run_all.py
```

默认使用外部临时目录；`--work-dir /absolute/outside/repository` 保留项目、报告与运行记录。Python 可用 `--renderer-root` 复用 Mermaid/Puppeteer，JavaScript 可用 `--toolchain-root` 复用按 package-lock 安装的 TypeScript/esbuild。

业务代码在 project，Config 在 project/configs，测试驱动在 run_all.py。所有源码修改仅发生在工作副本中。完整检查条件及旧任务替代关系见 [维护归档](../../../docs/maintainers/history/audits/addition-sandboxes-20261009.md)。

## 目录用途与边界

仅用于：javascript / plugin_addition 案例，验证插件、多文件资源、生命周期钩子和加法；保留真实项目输入与 runner。

- 新文件按上述用途归属；新增子目录同时写明职责，不能作为临时收纳箱。
- 一次运行的日志、缓存、依赖安装和候选构建放在仓库外临时工作区，用完清理。
- 已确定过时且不再使用的内容直接删除；需要追溯时使用 Git 历史，不默认另建归档。

完整归位规则见[仓库目录职责](../../../docs/maintainers/directory-layout.md)。
