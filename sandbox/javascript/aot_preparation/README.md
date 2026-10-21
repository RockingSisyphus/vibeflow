<!-- vibeflow-directory-purpose -->
# JavaScript AOT 调用准备开销

通过公开 SDK 与 `build_project_aot` 构建 1、32、138 个计算节点的真实串行加一工作流，加上边界资源为 2、33、139 种节点类型。每次 `runWorkflow` 使用不同输入并核对输出；模块只导入一次。它不是 Python 监工业务的 JS 移植，不能用两端耗时相除得出语言性能倍率。

`run_probe.py --toolchain-root /outside/repo/toolchain --report /outside/repo/javascript.json`。
toolchain 使用 `sandbox/javascript/minimal/project` 的 package.json/lock 执行 `npm ci` 准备。生成物位于 TMPDIR 的独立目录，结束清理。

原包测量耗时；另一份临时诊断副本只统计函数进入次数，区分模块初始化与单次调用。记录静态工厂、调用准备、冻结与 SDK 声明函数，不将诊断副本计时当原包性能，不修改原始包或 SDK。

另一个独立副本仅在运行插件为空时跳过钩子摘要构造，与原包交错计时，检查空钩子的实际成本。该副本只用于测量候选方案，不代表已交付内核修复或异步／插件生命周期验收。

当前实测与方案见[当前行为与维护约定](../../../docs/maintainers/project-preparation.md)。此专项按需运行，不把某次毫秒数设为验收门槛。
