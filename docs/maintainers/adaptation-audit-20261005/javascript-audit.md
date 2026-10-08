# Tooling / JavaScript SDK and Rule adaptation audit

Read-only VibeFlow audit. All independent probes and generated artifacts are in this /tmp directory. No VibeTrain source, workflow, or training was read or executed. No repository source was edited.

## Confirmed defects

### 1. The project-structure Rule still uses the old Node/BaseLib/Plugin layer model

The current multi-file SDK demo, copied into a `src/` directory to remove unrelated root-file limits, passes `validate` but fails `quality-check` with exactly:

- `QUALITY.STRUCTURE.BASE_LIB_UPWARD_IMPORT`: `src/math.ts -> src/math_support.ts` (explicit BaseLib support).
- `QUALITY.STRUCTURE.NODE_UNDECLARED_PROJECT_IMPORT`: `src/node.ts -> src/node_support.ts` (explicit Node support).
- `QUALITY.STRUCTURE.PLUGIN_NODE_IMPORT`: `src/plugin.ts -> src/node.ts` (fixed plugin declaration importing its own contributed Node).

Evidence: `probes.py quality`, `nested-validate.json`, `nested-quality.json`, `probes-report.json`.

Code: `tooling/application/javascript/cli.py:777-799` only maps Node/BaseLib/lifecycle Plugin entry source; `core/quality/root_structure.py:214-220` still treats every Node local import as BaseLib-only and every Plugin-to-Node import as illegal. `core/rules/builtin/project_quality.py:136-137` makes this an active formal structure Rule. Python `tooling/application/python/project/quality.py:136-160` is the same root cause, already independently confirmed by the parent agent.

Recommended design: supply the shared resource ownership facts, roles (entry/support/declaration), and explicit resource relationships to the structure Rule. Do not add a directory-name exception or disable the project Rule. This is one unified adaptation theme across both Targets.

### 2. JS compiler lifecycle graph transport recursively expands the native Nodeset registry

`compiler-nodeset-validate.json` is PASS; the same fixed plugin and Nodeset graph `build` returns exit 1 / `VF_BUILD_FAILED: maximum recursion depth exceeded`. No business Node is executed by the probe.

Evidence: `extra_probes.py compiler`, `compiler-nodeset-build.json`, `extra-report.json`; `probes.py graph` also shows `graph.nodesets["body"].graph.nodesets is graph.nodesets` and `RecursionError` directly.

Code: `targets/javascript/build/plugin_hooks.py:93-105` projects graph/compiled before lifecycle hooks; `195-219` recursively walks every dataclass field without finite native graph representation. The Rule path already uses declarations plus references in `targets/javascript/build/rule_session.py:148-162`, so the lifecycle path missed that adaptation.

Recommended design: one finite native graph transport used by the Rule and compiler-hook paths, retaining the stable graph metadata and Nodeset reference identities. A generic dict/list projection must not tree-expand the shared native graph.

### 3. Dispose failure skips session cleanup and leaves the worker running

A real worker factory whose `dispose` throws produces `worker_alive_after_failed_exit=true`, with stdin still open, the materialized-resource context retained, and stderr open. The probe then closes only the worker it created; `owned_worker_cleanup_exit=0` confirms cleanup. The input factory has no timer or business logic.

Evidence: `probes.py dispose`, `probes-report.json`.

Code: `targets/javascript/build/plugin_session.py:133-156`, especially the early raise at 139; worker `resources/plugin_worker.mjs:262-265` does not remove a session when dispose throws; `targets/javascript/sdk/loading.py:46-48` stops releasing later definitions when the first close raises.

Recommended design: attempt disposal of every opened session, unconditionally close process/pipes/temp resources in finally, then report the primary disposal failure. Worker-side deletion should also be final even when the user callback fails. Preserve the original in-flight exception when cleanup fails during another failure.

### 4. AOT build omits selected Rulesets of indirect Host dependencies

`demo.host` depends on `audit.child`; child explicitly registers an unused 501-line support file and selects `vibeflow.host_extension`. Same workflow:

- `validate` rejects `audit.child` with `BASE_LIB.SOURCE.MAX_LINES`.
- `review-rules` displays the child's effective Ruleset.
- `prepare_project_build` passes; its `used_host_extensions` contains both child and parent, but its Rule subjects only contain the parent.
- Actual CLI AOT `build --target node --profile esm-module` succeeds, exit 0 / PASS.

Evidence: `extra_probes.py host`, `host_build_probe.py`, `host-dependency-validate.json`, `host-dependency-preview.json`, `host-build-prepare-report.json`, `host-dependency-build.json`. The final workflow config only explicitly selects `demo.host`; the child is selected through the native dependency relation.

Code: `tooling/application/javascript/build.py:227-230` forms the Rule scope from direct config selections; `382-405` expands Host dependencies only after Rule execution. By contrast `audit.py:169-177` calls `_host_extension_records`, whose dependency visitor is at `731-797`, before the same engine is executed.

Recommended design: resolve the active, disabled and planned resource dependency closure once and use it for formal checks, build bindings, preview and architecture. Every selected dependency retains its own Rule selection; its support does not inherit the parent's permissions.

## Performance duplication / maintainability

- `targets/javascript/build/rule_session.py:222-238`: analysis cache is keyed by the entire request, including rule topic and subject. `253-260` sends different topics and subject IDs for the same frozen sources; `toolchain.py:380-413` starts a new process per miss. Also `run_javascript_rules:456-457` and each `run_javascript_workflow_rules:542-543` create a separate cache. Thus one audit/build can repeatedly parse the same source across Node import/static and workflow import/static. This is a code-confirmed duplication opportunity; no broad performance benchmark was run. Share immutable syntax/import/metric extraction within one explicit JS check session, while retaining per-subject policies and per-call Rule results.
- `plugin_session.py:71-74` has a standalone Rule preflight for arbitrary raw plugin dictionaries, and `rule_extensions.py:23-50` reconstructs an incomplete descriptor, omitting support and BaseLib facts and detaching Catalog worker provenance via `replace`. However the SDK's actual `JavascriptPluginBinding.to_dict` (`frontend/bindings.py:143-166`) carries no `rulesets`, so this branch is not used by the normal compiler SDK binding. This is a redundant, diverging maintenance path, not a confirmed normal SDK failure. Consolidate the native binding/check boundary instead of adding another compatibility branch.

## Candidates not confirmed

- Normal `inspect-resources` / `review-rules` worker leak: not reproduced. The selected Catalog owns worker retention through `weakref.finalize` (`sdk/loading.py:39-48`); each real command opened 1 worker, closed 1, left 0 retained Catalog entries and no alive workers. See `catalog-lifetime-report.json`. The disposal-failure defect above is independently confirmed; lack of an explicit close is not by itself a permanent leak.
- JS `review-rules` omitting reached BaseLib: the Python-only source-reach calculation is visible, but no mismatch was confirmed for supported explicit `base_libs` / `dependencies`. JS formal initial ownership selection and preview both follow those declarations. The proven Host build mismatch is separate and should not be labeled as this tentative preview issue.
