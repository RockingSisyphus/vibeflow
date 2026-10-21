# javascript async_addition

两个 Capability 调用使用相同 key 和不同能力实现，释放前均等待，先释放右侧得到 30，再释放左侧得到 5。持续入口通过显式 open 节点建立 API 会话，接收两对数字、发送 5/30，第三次接收挂起。作者取消后显式调用 cleanup 入口关闭会话；重复关闭由作者 API 幂等处理，框架不托管生命周期。保留 browser ESM 构建检查。

```bash
python sandbox/javascript/async_addition/run_all.py
```

默认使用外部临时目录；`--work-dir /absolute/outside/repository` 保留项目、报告与运行记录。Python 可用 `--renderer-root` 复用 Mermaid/Puppeteer，JavaScript 可用 `--toolchain-root` 复用按 package-lock 安装的 TypeScript/esbuild。

业务代码在 project，Config 在 project/configs，测试驱动在 run_all.py。所有源码修改仅发生在工作副本中。完整检查条件及旧任务替代关系见 [维护归档](../../../docs/maintainers/history/audits/addition-sandboxes-20261009.md)。

## 目录用途与边界

仅用于：javascript / async_addition 案例，验证异步节点和结果汇合的真实加法执行；保留真实项目输入与 runner。

- 新文件按上述用途归属；新增子目录同时写明职责，不能作为临时收纳箱。
- 一次运行的日志、缓存、依赖安装和候选构建放在仓库外临时工作区，用完清理。
- 已确定过时且不再使用的内容直接删除；需要追溯时使用 Git 历史，不默认另建归档。

完整归位规则见[仓库目录职责](../../../docs/maintainers/directory-layout.md)。
