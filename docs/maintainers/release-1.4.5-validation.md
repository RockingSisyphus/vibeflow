# 1.4.5 本地验证记录

范围：Linux 本机当前源码、双语言 CLI、离线 HTML、AOT、wheel/sdist 及两个分发 profile。未执行远端 CI 或其他平台验证。

## 首轮完整批次

执行 `python tools/verify_project.py --full --workers 4`，17 个阶段均运行结束。

- pytest：4814 passed、1 failed。失败为此前文档路由调整后不再适用的固定关键词断言。
- Python 沙箱、JavaScript 最小 AOT、规则回归 1115/1115、补充规则 194/194、运行观测浏览器、两端审查性能、适配回归 173/173、wheel/sdist 隔离及工作区清理通过。
- JavaScript 集成 50/51：验收代码仍引用旧输出变量。
- JavaScript 资源专项 11/12：Mermaid 文本资源视图需要的共享状态格式化函数被误删。
- 仓库检查和分发构建因同一处测试说明文档的失效链接未通过。

## 集中修复与复验

修复失效链接和验收变量，恢复仍被 Mermaid 文本使用的共享格式化函数。分发确定性场景改为执行真实构建 CLI，删除与固定文档位置和内核源码布局耦合的断言，继续检查正式产物与解压结果。

已通过的复验：

- JavaScript 完整集成：51 passed、0 failed、0 skipped。
- 分发 CLI 与 HTML 相关 pytest：54 passed。
- 两端资源专项：各 12/12。
- 双语言 CLI 及两种 Mermaid 文本布局：6 passed。
- 文本/数据 runner 移除不再需要的浏览器参数后，Python 审查性能与缓存场景通过。
- 仓库检查：0 error、0 warning。

双 profile 分发阶段已重新完整通过，包含内核校验、Python/JavaScript 运行以及从 ZIP 解压后的 AOT 构建和执行；两个内核归档均不包含已移除的生成模块与渲染器配置。

第二轮源码 pytest 为 4814 passed、1 failed：新增的本验证记录未登记到 docs 总索引。已补齐索引；该轮没有生产行为失败。最终完整 pytest 已通过：4815 passed、0 failed、0 skipped（458.63 秒）。



## 最终验收结论

首轮完整 17 阶段用于集中收集问题，未通过项随后逐项修复并复验；没有把首轮整体标为通过。最终生产源码的完整 pytest 为 4815 passed，JavaScript 完整集成 51/51、两端资源各 12/12、双 profile 分发验收通过。此前通过的规则、适配及 wheel/sdist 阶段未因文档索引修复再重复运行。

一次额外的直接 pytest 调用遗漏项目工具链环境变量，产生夹具准备错误；正式验收始终使用项目隔离 runner，该调用产生的临时夹具已清理。

正式构建命令为 `python distribution/build.py --profile all`，两个 ZIP 由构建器写入 dist；旧版本由既有发行机制保存。

正式 dist 中两个 ZIP 均与完成上述分发验收的候选 ZIP 逐字节一致（SHA-256 相同）；两个 profile 的内核归档字节一致。
