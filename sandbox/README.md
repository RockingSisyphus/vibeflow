# VibeFlow Sandbox

Runnable fixtures are grouped by target and scope:

- `python/minimal`: compact Python Node, base_lib, Plugin, and config fixture.
- `python/integration`: the complete Python runtime and CLI sandbox.
- `python/domain_rules`: model/data tags, domain source ownership, and numerical execution.
- `python/rule_graph`: external Rule providers/checkers, typed `requires`, and local overrides.
- `python/source_false_positives`: independent formal CLI controls for local bindings,
  pure paths, source-visible helper effects and inherited Node implementations;
  [observations and commands](python/source_false_positives/README.md).
- `python/exit_stack`: ExitStack receiver identity, deferred callback effects,
  and project-adaptation negative controls through the formal CLI;
  [observations and commands](python/exit_stack/README.md).
- `python/context_reuse`: frozen-fact reuse across subjects, phases and Node
  types, with formal CLI identity controls;
  [observations and commands](python/context_reuse/README.md).
- `python/review_performance`: command-local analysis reuse, presentation without
  binding, repeated Nodeset/Loop calls and browser-verified canonical products;
  [observations and commands](python/review_performance/README.md).
- `python/review_layout`: resource isolation between workflow and detail panels,
  nested Nodeset/Loop layout, and browser-verified expanded SVG;
  [observations and commands](python/review_layout/README.md).
- `python/resource_sections` and `javascript/resource_sections`: ordered Plugin,
  BaseLib, Host and Node type panels, opt-in Rule details, display-only Nodeset
  folding, formal CLI and browser checks; [Python](python/resource_sections/README.md)
  and [JavaScript](javascript/resource_sections/README.md) observations.
- `adaptation_regressions`: SDK source identity, Record sharing, compiler and
  inspection phases, resource ownership, Host closure and JS analysis reuse;
  [cases and commands](adaptation_regressions/README.md).
- `python/sdk_defaults`: independent SDK JSON-default registration probes,
  formal CLI observations, and native-container isolation controls; see
  [its README](python/sdk_defaults/README.md) for the reproduced failures.
- `javascript/minimal`: minimal JavaScript/TypeScript AOT end-to-end build.
- `javascript/integration`: the complete TypeScript AOT, Capability, Host
  Extension, and browser sandbox.
- `javascript/domain_rules`: code-plugin domain resources through TypeScript analysis and native AOT execution.
- `javascript/rule_graph`: the same declarative Rule graph through the JavaScript worker.
- `resources/python` and `resources/javascript`: multi-file Node, BaseLib, Plugin,
  and JS/TS Host implementations, with formal SVG and Architecture JSONC examples.

The formal CLI resource matrix covers registration, ownership, rules, edits,
presentation, and runtime behavior. Its commands and evidence are listed in
[resources/README.md](resources/README.md).

The runnable projects are the baseline fixtures. Automated tests copy them and
exercise invalid declarations, unavailable records, graph conflicts, source
ownership errors, and formal command failures. See [TEST_COVERAGE.md](TEST_COVERAGE.md)
for the coverage matrix and repeatable commands.

Integration runners discover a source checkout or built distribution from
marker files. They use temporary workspaces by default and therefore do not
leave reports, build directories, dependencies, or package links in this tree.
Pass `--keep-artifacts` only when the generated files are needed for inspection.

## 运行观测与注解回归

- [Python 双日志与状态接口](python/runtime_observation/README.md)
- [JS/TS AOT 与浏览器状态接口](javascript/runtime_observation/README.md)
- [类型注解与动态模块访问](python/typing_annotations/README.md)
- [RuleContext 共享对象图与实际工作流校验](python/readonly_graph/README.md)
