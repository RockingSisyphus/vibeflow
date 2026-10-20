# Multi-entry workflows and coordination

Implementation of the approved scheme C, started 2026-10-20. This record is an
implementation ledger, not a claim that unfinished stages have passed.

## Contract

- Named entries select one start and its reachable execution scope; shared work
  remains declared once. Legacy workflows without named entries keep their
  existing entry behavior.
- Ordinary SDK Nodes use declared capabilities and explicitly selected Rules.
  Names, shapes, colors and flow kinds do not grant coordination operations.
- Coordination operations are self, call, wait, send, receive and kill. Call
  returns an instance identity; wait is a separate operation. Message matching
  and lifecycle ownership belong to application authors.
- Launch commands and external hosts register instances through the same local
  JSON protocol. A launcher process exiting is not a workflow completion.
- No run groups, automatic child cleanup, implicit process pools, persistent
  message broker, business retries or cross-machine deployment.
- Native `type_used: vibeflow.io` and `io` configuration are migrated to ordinary
  SDK declarations with explicit contracts, port capabilities and Rules. Add
  terminal boundaries where the removed special node supplied implicit ones.
- Historical preview v2 remains readable; execution ABI changes require AOT
  rebuilds. No preview reports are added to AOT execution.

## Stages and evidence

1. Record current behavior and uncommitted AOT changes.
2. Consolidate Python execution support and JavaScript runtime resources.
3. Migrate port examples/tests and remove native IO execution branches.
4. Add named entries, Rule records and capability binding, then coordination.
5. Extend architecture facts, offline viewer, documentation and packaging.
6. Run targeted checks and the canonical full verification batch.

Evidence is retained next to the repository under
`VibeFlow-evidence/workflow-communication-20261020`; generated test projects and
builds use disposable external scratch directories.

### Implementation and acceptance checkpoints

- Shared Python execution support and split JS helpers preserve the existing
  execution model. ABI v9 saves entry scope, independent contracts and complete
  call-path policies. JS emits shared business code once, with prepared entry
  metadata instead of separate copies of each workflow.
- Native IO product fields, parser support and execution/codegen branches are
  removed. Ordinary fixed SDK declarations contribute explicit Capability/schema
  resources. Four sandboxes and fixtures now use explicit terminal boundaries;
  each migrated body gains two real terminal steps. Values and waiting semantics
  remain covered by cross-runtime conformance.
- Both Targets enforce declared operations and Rule grants at the individual
  call path. Source preparation and AOT construction fold the same policy;
  AOT execution does not recheck the graph.
- Python source, Python AOT, Node and a real browser exchange messages through
  actual workflow nodes and host adapters. Tests cover concurrent identities,
  early messages, repeatable wait, cooperative cancellation, unsupported stop,
  invalid JSON completion, launcher exit and caller exit without child cleanup.
- The offline viewer displays entries, operation facts and current-preparation
  target expansion. Browser checks cover default target entry selection,
  nested expansion, internal dragging, 1400% zoom, back navigation, shapes,
  resources and planned declarations. Empty definitions do not fabricate nodes.
- Neutral snapshot preparation uses a subprocess for foreign Target facts;
  each Target retains its own loader. Coordination contains protocol/client/
  host support; Tooling owns CLI dispatch and Python source/AOT preparation.
  Repository layer checks explicitly enforce these boundaries.
- Copyable ordinary SDK templates, migration guidance, protocol tables and both
  distribution profiles use the same interfaces. Package resource inventories
  include the new JS helpers and host adapters. The canonical package check now
  builds the wheel from an extracted sdist before isolated installation.

### Batch history (failures retained)

Evidence lives outside the checkout in the directory named above. Early batch
failures and their subsequent fixes are retained; passing targeted batches do
not overwrite earlier full-gate failures.

- Baseline/refactor: 22 existing tests each; entries: 122; ordinary ports: 44;
  conformance/AOT: 64; initial grants: 8; host/entries: 18.
- Earlier browser batch: 29 passed with real offline Chrome.
- `full-1`: all 18 stages completed, overall FAILED. Pytest reported 29 failed,
  4594 passed and 26 errors. Additional failures were repository checks, sandbox
  expectations, rule parity and distribution documentation. Historical reports
  remain under `full-1*`.
- Repairs addressed stale ABI/resource expectations, registered Architecture
  documents, ordinary-port fixture boundaries, nested entry-provider JSON
  serialization, profile documentation inclusion and Markdown code/link parsing.
- `repairs-2.log`: 352 passed, including real browser checks and the known
  full-1 pytest failures. `checker-1.log`: 55 passed; repository checks report
  zero errors, warnings and informational findings.
