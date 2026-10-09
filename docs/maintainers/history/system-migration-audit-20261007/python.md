# Python migration audit (read only, current working tree, 2026-10-07)

## Scope and evidence

Read all Python target module families project, quality, runtime, sdk and the relevant Tooling composition adapters. Compared f169429 (0.14.2 pre-rule-refactor baseline) to the working tree; the working tree contains extensive uncommitted changes and is the authority for current findings. Did not edit source, run the full test suite or claim a runtime acceptance test. Three tiny in-process probes are saved:

- /tmp/vibeflow-python-migration-probes.json (imports, old adapter, raw visitors)
- /tmp/vibeflow-python-migration-ownership-probes.json (new node Rule handler with explicit current ownership)
- /tmp/vibeflow-python-migration-library-ownership-probes.json (new library Rule handler with explicit current ownership)

All file line numbers below refer to current source unless a commit prefix is given.

## What really migrated

Old f169429 NodeRegistry.register accepted key/class or a decorator and derived config from caller arguments (old registry.py:37-67). Global registry existed. Old quality/source_analysis/__init__.py validate_node_purity pulled class NODE_INFO/CONTRACT and computed effective_effect_scope(info) (:61); trusted bypassed checks (:65), then it invoked numeric validators + visitors + legacy metadata validators.

Current project/registry.py:54-58 rejects anything except NodeDescriptor. Contract/config/rulesets come from that descriptor (:60-63, :97-101), class objects only bind execution. Global registry removed. Tooling project/declarations.py:19-65 obtains selected workflow SDK contributions, registers descriptors and delayed loaders, attaches contribution catalogs and rule loaders. quality/workflow/validation.py:38-50 executes selected import/static Rules, :79 workflow Rules; quality/rule_adapter.py:147+ iterates registry.rulesets(node.type_key). effect_scope now comes from selected Rules and typed effect_policy records (rule_adapter.py:63-78, :225-251); it no longer derives IO/trusted permission from flow_kind or external.

Therefore this is not a complete old NodeRegistry pipeline running alongside a new one. The remaining problems are narrower: active old role heuristics, remaining coarse checks behind new Rule wrappers, public compatibility models/analysis APIs, and dead files/functions.

## Confirmed active old-idea residuals

### PY-1. New ownership coexists with old module-name role/allowlist judgments

Call chain: validate_graph_health -> execute_python_node_rules -> execute_rule_plan -> python_rule_handlers()['vibeflow.no_side_effects'] -> no_side_effects (quality/rules/effects.py:83-90) -> old NodePurityVisitor._check_import (quality/source_analysis/visitors.py:373-386).

The new source ownership model is based on declarations and actual resolved import paths (project/source_membership.py:20-46; quality/rules/source_ownership.py:9-50). But the old visitor still uses names containing `nodes`, `boundary`/`boundaries`, `base_lib` to infer role (source_analysis/helpers.py:99-113). In particular `base_lib.*` must also match PurityPolicy.allowed_base_lib_modules even when NodeDescriptor.base_libs and the resolved library declaration already authorize it (:380-385). `_authorized_library_imports` in the new handler (:160-176) exempts correctly declared BaseLib exports from the `nodes` check; it does not exempt the later `base_lib` allowlist check.

Probe with a declared Node using base_libs=['audit.lib'], explicit owner entry for a pure library and the exact same value import: source_ownership finds no problem in all three variants; no_side_effects emits no finding for plain.calc, NODE.BASE_LIB.BASE_LIB_UNDECLARED for base_lib.calc, no finding for nodes.calc. The only changed input is the library module name.

Important formal-composition boundary: Tooling project/core.py:23 sets initial policy using workspace.policy only. contributed_resources.py:28-30 makes native BaseLibRegistry entries but does not update PurityPolicy. workspace_service.py:373-398 reconstitutes the old config resources and fills allowed modules from config `base_lib.modules` through config_base_lib_policy (project/resources.py:103-122). It does not read NodeDescriptor.base_libs to fill the allowlist. Thus an old config selection can mask this mismatch; a pure SDK dependency alone does not. Parent completed the formal CLI comparison at /tmp/vibeflow-migration-cli-probes/summary.json: using sandbox/python/multifile_resources and the same Node.base_libs=['demo.math'] declaration, put the identical library under ordinary/base_lib/boundary/nodes/runtime module directories and import it inside run_pure. ordinary PASS, base_lib FAIL NODE.BASE_LIB.BASE_LIB_UNDECLARED, boundary FAIL NODE.PURITY.BOUNDARY_IMPORT, nodes/runtime PASS. Move those same imports to the top level and all five PASS (new handler top-level path only checks known_modules). Thus the leftover role policy depends on both module name and import placement, not just authoritative declarations.

