# python cli_addition

YAML、pathlib、标准流三个配置通过真实 delegate-cli 执行 2+3+4=9。检查精确输出、文件、退出码、作用范围、节点次数、日志隔离及导出无副作用。

```bash
python sandbox/python/cli_addition/run_all.py
```

默认使用外部临时目录；`--work-dir /absolute/outside/repository` 保留项目、报告与运行记录。Python 可用 `--renderer-root` 复用 Mermaid/Puppeteer，JavaScript 可用 `--toolchain-root` 复用按 package-lock 安装的 TypeScript/esbuild。

业务代码在 project，Config 在 project/configs，测试驱动在 run_all.py。所有源码修改仅发生在工作副本中。具体断言见同目录 [run_all.py](run_all.py)，报告由每次运行生成。

## 目录用途与边界

仅用于：python / cli_addition 案例，验证CLI、YAML / 文件 / 标准流适配和真实加法执行；保留真实项目输入与 runner。

- 新文件按上述用途归属；新增子目录同时写明职责，不能作为临时收纳箱。
- 一次运行的日志、缓存、依赖安装和候选构建放在仓库外临时工作区，用完清理。
- 已确定过时且不再使用的内容直接删除；需要追溯时使用 Git 历史，不默认另建归档。

完整归位规则见[仓库目录职责](../../../docs/maintainers/directory-layout.md)。
