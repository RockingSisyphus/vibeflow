# 测试迁移审查

原始文件已逐字保存在 original-tests.tar.gz；未执行删除或批量重写。逐函数索引见 test-retirement-review.json。

| 文件 | 已核对的原目标 | 拟迁移 |
|---|---|---|
| test_input_exception_states.py | 异常出口、handler 匹配和参数传播的输入身份证明 | 退役该专用套件，有限 try 内直接写入由新输入规则测试覆盖 |
| test_source_parameter_facts.py | 跨文件参数/字典事实、builtin 证明和捕获参数传播 | 退役该专用套件；共享绑定代码继续保留在 SourceContext/bindings，并保留独立作用域测试 |
| test_input_declared_bindings.py | 全部基于 _input_call_facts/source_input_parameters 的闭包写回与参数污染断言 | 退役专用套件；简单参数遮蔽在有限输入规则中验收 |
| test_exit_stack.py | CLI 静态 close/callback 豁免与 analyze_exit_stacks，不含 Runtime cleanup 执行 | 退役专用静态分析套件；现有 Runtime 生命周期测试保留 |
| test_runtime_dispatch.py | 混合动态推断/编译三态事实与实际协调锁 | 保留 _global_state_graph/_global_state_health 和两项实际锁测试，退役其余推断期待 |
| test_input_writeback.py | 简单输入别名及大量异常/生成器/跨函数组合 | 用有限直接输入、简单别名、重绑定、遮蔽和不支持范围的正式 Rule 对照替换 |
| test_source_control_definitions.py | 有效词法身份/调用事实，夹带三行参数传播断言及未知 close 拒绝 | 保留全套结构身份案例，仅移除三行污染断言，未知 close 改为允许 |

另需逐处迁移活动格式测试的 Workflow v4 → v5、AOT v1 → v2 和退休字段期待；不改历史审核目录及旧版本 fixture 内容，不做整树删除。