Historical proof: f169429 visitors.py:437-442 had the same base_lib name/allowlist branch. The mechanism has been retained inside the new Rule handler rather than replaced by declaration ownership.

### PY-2. A declared BaseLib support file can be rejected just for a directory/module name

Call chain: same selected no_side_effects Rule, base_lib subject -> rules/effects.py:19-42 -> _BaseLibAstScanner -> rules/base_lib_effects.py:209-219. This rejects every import containing any of `boundary`, `boundaries`, `nodes`, `plugin`, `plugins`, `runtime` (constant :43-45), irrespective of current source owners or declared dependencies.

Probe: a library and its explicitly registered support file share the same BaseLib owner. ownership_findings=[] for helpers.calc, runtime.calc and plugins.calc. no_side_effects=[] for helpers.calc, but BASE_LIB.FORBIDDEN_PROJECT_IMPORT for runtime.calc and plugins.calc. These need not be Node/plugin/runtime resources at all; the folder name dictates the answer. f169429 project/base_lib.py:44-46 and :376-386 supplied the same mechanism.

### PY-3. A second legacy BaseLib detection path remains inside node effect checks

quality/rules/effects.py:135-147 selects helpers solely when their module name contains base_lib, then rescans the entire module using _BaseLibAstScanner and emits NODE.BASE_LIB.INDIRECT_VIOLATION. Current reached BaseLib review already uses actual BaseLibDescriptor entries and selected Rulesets (project/resource_rules.py:94-158). This leaves a name-triggered old library check alongside declared library review. Plainly changing a module name changes whether this additional scan occurs. Source-role-independent AST traversal is not itself a migration fault; this special path is the concern.

Related inert residue: project/source_closure.py:97,133 still sets PythonSourceFact.is_base_lib via path segment `base_lib` (:259-260). Current consumers do not read that fact; it is a dormant old-role flag, not an additional active permission grant.

### PY-4. The old monolithic purity visitor is wrapped by the new effect Rule and still contains other rule topics

The visitor is not merely an AST fact extractor. Selected `vibeflow.no_side_effects` still checks run_pure yield/async, contract return keys, mandatory output keys, internal while loops, node direct calls, class resource field names etc. Examples: visitors.py:224-229 class resource/async; :243-246 yield; :309-317 prohibits while; :341-355 compares output contract; :414-417 node direct call. no_side_effects params in core/rules/builtin/effects.py:7-11 expose effect_scope and policy only. Node interface is separately declared (:12-13) but some interface/contract checks remain bundled with effects.

This is a maintainability/independent-selection issue, not a proof that those checks execute without any Ruleset selection. Empty Node.rulesets bypasses them correctly. Users cannot select only the built-in effect check while independently relaxing these bundled old restrictions; they must implement a different Rule. A uniform plug-in architecture may still intentionally ship coarse built-in Rules, so treat this as a design residual to assess, not an automatic bug.

### PY-5. Boundary vocabulary in diagnostics needs an explicit current interpretation

The retained visitors still emit suggested_fix_type='move_to_boundary' and mention Context/boundary fields. Current PluginRegistry rejects boundary plugin types, but native I/O nodes and Host/lifecycle boundaries remain valid concepts, and current examples still use boundary names. The wording alone is therefore NOT sufficient proof of an obsolete mechanism or invalid advice. Only guidance that specifically assumes removed boundary plugin/metadata interfaces should be updated. This is a vocabulary/documentation review item, not an independently confirmed functional defect.

## Public old models and APIs retained

### PY-6. Legacy BaseLib adapter remains public and loses new Rulesets

project/descriptors.py:67-102 base_lib_descriptor_from_registry translates native BaseLibResource back to a portable BaseLibDescriptor but copies only identity/metadata/implementation, omitting resource.rulesets. adapt_base_lib_registry (:123-151) still merges legacy registry metadata with a static catalog, emits DESCRIPTOR.LEGACY_BASE_LIB.* diagnostics and source='python:BaseLibRegistry'. Both are lazy-exported as the stable frontend API in project/__init__.py:50-59.

