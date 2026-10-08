# 规则上下文派生与资料复用

本沙箱复现只更换 subject、阶段或一个 fact 时，RuleContext 仍重新冻结整份分析资料的性能缺陷。`before.json` 直接使用修复前的正式 0.15.0 内核 ZIP，四种派生操作各执行约 10,000 次 readonly 调用；`after.json` 中相应次数为 4、3、7、5。验收断言遍历次数与对象身份，不依赖机器速度。

```bash
python -B sandbox/python/context_reuse/probe.py \
  --report /tmp/vf-context-reuse.json
PYTHONPATH=src:. python -B -m sandbox.python.context_reuse.cli_probe \
  --work /tmp/vf-context-reuse-cli --report /tmp/vf-context-reuse-cli.json
```

CLI 案例使用公开 SDK 定义 12 种 Node 和调用级、源码级两条 Rule，通过正式 validate 执行 24 次检查。每个 Node 使用唯一输出键，原生路由与契约不变。规则记录实际源码服务与 Node catalog 的身份，并检查调用级资料只提供给调用规则。规则自己的统计代码是受信扩展实现，fixture 明确选择身份检查规则，不依赖业务 Node 的副作用授权。

`cli-before.json` 在旧发行内核上取得 24 份不同源码资料与 catalog；`cli-after.json` 中各只有一份。两次正式 CLI 都返回 0，观察脚本另外判断复用是否符合预期。

修复仅复用当前上下文已经生成的只读快照及其直接字段。新 subject、facts、scope 仍递归冻结；任意外部浅层 mappingproxy 不被当作完成冻结的资料。独立新上下文、原始资料重新提交以及各命令的检查范围保持各自语义，不添加跨检查的持久缓存。Python Target 在本次规则阶段建立共享事实上下文，加载状态仍按实际阶段刷新；JS Target 切换入口时派生已有上下文。

`tests/core/test_rule_context_reuse.py` 检查派生、外部代理、原始资料变化、临时对象身份复用、调用与源码边界；`tests/targets/python/test_context_reuse.py` 执行正式 CLI 案例。之前的 tuple DAG、混合容器、循环、只读及默认值隔离回归继续保留。

`mnist-observation.json` 与 `mnist-report.json` 记录未修改的 VibeTrain MNIST workflow 的只读校验。当前源码约 56 秒返回报告，上一轮约 120 秒；20 条 error 和 91 条 warning 的完整诊断与上一轮逐项一致。此结果说明消除了这批重复工作，不表示训练验收通过，也不保证其他设备或工作流都在 90 秒内完成。没有修改 VibeTrain 源码、配置或安装内核，没有执行训练。

`verification.json` 记录本轮验收和后续重新构建的发行内核；`released-after.json`、`released-cli-after.json` 直接验收新包中的上下文复用。扩展 JS 回归另外发现具名 Node 的专用 Context 被 SDK 的通用 Context 过早约束，已修正类型声明，实际实现仍由原有 AOT 契约检查验证。

Core 和双 Target 回归为 1,208 passed / 7 skipped，独立仓库质量为 0 errors / 0 warnings，其自身测试为 46 passed。两个正式 0.15.0 ZIP 已重新构建并验证内核、源码字节、文档与提示词一致性。新发行内核的真实 MNIST 只读校验约 56 秒，诊断逐项一致，见 `mnist-release-observation.json` 与 `mnist-release-report.json`。本轮未重新运行完整发行 gate 或训练。
