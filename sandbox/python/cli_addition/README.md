# python cli_addition

YAML、pathlib、标准流三个配置通过真实 delegate-cli 执行 2+3+4=9。检查精确输出、文件、退出码、作用范围、节点次数、日志隔离及导出无副作用。

```bash
python sandbox/python/cli_addition/run_all.py
```

默认使用外部临时目录；`--work-dir /absolute/outside/repository` 保留项目、报告与运行记录。Python 可用 `--renderer-root` 复用 Mermaid/Puppeteer，JavaScript 可用 `--toolchain-root` 复用按 package-lock 安装的 TypeScript/esbuild。

业务代码在 project，Config 在 project/configs，测试驱动在 run_all.py。所有源码修改仅发生在工作副本中。完整检查条件及旧任务替代关系见 [维护归档](../../../docs/maintainers/history/audits/addition-sandboxes-20261009.md)。