Probe: BaseLibRegistry.register(...rulesets=('custom.review',)) yields native.rulesets=('custom.review',) but base_lib_descriptor_from_registry(...).rulesets=(). So the public bridge can silently strip a newly selected rule. No production src callers of these adapter functions were found; tests/tooling/test_descriptors.py and tests/targets/python/test_resource_rule_selection.py exercise them. Callers who only use official workflow SDK loading do not go through this adapter. Classify as retained public legacy path with concrete metadata loss, not active mainline loss.

### PY-7. BaseLibRegistry/PluginResourceRegistry survive in the new mainline as secondary representations

Tooling project/contributions.py:14-49 turns SDK catalogs into these old native registries, then creates ConfigResources and WorkspaceResourceRegistries; project/resources.py:158-262 defines them. lifecycle_registry (:52-92) similarly binds modern selected factory declarations to the existing native PluginRegistry hook executor. Existing presentation/config resource adapters consume BaseLibResource/PluginResource/PluginInfo.

This reuse alone is legitimate language binding and does not restore project registry factories or class metadata authority. But the old registry/resource representation still determines old config-selection and policy plumbing, and blocks deletion of resources.py plus the associated Tooling adapters. The problem to address is the old role/allowlist/config behavior in PY-1, not the word Registry.

### PY-8. Old metadata types, normalizers and Context/Registry APIs remain public, with no mainline authority

project/node.py:28-45 NodeInfo/NodeContract still coexist with current NodeDescriptor/NodeContractDescriptor. They are exported through project/__init__.py:68-70 and targets/python/__init__.py:20-26. New implementation Rules and metrics annotate against old types but are actually passed the new descriptors (e.g. maintainability.py:31-33). Fixtures deliberately build new descriptors from old NodeInfo/NodeContract in tests/fixtures/support/declarations.py. This preserves test/API vocabulary without putting NODE_INFO/CONTRACT back in runtime authority.

project/resources.py:272-317 normalize_plugin_info and normalize_base_lib_info still read PLUGIN_INFO/plugin_info/BASE_LIB_INFO-shaped legacy objects and require old fields. They have no production or test function-call sites now; they remain exported and imported by Tooling resource facade. In f169429 plugin_loader.py:139 and Tooling project/resources.py:267 actively called them; those old loaders/calls have been removed.

project/context.py:19-75 old mutable dot-key Context remains public/lazy exported (:48), only tests/targets/python/test_context.py call it. Runtime uses current RuntimeContext/value structures, not this object. project/registry_base.py:9 generic mutable RegistryBase remains public/exported (:104), while current NodeRegistry no longer subclasses it. No src consumers or tests that instantiate it were found. These are explicit retained public APIs, so deletion requires an API support decision even though mainline no longer depends on them.

## Whole files and dead functions

### PY-9. Old Python BaseLib scan API remains usable outside the new selection model

project/base_lib.py:49-101 analyze_base_lib_source fixes its selection to built-in vibeflow.base_lib (:89-96); :182-205 scan_base_lib discovers `project_root/base_lib` or allowed_base_lib_paths (:217-239) and scans all *.py. Neither API accepts SDK catalogs or resource-selected Rulesets. It also retains inspect-based node_base_lib_imports (:208-214), old module-name library dependency discovery (:160-178) and summary/closure logic (:129-157,284-327).

Mainline now uses declared source context + review_reached_base_libs. These old functions are public exports in project/__init__.py:19-26 and quality/base_lib.py:3-4. scan_base_lib is still exercised by tests/targets/python/strict_node_purity.py, strict_effect_scopes.py, strict_imports_and_smells.py, tests/targets/python/test_analysis.py, tests/tooling/strict_base_config_examples.py. Calling them proves the old standalone model remains supported, not that the regular workflow still runs the old automatic scan. This is a retained compatibility/analysis surface with a different selection contract.

### PY-10. Completely shadowed old quality/rules.py

`quality/rules.py` and `quality/rules/` exist together. Normal import vibeflow.targets.python.quality.rules resolves to the new package __init__.py. The old side_effect_findings at rules.py:11-64 is never exported by the package. Direct spec_from_file_location loading raises ImportError because rules.py:8 imports SIDE_EFFECT_ATTR_CALLS/SIDE_EFFECT_CALLS/SIDE_EFFECT_IMPORT_ROOTS removed from current quality/source.py. Thus it is broken, shadowed leftover source. It was byte-for-byte retained from f169429, but f169429 already used a different local source.py side-effect implementation, so some duplicate debt predates this rebuilding phase.

### PY-11. Unused whole modules still shipped or exported

