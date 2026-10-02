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
python -m vibeflow review-rules --workspace sandbox/python/rule_graph/vibeflow_config.jsonc --config sandbox/python/rule_graph/project/configs/calculate.jsonc --node calculate --json
python -m vibeflow validate --workspace sandbox/python/rule_graph/vibeflow_config.jsonc --config sandbox/python/rule_graph/project/configs/calculate.jsonc --json
```

Run the business workflow with the provided input:

```sh
python -m vibeflow run --workspace sandbox/python/rule_graph/vibeflow_config.jsonc --config sandbox/python/rule_graph/project/configs/calculate.jsonc --input sandbox/python/rule_graph/input.json --run-root /tmp/vibeflow-rule-graph-runs
```
