# A/B Quality Improvement Plan

This document records the proposed deterministic improvements for the current quality systems:

- A: `topology-kernel quality-check`, the generic Python code quality scanner under `src/topology_kernel/devtools/`.
- B: kernel health governance for topology projects, nodes, plugins, config, flow, and `base_lib`.

No item in this plan requires model calls. The plan intentionally avoids copying large reference subsystems.

## Current Scope

A should stay a generic Python structure and complexity checker. It should help users find the worst files/functions first, but it should not become a full linter, type checker, or multi-language analyzer.

B should stay a topology/runtime health gate. It should enforce policy, node purity, `base_lib` safety, graph flow semantics, plugin/schema health, and runtime refusal. It should not absorb A's generic repo-structure rules.

## Proposed Changes

Status after implementation pass:

| Area | Priority | Change | Status |
| --- | --- | --- | --- |
| B | P0 | Apply policy downgrades/exemptions after findings are produced | Done |
| B | P0 | Run module-level purity scan in normal graph health | Done |
| B | P0 | Add decision-loop exit validation | Done |
| A | P0 | Add top offenders for files/functions | Done |
| A | P0 | Add a simple quality score | Done |
| A | P0 | Add function parameter-count rule | Done |
| A | P1 | Improve file discovery hygiene | Done, minimal generated/vendor/sensitive-file skips only |
| B | P1 | Make duplicate/collapsed explicit edges visible | Done |
| B | P1 | Add a deterministic rule catalog | Done, small catalog for touched/frequent rules |
| B | P2 | Add shared import/call primitives | Done, via existing `ast_rules.py` helpers |
| B | P2 | Add optional architecture report | Done, standalone report function only; not a hard gate |

| Area | Priority | Change | Expected Effect |
| --- | --- | --- | --- |
| B | P0 | Apply policy downgrades/exemptions after findings are produced | Policy becomes an actual health-report control plane instead of only parsed metadata |
| B | P0 | Run module-level purity scan in normal graph health | Runtime health catches node module top-level side effects, not only class-level purity issues |
| B | P0 | Add decision-loop exit validation | A cycle is allowed only when a decision node has an exit edge leaving the cycle and reaching a terminal end |
| A | P0 | Add top offenders for files/functions | Reports show the most useful repair targets first |
| A | P0 | Add a simple quality score | `PASS`/`CONCERNS`/`FAIL` stays authoritative, with a numeric trend signal added |
| A | P0 | Add function parameter-count rule | Detects over-wide function interfaces in generic Python code |
| A | P1 | Improve file discovery hygiene | Avoid scanning generated/vendor/cache/sensitive files when practical |
| B | P1 | Make duplicate/collapsed explicit edges visible | Avoid silently hiding repeated or conflicting explicit edge declarations |
| B | P1 | Add a deterministic rule catalog | Rule IDs, severities, layers, and suggested fixes become auditable and documentable |
| B | P2 | Add shared import/call primitives | A, node purity, and `base_lib` can reuse the same conservative AST import/call logic |
| B | P2 | Add optional architecture report | Provides project-level architecture insight without becoming a default hard gate |

## Items Explicitly Excluded

| Excluded Item | Reason |
| --- | --- |
| Cache/manifest incremental scanning | Not needed for the current scope |
| Model calls or semantic extraction | Explicitly outside the requirement |
| Tree-sitter/multi-language analyzer | Too large for the current Python/topology scope |
| HTML dashboard | Markdown/JSON/text are enough until a concrete need appears |
| Comment-ratio hard rule | Noisy and easy to game |
| Naming-convention hard rule | Better handled by existing linters if needed |
| Regex error-handling rule | Current side-effect/purity checks are more aligned with this project |

## Second-Pass Verification

The sections below are updated after re-reading the project code and the two reference projects.

### Project-Code Check

