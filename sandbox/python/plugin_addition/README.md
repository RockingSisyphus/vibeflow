# python plugin_addition

默认 2+3=5，局部覆盖 b=4 得到 6；临时 helper 改为 a+b+1 后 6，恢复后 5。检查源码归属、编译/运行钩子与重复调用；源码阶段各用新解释器。

```bash
python sandbox/python/plugin_addition/run_all.py
```

默认使用外部临时目录；`--work-dir /absolute/outside/repository` 保留项目、报告与运行记录。Python 可用 `--renderer-root` 复用 Mermaid/Puppeteer，JavaScript 可用 `--toolchain-root` 复用按 package-lock 安装的 TypeScript/esbuild。

业务代码在 project，Config 在 project/configs，测试驱动在 run_all.py。所有源码修改仅发生在工作副本中。完整检查条件及旧任务替代关系见 [维护归档](../../../docs/maintainers/history/audits/addition-sandboxes-20261009.md)。
