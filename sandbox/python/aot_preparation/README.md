<!-- vibeflow-directory-purpose -->
# Python AOT 调用准备开销

使用作者交接 ZIP 中原有的 139 节点监工 Bundle，但通过当前仓库 src 的公开 `load_bundle/create_runtime/run` 执行真实 `settings.get`。每次新建 Runtime，使用独立合成身份和空数据库，不访问原任务状态。

`run_probe.py --handoff /path/to/vibeflow-author-handoff.zip --report /outside/repo/python.json`。
临时目录由 `TMPDIR` 指定，结束自动删除。报告显式保留在仓库外；不把包和运行目录复制进沙盒源码。

五次暖调用的 cProfile 只用于次数；耗时另用未开启 profiler 的交错顺序测量。四种模式为原实现、只缓存固定 Descriptor、只缓存固定 Plugin 绑定表、两者；后面三种仅进程内实验，退出恢复方法，不修改内核文件，不复用业务对象。它们不能替代跨 Bundle、并发和生命周期验收。

当前实测与方案见[分析记录](../../../docs/maintainers/aot-preparation-analysis.md)。此专项需要原交接包，按需运行，不自动加入完整验收批次。

方案二修复后，normal 即生产实现，暖 profile 应不再出现 Descriptor 解码与完整绑定表构造。保留的缓存分组用于历史诊断对照；各组不再增加额外固定资料复用，不用其计时差异冒充新的优化收益。
