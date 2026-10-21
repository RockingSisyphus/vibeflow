# python object_addition

Box 从 2 开始加 3；单次 5、条件两次 8、固定四次 14。检查两个原对象、集合/NaN、导出、子计划参数/顺序、carry/collect 和执行 trace，固定循环覆盖 plan/block/compiled。

```bash
python sandbox/python/object_addition/run_all.py
```

默认使用外部临时目录；`--work-dir /absolute/outside/repository` 保留项目、报告与运行记录。Python 可用 `--renderer-root` 复用 Mermaid/Puppeteer，JavaScript 可用 `--toolchain-root` 复用按 package-lock 安装的 TypeScript/esbuild。

业务代码在 project，Config 在 project/configs，测试驱动在 run_all.py。所有源码修改仅发生在工作副本中。具体断言见同目录 [run_all.py](run_all.py)，报告由每次运行生成。

## 目录用途与边界

仅用于：python / object_addition 案例，验证对象身份、状态、Nodeset 和循环加法；保留真实项目输入与 runner。

- 新文件按上述用途归属；新增子目录同时写明职责，不能作为临时收纳箱。
- 一次运行的日志、缓存、依赖安装和候选构建放在仓库外临时工作区，用完清理。
- 已确定过时且不再使用的内容直接删除；需要追溯时使用 Git 历史，不默认另建归档。

完整归位规则见[仓库目录职责](../../../docs/maintainers/directory-layout.md)。