| Item | Current Project State | Decision |
| --- | --- | --- |
| A top offenders | `QualityReport.to_dict()` reports summary, scope summary, files, dependency graph, directory graph, prefix clusters, structure summary, longest dependency chain, errors, and warnings. It does not rank worst files/functions. | Keep. This is not implemented and is useful for prioritization. |
| A quality score | A has only `PASS`/`CONCERNS`/`FAIL`. No numeric score exists in `QualityReport` or text output. | Keep, but make it a trend signal only. `PASS`/`CONCERNS`/`FAIL` remains authoritative. |
| A parameter-count rule | `QualityThresholds` has no `max_function_params`; `FunctionQuality` has no `param_count`; `_function_shape_findings()` checks only lines, branches, and nesting. | Keep. Add `QUALITY.FUNCTION.TOO_MANY_PARAMS` with minimal AST arg counting. |
| A discovery hygiene | `_iter_python_files()` uses `Path.rglob("*.py")` plus excluded directory names. Defaults already exclude many common directories, but there is no `.gitignore` or sensitive-file handling. | Keep as P1 and keep it small. Do not add a full ignore engine unless real scans need it. |
| B policy downgrades/exemptions | `policy.py` parses and merges `rules.downgrades`, `rules.exemptions`, and `rules.downgradeable`; plugin relaxations are audited. No general post-processing step applies these entries to produced `HealthFinding`s. | Keep. This is a real gap: policy metadata exists but does not yet control final health severities/skips. |
| B module-level node scan in graph health | `inspect-node` calls `validate_node_class(..., scan_module=True)`. Normal graph health calls `validate_node_class(...)` without `scan_module=True`. `purity.py` already supports module scanning through `ModulePurityVisitor`. | Keep. This is already implemented as a capability, but not wired into the normal health path. |
| B decision-loop exit validation | `compiler.py:_validate_routed_cycles()` rejects cycles without a decision node. `health_flow.py` checks reachability to end and decision branch reachability, but it does not require a decision inside a cycle to have an exit edge leaving the cycle and reaching a terminal end. | Keep. Add `GRAPH.CYCLE.MISSING_DECISION_EXIT` in flow health, not compiler. |
| B duplicate/collapsed explicit edges | `graph_config.py` validates unknown edge endpoints. `compiler.py:_merge_edges()` silently folds explicit edges by `(source, target)` and keeps `existing.when or edge.when`. | Keep as P1. Do not build a full graph diagnostics subsystem; only surface duplicate/conflicting explicit declarations. |
| B deterministic rule catalog | Rule IDs are constructed throughout the codebase; no central catalog or generated rule metadata exists. | Keep, but start with a small static catalog for touched/new rules. Do not block P0 on full catalog coverage. |
| B shared import/call primitives | A, node purity, and `base_lib` each have AST/import logic. Docs already mention shared AST helpers as a future candidate. | Keep as P2. Useful, but not needed before the concrete health gaps above. |
| B optional architecture report | There is no `god node`, `affected`, query/path, or architecture report feature in the kernel source. | Keep as P2 only. It should be separate from runtime refusal and not a hard gate. |

Conclusion: the P0 items are not redundant with existing project code. The only item that needed narrowing is graph diagnostics: B already has substantial flow/topology integrity checks, so the plan should add only decision-loop exit validation and explicit-edge duplicate/collapse visibility.

### Reference-Code Check

