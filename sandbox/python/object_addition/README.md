# python object_addition

Box 从 2 开始加 3；单次 5、条件两次 8、固定四次 14。检查两个原对象、集合/NaN、导出、子计划参数/顺序、carry/collect 和执行 trace，固定循环覆盖 plan/block/compiled。

```bash
python sandbox/python/object_addition/run_all.py
```

默认使用外部临时目录；`--work-dir /absolute/outside/repository` 保留项目、报告与运行记录。Python 可用 `--renderer-root` 复用 Mermaid/Puppeteer，JavaScript 可用 `--toolchain-root` 复用按 package-lock 安装的 TypeScript/esbuild。

业务代码在 project，Config 在 project/configs，测试驱动在 run_all.py。所有源码修改仅发生在工作副本中。完整检查条件及旧任务替代关系见 [维护归档](../../../docs/maintainers/history/audits/addition-sandboxes-20261009.md)。
