# Rules Guide — Where to Find Project Rules

Reference for the rulecheck agent. Focus on rules that **linters can't enforce** —
architectural principles, patterns, and conventions from CLAUDE.md.

## Primary Source: `CLAUDE.md` (Root)

Read this file thoroughly. Every section contains enforceable rules.

### Engineering Principles (each is a concrete rule, not a slogan)

| Principle | What to Look For |
|-----------|-----------------|
| **Fail Fast** | Silent fallbacks, swallowed errors, catch blocks that return defaults instead of throwing, silently broadened permissions |
| **KISS** | Clever meta-programming, hidden dynamic behavior, convoluted control flow, magic that obscures intent |
| **YAGNI** | Config keys with no caller, speculative abstractions, feature flags for unplanned features, partial fake support |
| **DRY + Rule of Three** | Same pattern copy-pasted 3+ times without extraction; OR premature abstractions extracted from only 1-2 uses |
| **SRP + ISP** | God modules mixing policy/transport/storage, fat interfaces with unrelated methods, modules doing too many things |
| **Determinism** | Flaky tests with timing dependencies, network-dependent tests without guardrails |
| **Reversibility** | Mixed mega-patches, changes with unclear blast radius |

### Logging Rules

| Rule | Violation |
|------|-----------|
| Use Pino structured logger | `console.log`, `console.error`, `console.warn` in production code |
| Event naming: `{domain}.{action}_{state}` | Events like `processing`, `handling`, `doing_stuff` |
| Standard states: `_started`, `_completed`, `_failed` | Unpaired events (a `_started` without matching `_completed`/`_failed`) |
| Never log secrets | Logging variables named token, key, password, secret without masking |
| Include context in logs | `log.error("failed")` without IDs, durations, or error details |
| Log levels matter | Using `log.info` for errors, or `log.error` for non-errors |

### Error Handling Rules

| Rule | Violation |
|------|-----------|
| Log with structured context | `catch(e) { throw e }` without `log.error({ err, contextId })` |
| Use `classifyIsolationError()` | Git operation catch blocks that don't classify the error for users |
| Surface errors to users | Catch blocks that silently swallow without notifying the user |
| Include error type info | `log.error({ error: err.message })` instead of `log.error({ err, errorType: err.constructor.name, err })` |
| Clear error messages | `throw new Error("failed")` without saying what failed or why |

### Import Rules

| Rule | Violation |
|------|-----------|
| No generic `import *` from `@archon/core` | `import * as core from '@archon/core'` |
| Use `import type` for type-only | `import { MyType } from '...'` when MyType is only used as a type |
| Namespace imports for submodules only | `import * as conversationDb from '@archon/core/db/conversations'` is fine |
| Specific named imports for values | `import { handleMessage, pool } from '@archon/core'` |

### Git Safety Rules

| Rule | Violation |
|------|-----------|
| Never `git clean -fd` | Any use of `git clean` (use `git checkout .` instead) |
| Use `execFileAsync` not `exec` | `exec("git ...")` instead of `execFileAsync("git", [...])` |
| Use `@archon/git` functions | Direct git shell calls when an `@archon/git` function exists |

## Violation Categories by Impact

### Tier 1 — Critical (fix first)

- **Swallowed errors** — catch blocks that silently eat errors without logging or re-throwing
- **Silent fallbacks** — returning defaults for unexpected states instead of failing fast
- **Missing error context** — throw/log without IDs, descriptions, or structured data
- **God modules** — files mixing unrelated concerns (>300 lines doing multiple jobs)

### Tier 2 — High (fix next)

- **Wrong logger** — `console.log`/`console.error` in production code instead of Pino
- **Bad log event names** — events not following `{domain}.{action}_{state}` convention
- **Missing error classification** — git catch blocks without `classifyIsolationError()`
- **Generic `import *`** — from `@archon/core` instead of specific named imports

### Tier 3 — Medium (fix if time permits)

- **Unpaired log events** — `_started` without corresponding `_completed`/`_failed`
- **DRY violations** — same pattern in 3+ places without extraction
- **Nested ternaries** — should be if/else or switch
- **Clever code** — meta-programming or hidden dynamic behavior that obscures intent
- **YAGNI violations** — speculative code with no current caller

### Tier 4 — Low (note for backlog)

- **Missing `import type`** — type-only imports without `type` keyword (often auto-fixable)
- **Inconsistent naming** — doesn't follow project conventions
- **Comment quality** — obvious comments, outdated descriptions

## What NOT to Check

These are already enforced by tooling — don't waste time on them:
- ESLint rules (return types, unused vars, etc.) — `bun run lint` catches these
- TypeScript strict mode violations — `bun run type-check` catches these
- Formatting (quotes, commas, indentation) — Prettier handles this
