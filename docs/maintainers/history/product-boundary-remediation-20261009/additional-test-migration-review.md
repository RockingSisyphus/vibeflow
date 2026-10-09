# 首轮全量后的新增混合测试迁移审查

首轮 pytest：3713 passed、284 failed、18 setup errors。参数化失败不代表 284 个独立机制。18 个 setup 错误和发行包/浏览器部分失败来自仓库内 TMPDIR；第二轮使用 /var/tmp。其余失败逐类处理，不把失败统一改为通过。

自动审批拒绝 11 文件批量修改，理由是超过已批准的七文件清单，且调整拒绝断言可能削弱保障。该命令没有执行。待批准的具体范围如下；所有原函数/参数化案例保留，修改前逐字归档。

| 文件 | 调整的期待 | 继续验收 |
|---|---|---|
| Python test_source_effect_parameters.py | ctypes/eval 不再是默认安全禁令；未知 close 不再是 I/O；输入案例调用独立 input_writes，不要求效果 Rule 证明参数污染/闭包调用 | 实际导入政策、open/Path、真实模块状态、函数默认表达式与 lambda 原生符号身份、遮蔽、helper 身体效果 |
| Python test_comprehension_scopes.py | 直接入口表达式交给 input_writes；helper 参数污染、推导式消费后的 walrus 所有权和 closure 不作证明；未知 close 不因叶名拒绝 | 全部推导式作用域、同名导入/局部符号、resolved_function_calls、实际 helper 文件/行列位置、宿主 argv |
| Python strict_effect_scopes.py | 任意 vendor set/seed/reset、FFI、动态代码不再默认拒绝；跨 helper 输入传播和 inputs.get 返回值不作证明；FileType 在明确 python_io 下允许 | 已知 random.seed/torch.manual_seed/sys.setrecursionlimit、实际全局写入、open/保存/线程/进程、argv、直接输入别名、正式 CLI |
| Tooling strict_mermaid_cli.py | 局部 while/私有递归、对象字段、动态/缺失/未声明的静态输出构造、示例 outputs 不再仅因旧静态猜测拒绝 | 所有真实接口签名、生成器入口、Node 耦合、复杂度超限；实际输出由 Runtime 测试继续验收 |
| JS test_source_effect_parameters.py | Date/Math.random 不再需要 IO 政策 | 真实 fetch/console、process 生命周期、导入策略、原生 checker/遮蔽 |
| Python test_import_policy_parameters.py | importlib/ctypes 默认安全禁令和 import_module 硬拒绝退役；显式参数化禁令仍生效 | 完整 Rule 计划、参数优先级、空数组、真实 sys/io/http 效果导入 |
| JS test_analysis_session.py | BaseLib 所有权测试选新 architecture 主题 | 同一程序事实下不同选择仍独立，不共享权限 |
| JS strict_aot_toolchain.py | 无已安装依赖的 yarn/pnpm/多 lock 项目应报实际 dependency missing，不报 lock qualification | 不因修改 lock 期待伪称构建成功；另有三例真实依赖构建/运行/替换发布 |
| JS test_project_dependency_negatives.py | 选新 architecture 主题以验收 Node/BaseLib 所有权 | 所有精准诊断、位置与失败替换原产物保持不变 |
| Integration test_javascript_sandbox.py | Node 所有权诊断 definition_id 改为 node_architecture | 正式入口仍拒绝真实 Node 耦合；import_side_effects 保留其独立职责 |
| JS test_quality_sandbox.py | 私有递归不再自动成为 hard error，仍保留实际调用图与链长阈值检查 | 已配置复杂度阈值、真实图、Schema keys、共享分析缓存 |

目标权衡：批准后，回归保证会精确落在 B01—B11 的新职责上；保留旧拒绝期待则需要恢复已明确退役的分析器。此次不删除真实运行机制或词法案例，不改变 Runtime 输出合同、锁、异步和 cleanup 的验收。旧测试与历史观察通过归档继续可追溯。

除此之外的格式 hash 更新、文档链接/版本迁移和环境修复是对应新 ABI/AOT 的机械一致性工作；若另有实质行为变化，另行说明，不用当前观察自动生成期待。
