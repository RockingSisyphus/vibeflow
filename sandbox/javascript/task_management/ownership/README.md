<!-- vibeflow-directory-purpose -->
# 跨 root Nodeset 任务目标的源码归属复现

仅保存公开 SDK、声明、配置和两个最小项目 root。所有命令只 validate，不执行业务；依赖与报告放在仓库外。针对 Gensokyo 0.19.0 的源码归属阻断建立独立最小对照，不复制业务项目或修改其内核。

library/plugin.ts 登记 ownership.worker、ownership.math BaseLib 及 types.ts implementation_files，worker 明确声明 base_libs。worker.ts 同时导入纯 helper 和 type-only 类型。caller 引用 library 插件；两 root 的配置复用相同资源。loose.ts 故意不登记，为归属检查的负对照。

```bash
python -B sandbox/javascript/task_management/run_ownership.py \
  --toolchain-root /path/to/typescript-esbuild-toolchain \
  --work-dir /path/to/external-work
```

`--launcher /path/to/extracted-package/run.py` 可改用实际解压包，并移除 PYTHONPATH。toolchain-root 下须已有 node_modules。cases.json 声明十项预期：合法调用无阻断，真正未登记导入必须被拒绝。FAIL 与退出 1 表示真实回归不匹配，不把现有错误改成通过预期。每次使用新的工作目录。

| 调用方式 | 同 root | 跨 root |
| --- | --- | --- |
| 普通 Nodeset | PASS | PASS |
| planned 管理 Node 的 Nodeset 任务目标 | CONCERNS，无归属错误 | ERROR，3 条 VF_IMPORT_OWNER：缺陷复现 |
| implemented 管理 Node 的 Nodeset 任务目标 | PASS | PASS |
| planned 管理 Node 的直接 Node 任务目标，不导入 Nodeset | CONCERNS，无归属错误 | CONCERNS，无归属错误 |
| 普通 Node 导入真实未登记 loose.ts，不导入 Nodeset | ERROR，1 条 VF_IMPORT_OWNER | ERROR，1 条 VF_IMPORT_OWNER |

上述为 2026-10-14 修复前源代码与实际 0.19.0 包的静态结果，不是任务运行、取消或业务迁移验收。inspect-base-lib.json 保存公开清单，证明 helper 与 types.ts 已登记。

正式修复后十项全部匹配：跨 root planned Nodeset 目标恢复 CONCERNS，两个真实未登记导入仍被拒绝。integration runner 在任务管理生命周期检查之后自动运行此归属矩阵，根目录完整验收因而覆盖本案例。历史 full-04 通过仍不涵盖此组合，不改写其分母。根因与各阶段验证见开发文档 docs/maintainers/history/task-ownership-reproduction-20261014.md。
