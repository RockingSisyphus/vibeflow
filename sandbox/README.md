# VibeFlow Sandbox

Runnable fixtures are grouped by target and scope:

- `python/minimal`: compact Python Node, base_lib, Plugin, and config fixture.
- `python/integration`: the complete Python runtime and CLI sandbox.
- `python/domain_rules`: model/data categories, domain source ownership, and numerical execution.
- `python/rule_graph`: external Rule providers/checkers, typed `requires`, and local overrides.
- `javascript/minimal`: minimal JavaScript/TypeScript AOT end-to-end build.
- `javascript/integration`: the complete TypeScript AOT, Capability, Host
  Extension, and browser sandbox.
- `javascript/domain_rules`: the same domain bundle through TypeScript analysis and native AOT execution.
- `javascript/rule_graph`: the same declarative Rule graph through the JavaScript worker.

The runnable projects are the baseline fixtures. Automated tests copy them and
exercise invalid declarations, unavailable records, graph conflicts, source
ownership errors, and formal command failures. See [TEST_COVERAGE.md](TEST_COVERAGE.md)
for the coverage matrix and repeatable commands.

Integration runners discover a source checkout or built distribution from
marker files. They use temporary workspaces by default and therefore do not
leave reports, build directories, dependencies, or package links in this tree.
Pass `--keep-artifacts` only when the generated files are needed for inspection.