| Reference Area | Useful For | Copyability |
| --- | --- | --- |
| `references/fuck-u-code/src/cli/output/stats.ts` | A top offenders and project stats. `collectWorstFunctions()` and `aggregateProjectStats()` show the right reporting shape. | Do not copy. Reimplement a small Python version over existing `QualityReport.files` and `FunctionQuality`. |
| `references/fuck-u-code/src/scoring/index.ts` | A score/aggregation concept: normalized metrics, averages, min/max/median. | Do not copy. Its weight handling is not suitable because category weights are effectively applied once per metric. Use the idea only. |
| `references/fuck-u-code/src/metrics/size/parameter-count.ts` | A function parameter-count rule. | Do not copy. Reimplement with Python `ast.arguments` and current `QualityThresholds`. |
| `references/fuck-u-code/src/analyzer/file-discovery.ts` and `src/gitignore/parser.ts` | A discovery hygiene: common excludes, `.gitignore`, nested ignore behavior. | Do not copy. The code depends on Node/TypeScript libraries and is broader than needed. Adapt only the minimal behavior if scans demand it. |
| `references/fuck-u-code/src/metrics/types.ts` | A possible report model vocabulary: metric result, aggregated metric, severity, locations. | Reference only. A already has dataclasses; avoid introducing a parallel metric framework. |
| `references/fuck-u-code/src/parser/tree-sitter-parser.ts` | Parameter counting and multi-language parsing examples. | Do not use for this plan. A should stay Python stdlib AST; Tree-sitter is out of scope. |
| `references/graphify/graphify/diagnostics.py` | B duplicate/collapsed edge visibility. It reports duplicate edges, same-endpoint collapse, dangling endpoints, self-loops, and variant groups. | Reference only. B already has typed graph/config checks; implement small warnings for explicit-edge duplicates/conflicts instead of porting diagnostics. |
| `references/graphify/graphify/detect.py` | A discovery hygiene: sensitive-file suppression, generated/noise dirs, `.gitignore`/custom ignore ideas. | Reference only. Adapt a few patterns if needed; do not copy the full multi-corpus scanner. |
| `references/graphify/graphify/symbol_resolution.py` | B future shared import/call primitive. Valuable rules include import-guided resolution, unique-candidate checks, and ambiguity avoidance. | Reference only. AST shapes and kernel health objects differ, so copy-paste would add risk. |
| `references/graphify/graphify/analyze.py`, `affected.py`, `report.py` | B optional architecture report: god nodes, surprising connections, import cycles, affected nodes, report sections. | Reference only and P2. Do not pull this into the runtime health gate. |

No reference module should be copied wholesale. The references are valuable mainly as design examples and threshold/reporting calibration. The current kernel data models are different enough that small native Python implementations are safer.

### Updated Implementation Order

Implementation status: items 1-11 are done. Item 11 remains optional and is not wired into runtime refusal.

1. B P0: apply policy downgrade/exemption post-processing to `HealthFinding`s.
2. B P0: wire `scan_module=True` or equivalent module-level purity checks into normal graph health.
3. B P0: add `GRAPH.CYCLE.MISSING_DECISION_EXIT` in `health_flow.py`.
4. A P0: add parameter-count collection and `QUALITY.FUNCTION.TOO_MANY_PARAMS`.
5. A P0: add top offenders to JSON/text output.
6. A P0: add a simple score derived from existing findings and metrics.
7. B P1: surface duplicate/collapsed explicit edge declarations with small warnings.
8. A P1: improve discovery hygiene only if current excludes miss real generated/vendor/sensitive files.
9. B P1: add a small deterministic rule catalog for new and frequently emitted rules.
10. B P2: extract shared import/call primitives.
11. B P2: add optional architecture report outside the hard health gate.

## Likely Code Touch Points

| Change | Files |
| --- | --- |
| A parameter count | `src/topology_kernel/devtools/code_quality_types.py`, `src/topology_kernel/devtools/code_quality.py`, `src/topology_kernel/cli.py`, quality tests |
| A top offenders and score | `src/topology_kernel/devtools/code_quality_types.py`, `src/topology_kernel/devtools/code_quality_format.py`, `src/topology_kernel/devtools/code_quality.py`, CLI/text/JSON tests |
| A discovery hygiene | `src/topology_kernel/devtools/code_quality.py`, `src/topology_kernel/devtools/code_quality_types.py`, discovery tests |
| B policy application | `src/topology_kernel/policy.py` or a tiny policy findings module, `src/topology_kernel/health.py`, policy tests |
| B graph-health module scan | `src/topology_kernel/health.py`, node purity tests |
| B decision-loop exit | `src/topology_kernel/health_flow.py`, graph flow tests |
| B explicit-edge visibility | `src/topology_kernel/compiler.py` and/or `src/topology_kernel/health_flow.py`, compiler/health tests |
| B rule catalog | new small catalog module plus docs/tests for touched rules |

## Guardrails

Keep the changes boring and local:

- Do not add dependencies for P0.
- Do not add model calls.
- Do not add cache/manifest behavior.
- Do not replace existing A AST analysis or B topology health logic.
- Do not turn optional architecture reporting into a runtime refusal rule.
- Prefer one small helper per repeated concern over a new framework.
