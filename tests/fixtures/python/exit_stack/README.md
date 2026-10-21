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

`tests/targets/python/test_exit_stack.py` 将所有 CLI 案例接入常规回归，并检查分析不修改原 AST、回调源码位置、只读分析结果及对象替换。分析只依据当前源码事实，不执行清理回调，也不把动态未知对象推定为纯对象。

## 目录用途与边界

仅用于：exit_stack 专项实现回归的固定输入、预期及 runner；只保留有当前加载方的材料，运行产物写入临时工作区。

- 新文件按上述用途归属；新增子目录同时写明职责，不能作为临时收纳箱。
- 一次运行的日志、缓存、依赖安装和候选构建放在仓库外临时工作区，用完清理。
- 已确定过时且不再使用的内容直接删除；需要追溯时使用 Git 历史，不默认另建归档。

完整归位规则见[仓库目录职责](../../../../docs/maintainers/directory-layout.md)。
