# 运行观测与类型注解修复记录

基线为 `9c443f3`。本轮增加双日志及外部监控状态接口，并修复类型参数化被误报为动态模块访问的问题。公开使用方式见[运行日志与状态接口](../user/runtime-observation.md)。

## 实现

- Core 提供状态枚举、JSON 信息快照和记录构造；Target 管理语言上下文、输出和定时发布，Tooling 覆盖配置及声明加载阶段。状态只有 starting/running/succeeded/failed，业务只更新 info。
- Python CLI 在 POSIX 上捕获 stdout/stderr 的真实文件描述符；嵌入式 Runtime 使用上下文标准流。Kernel 诊断与运行事件写入 vibeflow.log，控制台输出写入 business.log。委托 CLI 保留既有诊断中的业务异常内容隐藏行为。
- Python 配置使用 status_interval/status_file；JS/TS 使用 statusIntervalMs/statusFile/runDir。默认间隔 60 秒，状态变化与结束立即发布；文件原子替换。信息按完整数组替换，复制后缓存，结束时发布最新值。
- Node.js AOT 使用 AsyncLocalStorage 路由输出和独立线程维持文件更新。Host 的创建、启动、多次调用和停止共用一个会话观测范围；原生实例与生命周期协议保持原有机制。浏览器使用 onStatus 交由 Host 存储。
- 源码检查区分公共 typing/collections.abc 类型构造器的参数化与模块访问。继续检查下标内表达式，不忽略整个注解；模块反射、别名遮蔽及注解中的 eval 仍产生诊断。

## 验证

| 验证 | 结果 |
| --- | --- |
| 相关运行器、SDK、导入规则、Host、插件、AOT、CLI、workspace 与发行文档回归 | 513 passed |
| 启动路由与文档复查 | 38 passed |
| 输出流及委托 CLI 最后复查 | 99 passed |
| 仓库独立质量 | 0 error / 0 warning；46 tests passed |
| 注解正式 CLI 沙箱 | 14 组全部符合预期；保留修复前对照 |
| Python 正式 CLI 运行 | 成功、运行失败、启动失败均符合预期；原生/子进程/线程输出和实时 JSON 已实际读取 |
| JS/TS 正式 AOT 运行 | 成功、失败、重新运行均符合预期；主事件循环被占用时仍观察到状态文件更新 |
| 真实 Chromium | 实际按钮触发工作流，状态序列与业务信息正确；完整验证入口的新增浏览器步骤单独执行通过 |

上述测试组存在重复案例，数量不相加。机器报告和可重跑脚本位于 sandbox/python/runtime_observation、sandbox/javascript/runtime_observation 和 sandbox/python/typing_annotations。Python/Node 沙箱进入 pytest，真实浏览器状态案例进入 verify_project.py --full。

上述实现验收阶段没有重跑完整仓库发行门禁、MNIST/VibeTrain 的实际训练，也没有重新构建发行 ZIP。发行文档及提示词的后续构建验收记录如下。

## 业务使用文档与发行包复查

运行观测手册增加业务 Node 的训练进度方法示例，并明确完整数组替换、可选 id、复制缓存、刷新时机、多 Node 更新及 JSON 原生数据要求。Python 与 JS/TS SDK 手册中的完整文本处理 Node 同步调用更新接口，保留原契约输出和 `vibeflow.process` 选择。公共 AI 提示词提供准确的调用位置和参数语义，两个 profile 共用。

使用 `distribution/build.py` 重建 collaborative 与 autonomous 两个正式目录和 ZIP。逐项比对每个包的 13 份 canonical 文档及合成 AGENTS；外层和内层 ZIP 完整性通过，两个内核 ZIP 字节相同。解压发行 ZIP 后，清除 PYTHONPATH，用包内 run.py 执行两个手册 Node 的 Python 运行和 JS AOT 构建、实际运行；四项均成功，最终 info 与示例更新一致，JS 正常返回规范化结果。

相关文档和运行观测回归为 43 passed，仓库独立质量为 0 error / 0 warning。机器结果见 `sandbox/python/runtime_observation/documentation-release.json`，其中记录本次归档哈希。完整仓库门禁和业务训练的验收范围仍按前述记录。