- `core-parity4.json`: 326/326 cases match, no process errors. Eleven obsolete
  native-IO parser-only Tooling cases are explicitly retired; the frozen
  historical reference remains unchanged. Baseline-only fixture adapters retain
  historical IoSpec imports solely to execute the old comparison tree.
- An explicit terminal is both a start and an end, so its isolated-node case
  now expects ORPHAN instead of the old receive-only reachability diagnostics.
  Two ordinary process-node controls retain unreachable/end/unconsumed coverage.
- `full-2-verification.json`: all 18 stages completed; 17 passed, with only
  distribution failing. Pytest: 4658 passed; Python sandbox: 103/103; JS sandbox:
  50/50, zero skipped; rule parity: 1210/1210; supplemental rules: 680/680.
  Browser observation, layout, resource sections, both performance suites,
  adaptation, extracted-sdist wheel installation, quality and cleanup passed.
- The distribution failure exposed an independent CLI import-path dependency:
  generating interface templates imported Core only when the developer's
  PYTHONPATH was present. The builder now explicitly uses its checkout's src;
  it does not depend on an installed kernel or ambient development imports.
- `distribution-3.log`: the complete canonical distribution stage passes after
  that fix, including both profiles, extracted archives, source/JS execution and
  relocated self-contained Python AOT. This targeted rerun does not relabel the
  failed full-2 batch as a frozen full PASS. No executor or runtime source changed
  after full-2; repeating unrelated rule/rendering stages was not necessary for
  this build-entry correction.
- `packaged-hosts-1.json`: both profiles independently pass real communication
  from extracted paths containing Chinese characters and spaces. With PYTHONPATH
  removed, the kernel ZIP starts a Python AOT instance and the packaged Node
  host; message/reply, actual completion, repeated wait and cooperative kill all
  pass. No repository kernel is used by those probe processes.

### Performance checkpoint

`coordination-performance.json` records Linux, Python 3.13.13, Node 24.18.0;
there is no predetermined latency threshold. Five fresh launches per host:

| Host | Registration median | First message round trip median | Stop after registration |
| --- | ---: | ---: | ---: |
| Python source | 54.2 ms | 385.2 ms | 383.9 ms |
| Python AOT | 151.4 ms | 85.8 ms | 86.5 ms |
| Node | 39.3 ms | 10.2 ms | 11.2 ms |

Registration precedes Runtime preparation. First message and immediate stop
include its remaining cold preparation; registration alone is not ready-to-work
latency. Twenty steady transport round trips between resident clients have a
1.78 ms median (2.48 ms maximum), excluding business processing. Twenty warm
Python AOT samples have 4.01 ms median Runtime preparation and 0.95 ms execution;
the AOT object is reused with a local Capability stub and tracing disabled.

A 100-common-node JS fixture with 1/2/8 entries produces approximately
355/372/480 kB after shared emission, compared with approximately
340/621/2310 kB in the earlier duplicated prototype. A regression checks that
common node code is emitted once. This is a size observation, not a browser
latency measurement or a Windows performance claim.

## Execution cost, goals and route review

The ordinary-node prototype, removal of native branches, cross-Target round
trip and package integration support the original shared-plan/explicit-host
route. Avoiding duplicated JS entry code reduced growth without introducing a
second interpreter. Rule records and public operation contracts keep privileges
independent of presentation and put transport outside executors.

Implementation and necessary Linux acceptance are complete. The first canonical
batch took roughly 26 minutes and the second about 29 minutes, mostly rule-gap
comparisons. Both retain their actual failures. The second batch left one
standalone packaging import issue, repaired and verified with the full package
stage plus new package-contained host probes; product runtime code remained
frozen. This provides stage coverage without pretending a targeted rerun was a
new frozen full batch. Future meaningful runtime changes still require relevant
checks and the canonical gate. Retain failures and do not edit sources while a
batch is running.

The user clarified that Windows native testing is not a prerequisite for this
feature. Current acceptance is Linux plus real browser and isolated package
execution. Windows path/launch/stop compatibility remains explicitly unverified
locally and is assigned to the added future CI job, not a claim of native PASS.

No groups, pooling, automatic cleanup or graph checks in AOT execution were
added. Application authors still supply host launch/stop behavior and own
background lifecycle. ABI v9 and removed native IO require rebuilding AOT and
migrating old execution configs; preview v2 history remains readable. The prior
uncommitted AOT optimization is preserved. This task does not change the release
version, overwrite existing release archives, commit, push or publish.

If evidence requires a materially different agreed behavior, explain alternatives
and consequences in Chinese before asking for a decision (critical-fork). Keep
independent work progressing and update the acceptance record. Follow
codex-task-alert for required intervention and final completion, and
complete-test-batch for failure retention and batch repair.
