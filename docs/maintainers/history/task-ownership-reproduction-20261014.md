# 跨 root 任务目标源码归属阻断：最小复现与根因

用户提供 Gensokyo 的“源码归属检查阻断.md”，要求分析并在 VibeFlow 根目录沙箱建立复现，确认问题后说明原因及修复方法。本次仅增加复现材料、定位根因与仓库外候选试验；未修改产品源码、0.19.0 发布包或下游项目。

## 公开入口复现

案例见 [ownership fixture](../../../sandbox/javascript/task_management/ownership/README.md)，入口为 `sandbox/javascript/task_management/run_ownership.py`。两个 workspace root 复用同一 worker 和已登记 BaseLib/source/implementation_files。只运行公开 validate 与 inspect-resources，不执行业务，不关闭规则。

最终十项对照中九项符合预期：同 root 普通/任务调用通过，跨 root 普通 Nodeset 与 implemented 管理调用通过，直接 Node 目标通过，真正未登记 loose.ts 在两 root 均被拒绝。唯一不匹配为跨 root 的 planned 管理 Node + Nodeset 目标：3 条 VF_IMPORT_OWNER，分别指向已登记 math.ts/types.ts（类型检查位置产生两条 types.ts 诊断）。源码与实际 0.19.0 包结果相同。

初次配置在直接 Node 和负对照也导入了未使用 Nodeset，暴露同一更广泛的“独立声明审查”缺口，导致两个非预期失败；后续去掉这些对照不需要的 nodeset_imports，让最终矩阵只改变待比较的机制。初次日志保留，不能用最终矩阵覆盖它。

源码最终报告：`/home/rockingsisyphus/.cache/vftm/ownership02/report.json`；解压包报告：`/home/rockingsisyphus/.cache/vftm/ownership019/report.json`。两个目录保留逐项 stdout/stderr 和 inspect-base-lib.json；初次报告为 ownership01/report.json。

## 根因调用链

1. `core/rules/planning.py::graph_rule_subjects` 遇到 planned 管理 Node 时跳过其调用遍历；导入的 Nodeset 因未在调用图遍历到，被另行保存为 declaration_only。它内部的 worker 仍是 implemented。
2. `targets/javascript/build/rule_session.py::node_type_calls` 不计 declaration_only。`tooling/application/javascript/audit.py` 用这个活跃调用集合构造初始 target_neutral_import_policy，只登记其 Node 与依赖 BaseLib。
3. `run_javascript_rules` 随后把 declaration_only 内的 implemented Node 加入实际源码审查集合，但没有同步重建该 import_policy。于是 worker 被审查，ownership.math 与 types.ts 的完整归属却不在这份名单中。
4. `rule_session.py` 补充源码闭包时仅纳入本 root 文件或名单中已有 owner 的文件。跨 root helper/type 因缺 owner 被排除，后续 closure_import_policy 无法补回它们的归属；同 root 则通过本地闭包补回，掩盖初始不一致。
5. toolchain_driver.mjs 根据收到的不完整 owner 事实返回 VF_IMPORT_OWNER。Catalog/inspect-resources 中的声明正确，问题不是业务漏登记，也不是 TypeScript type-only 文件不能归属。

这不是单纯“跨 root 路径不能解析”：普通调用及 implemented 管理调用已通过。planned 管理 Nodeset 暴露的实质问题是活跃调用集合与独立源码审查集合不一致；未使用 Nodeset 声明也可能触发同一缺口。不能推断异步运行器失败。

## 修复方向及低成本验证

以本次实际接受源码审查的 implemented Node 集合构造归属策略，同时登记它们声明的 BaseLib 与传递依赖、source/implementation_files。调用路径与执行计划仍按活跃调用集合建立，declaration_only 不变成实际运行调用；planned Node 不加载实现。归属策略应由源码审查集合统一构造，避免 audit/build 等入口各自维护不一致集合。

候选验证只在 `/home/rockingsisyphus/.cache/vftm/ownership-proof/src` 的源码副本进行：run_javascript_rules 合并 declaration_only/registered 审查对象后，按 used 集合重新构造策略，同时保留选中的 Host/Plugin、external packages 资料。十项全部匹配，合法跨 root planned Nodeset 目标恢复 CONCERNS（保留 planned 提示），两个真实未登记导入仍各报 1 条 VF_IMPORT_OWNER。报告为该目录 `results/report.json`。

这证明补齐实际归属信息能消除误判，无需清空规则、复制业务、伪装 external、把任务移出图或把 planned 提前标为 implemented。副本候选尚不是正式修复，也未跑完整回归：实际落地还需收敛共享集合接口，核对 Host/Plugin 归属与其他已登记但未调用资源的审查，并验证 validate/review/build，随后再构建可信新包。当前正式内核与发布包仍存在此缺陷。