- quality/imports.py:9-120: old import graph builders; no src/test consumers. Same source as f169429. Current source.py:167-222 retains another import-site implementation; core/quality/evaluator.py:233+ contains current graph builders. Whole-file dead duplicate.
- quality/workflow/base_lib.py:10-61: old report conversion/dependency helpers. No current callers; still lazy-exported through workflow/__init__.py:11-22. Old f169429 workflow/validation.py:224,236 and CLI node.py:169,197 called them; replaced by Rule reports.
- quality/base_lib.py:3-4: compatibility forwarding file to project/base_lib.py; no src direct consumer. It remains importable publicly.
- runtime/config.py:1-53: explicitly labelled compatibility adapter forwarding core/config/scope and translating an exception. Only tests/core/test_core_neutral_seams.py:20 calls it; runtime itself uses core scope APIs.
- project/context.py and project/registry_base.py as PY-8 above.
- project/descriptors.py as PY-6 above; tests/public API retain it, not mainline.

All seven named whole modules above are retained from f169429; context.py, registry_base.py, quality/imports.py, quality/workflow/base_lib.py, quality/base_lib.py, runtime/config.py and the shadowed quality/rules.py are unchanged by diff to that baseline. Do not call exportable/test-covered adapters unreachable; distinguish them from quality/imports.py and shadowed rules.py.

### PY-12. Dead legacy functions left in otherwise live modules

Confirmed no call/reference outside their own definitions/import-only/export sites across current src/tests and parent's lexical inventory including sandbox/tools/distribution (excluding archived migration fixtures):

- source_analysis/helpers.py:14 _validate_key_tuple, :23 _validate_semantics, :37 _validate_schema_mapping, :82 _is_inputs_subscript, :183 _dedupe_violations. First two are imported by validators.py but not called. _tokens is NOT dead: _looks_temporary_key calls it.
- source_analysis/validators.py:23 _validate_source_size, :31 _validate_complexity_metrics, :35 _validate_call_chain_metrics, :133 _validate_contract_examples_shape; the internal _numeric_violations (:60) and _core_metrics (:42) only serve those dead entry functions. _validate_architecture_smells (:83) is still used by new maintainability and must not be deleted with the module.
- source_analysis/source.py:25 _parse_source is dead; _source_info (:11) still serves the public inspect/class runtime-dispatch analysis API.
- project/resources.py:272 normalize_plugin_info / :298 normalize_base_lib_info as PY-8 (public exports); their helper field parsing only exists for those routines.
- project/base_lib.py:129 summarize_base_lib_dependency_chain, :208 node_base_lib_imports have no consumers beyond public exports; :160 base_lib_imports_from_source only serves node_base_lib_imports. These are public legacy APIs rather than wholly private dead code.

Historical attribution: f169429 source_analysis/__init__.py:72-79,105,173,218,242 invoked the now-dead numeric/parsing/deduping functions; old validators.py:51 invoked contract-examples shape. Removing that old orchestrator left these helpers behind during this migration. _validate_schema_mapping and _is_inputs_subscript require checking earlier history to establish whether already dormant at baseline; do not attribute every line to the latest refactor.

Preexisting extra runtime debt: runtime/engine.py:359-398 _execute_graph_block and :400-406 _assert_block_eligible have no references in src/tests/sandbox/tools/distribution. They are already present in f169429; the current _run_block_steps (:351-357) dispatches graph_block(self._plan).callable and never invokes either method. This is older dead execution code, not proof of Rule/Node migration failure.

## Negative findings / retained algorithms that should not be called legacy system

- Global registry, old class metadata registration/decorator and policy hooks are genuinely removed from mainline. No effective_effect_scope(info) or trusted/external skip remains in current Python target.
- flow_kind still determines native terminal scheduling/global-state lock behavior (runtime/planning.py:419,489; execution_lock_mixin.py:235); design explicitly preserves native execution identity, so those checks are not old hidden effect grants.
- Runtime expects run_pure and instantiates Python classes; that is the native Python ABI, not a failure to use SDK/plugin contributions.
- AST effects/call-chain calculations, core numeric implementation evaluator, graph compiler, registry queries and language-specific runtime hook dispatcher are appropriate reusable algorithms/binding facilities. The migration does not need to rewrite working AST traversals solely to erase the old filename.
- planned.py/file.py source safety is reached through the selected workflow Rule, not an unconditional second validator in regular graph health. Stub execution signature check is native ABI. Do not count those as a bypass based merely on old source.
- No exhaustive dynamic reachability proof was performed for arbitrary third-party use of exported APIs. Dead/private findings have static + historical evidence; public compatibility surfaces are specifically labelled.
