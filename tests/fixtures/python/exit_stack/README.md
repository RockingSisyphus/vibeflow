# ExitStack 清理与回调回归

本沙箱只用标准库与公开 SDK，独立构造 workflow，经正式 `validate/run` 检查，无需 VibeTrain 或 Torch。34 个案例保留稳定 ID；四个合法案例执行实际 Node，其他案例检查健康规则与退出码。

```bash
PYTHONPATH=src:. python -B -m tests.fixtures.python.exit_stack.probe \
  --work /tmp/vf-exit-stack --report /tmp/vf-exit-stack.json
```

每次使用新的工作目录。负例须命中目标诊断；回调负例还断言 `open/print/random.seed` 的实际诊断，避免另一条 `stack.close` 错误遮挡回调漏查。测试不执行这些负例业务代码，文件写入 marker 必须不存在。

| 案例组 | 检查内容 |
| --- | --- |
| `node_empty/alias/qualified/inline/with/constructor_alias/bound_close` | 空栈、别名、with 与绑定清理方法可合法使用 |
| `node_nested_close`、`class_field` | 栈清理回调与类字段中的真实 ExitStack；None 初始化不被当作未知对象授权 |
| `node_callback_*`、`node_partial_open`、`node_push_print` | 检查延迟回调，覆盖自动退出、绑定注册方法及 partial；合法 global_state 与纯规则拒绝对照 |
| `node_connection/reassigned/shadow/branch_reassigned/file`、`class_field_reassigned/same_name` | 文件、连接及未知替代对象仍受限；不把 self.stack.close 错绑为同类的 self.close |
| `library_*` | BaseLib 独立选择规则，检查回调与可达 helper 函数体；纯 close helper 通过，含 open 的 helper 拒绝 |
| `missing_output_branch/file_over_limit/readonly_deepcopy` | 保留缺失输出、逐文件 500 行限制和自定义规则浅复制冻结资料后的错误 |

`before.json` 保存修复前第一组 22 个案例的真实观察，9 个合法案例遭到误拒。后续补充的 12 个案例用于更严格的回调与对象绑定验收，未伪造其历史观察。`after.json` 保存最终 34 个案例及四次真实运行结果，全部符合预期。

`tests/targets/python/test_exit_stack.py` 将所有 CLI 案例接入常规回归，并检查分析不修改原 AST、回调源码位置、只读分析结果及对象替换。分析只依据当前源码事实，不执行清理回调，也不把动态未知对象推定为纯对象。

`mnist-observation.json` 和 `mnist-report.json` 保存未修改的 VibeTrain MNIST workflow 在本仓库源码内核下的只读正式校验。错误从上一轮 31 条降为 20 条，消除 11 条 ExitStack 误报及连带诊断；警告为 91 条。剩余错误为 17 条源码文件超限、1 条缺失声明输出、1 条 BaseLib 的 torch.set_grad_enabled 与其自身所选规则不匹配、1 条项目自定义规则 deepcopy 冻结资料失败。项目仍为 FAIL，未执行训练、未修改或安装 VibeTrain 内核。

`verification.json` 记录命令与验收范围。本轮只验证源码修复、Core/Python 回归及仓库独立质量；未重建发行包，未执行完整跨 Target、浏览器或发行验收。

后续于 2026-10-05 重建两个 0.15.0 分发包，`released-after.json` 记录从新包解压内核执行的 34 个案例与四次真实运行，全部通过。内核、文档、提示词及其他专项回归见[发行验证记录](../../../../docs/maintainers/evidence/index.md#artifact-6603a23574036898)。此记录不替代下游训练或完整浏览器验收。

历史生成报告和截图已移出夹具目录，原始位置与恢复方法见 [证据索引](../../../../docs/maintainers/evidence/index.md)。上文历史成绩不代替当前运行。

## 目录用途与边界

仅用于：exit_stack 专项实现回归的固定输入、预期及 runner；只保留有当前加载方的材料，运行产物写入临时工作区。

- 新文件按上述用途归属；新增子目录同时写明职责，不能作为临时收纳箱。
- 一次运行的日志、缓存、依赖安装和候选构建放在仓库外临时工作区，用完清理。
- 已确定过时且不再使用的内容直接删除；需要追溯时使用 Git 历史，不默认另建归档。

完整归位规则见[仓库目录职责](../../../../docs/maintainers/directory-layout.md)。
