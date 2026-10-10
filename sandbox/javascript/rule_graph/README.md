# Typed Rule graph example

The workflow calculates `3 * 2 + 1 = 7`. Its calculation Node selects a
Ruleset whose checker receives `example.numbers.v1` from a facts provider.
The `requires` relation binds records automatically; findings and availability
are separate. The two handlers are ordinary external source modules.

The Ruleset has the default static entrypoint. It is checked by `validate`,
but it does not silently run at import or execution time. `review-rules` shows
its declarative plan without loading either implementation. Integration tests
copy this project and explicitly select import/run entrypoints when testing
those phases, along with nested includes and local overrides.

From the repository root, inspect the graph and validate its static checks:

```sh
python -m vibeflow review-rules --workspace sandbox/javascript/rule_graph/vibeflow_config.jsonc --config sandbox/javascript/rule_graph/project/configs/calculate.jsonc --node calculate --json
python -m vibeflow validate --workspace sandbox/javascript/rule_graph/vibeflow_config.jsonc --config sandbox/javascript/rule_graph/project/configs/calculate.jsonc --json
```

Install the pinned local toolchain before validation or building:

```sh
npm ci --prefix sandbox/javascript/rule_graph/project
python -m vibeflow build --workspace sandbox/javascript/rule_graph/vibeflow_config.jsonc --config sandbox/javascript/rule_graph/project/configs/calculate.jsonc --target node --profile single-esm --out-dir /tmp/vibeflow-rule-graph-aot
```

The built entry exports `runWorkflow({value: 3})`, which returns `{result: 7}`.
Build uses static Rules; the explicit `run_javascript_rules(..., phase="run")`
Target API can perform run checks before callers execute the offline artifact.

## 目录用途与边界

仅用于：javascript / rule_graph 案例，验证Rule / Ruleset 组合与选择的真实项目行为；保留真实项目输入与 runner。

- 新文件按上述用途归属；新增子目录同时写明职责，不能作为临时收纳箱。
- 一次运行的日志、缓存、依赖安装和候选构建放在仓库外临时工作区，用完清理。
- 已确定过时且不再使用的内容直接删除；需要追溯时使用 Git 历史，不默认另建归档。

完整归位规则见[仓库目录职责](../../../docs/maintainers/directory-layout.md)。
