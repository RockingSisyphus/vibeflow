<!-- vibeflow-directory-purpose -->
# Python AOT 调用准备开销

使用当前公开 SDK 与正式 Python AOT 构建入口，生成 1、32、138 个串行加一节点；加上共享边界声明为 2、33、139 种节点类型。每次创建独立 Runtime，改变输入并核对输出，不复用业务实例。样本自行构建为当前 ABI，不依赖外部交接包。

运行 `python sandbox/python/aot_preparation/run_probe.py --nodes 1 32 138 --rounds 20 --report /outside/repo/python.json`。临时项目和 Bundle 位于 TMPDIR，结束自动删除；正式报告显式保留在仓库外。专用节点数/轮数仅用于控制测量规模，不设毫秒数通过门槛。

Bundle 只加载一次，先预热，再分别进行五次 cProfile 计数与无 profiler 的计时。报告给出装载、Runtime 准备、执行和总耗时，以及固定描述/绑定工作次数。没有历史类方法替换或重复缓存方案。它不是监工业务的移植，不能把 Python 与 JS 数字相除作为语言性能倍率。

[原交接分析](../../../docs/maintainers/aot-preparation-analysis.md)保留当时结果；其中 ABI v8 交接 Bundle 不能直接用于当前加载器。长期回归位于 tests/targets/python/test_aot_preparation.py，覆盖固定资料复用及实例、参数、插件隔离。
