# VibeFlow

[中文](README.md)

> Keep AI-built projects from turning into an unmaintainable pile of mud.

VibeFlow forces AI to plan the program's rough architecture before development, and automatically generates a directly readable standard program flowchart from the program's **real code logic** so developers can understand the real structural logic of each part instead of guessing from AI descriptions that may be distorted. VibeFlow forces AI to follow high cohesion, low coupling, small files, small functions, explicit flow edges, and checkable contracts. AI can still move fast, but every edit must return to a visual, verifiable, runnable flowchart.

## Why VibeFlow 🧯

LLMs are great at writing code quickly. Across many rounds of edits, they are also great at quietly creating these problems:

- One function keeps growing until nobody wants to touch it.
- New features bypass existing structure and add hidden dependencies.
- Bug fixes become local patches while the root cause stays alive.
- The project architecture gradually becomes bloated and chaotic until AI itself can no longer understand it.

Eventually the code may still run, but the structure is no longer reviewable, new features are hard to add, and bugs become hard to fix.

VibeFlow moves these risks earlier. Before AI writes code, the project already carries executable rules for structure, contracts, flow, and artifacts.

## In One Sentence 🧭

VibeFlow constrains a project into a runnable, checkable, visual standard flowchart.

```text
terminal start -> io input -> process -> decision -> process -> io output -> terminal end
```

AI still writes business code, but it must work through the flowchart: each node stays small, control flow comes only from config, and every run starts with health checks.

## Showcase ✨

This SVG was exported from a complete integration sandbox example. Throughout AI development, developers can inspect the latest flowchart generated under `reports/` at any time to understand the project's current logical structure and keep track of the whole project state with minimal effort.

![VibeFlow comprehensive flowchart](docs/assets/comprehensive_flowchart.svg)

## Who It Is For 👥

- Developers using OpenCode, Codex, Claude Code, or other vibe coding tools for long-running projects.
- Teams that want AI assistance without losing project structure.
- Projects where business flow should be reviewable as Mermaid, ASCII, or SVG diagrams.
- Workflows that need automatic structure, contract, and quality checks before execution.

## Usage 🚀

VibeFlow is designed for release-package usage.

1. Download the latest package from GitHub Releases.
2. Extract it into your workspace.
3. Open or create a project in that directory with any vibe coding tool, such as OpenCode, Codex, or Claude Code.
4. Let AI follow `AGENTS.md`: design a planned flowchart first, review the structure, then implement business nodes, base_lib helpers, plugins, and JSONC configs step by step.

The release package root includes `AGENTS.md`. AI tools that support project instructions can read it automatically and learn:

- Which directories are editable.
- Which kernel files should not be modified.
- How to add nodes, nodesets, and plugins.
- How to run validate, run, quality, and diagram commands.
- Which health checks must pass before execution.
- How to design planned nodesets first, export diagrams for human review, and only then implement them.

You do not need to understand the full kernel source first. Treat the release package as an AI development workspace with built-in rules.

## Typical Release Package Layout 📦

```text
project/
  nodes/          # business nodes
  base_lib/       # pure helper functions
  plugins/        # optional policy/runtime plugins
  configs/        # JSONC flow configs
  registry.py     # node registration
kernel/
  vibeflow/       # VibeFlow kernel copy, usually not edited
AGENTS.md         # project rules for AI tools
run.py            # project entrypoint
```

Common commands:

```bash
python run.py validate --config project/configs/main.jsonc
python run.py run --config project/configs/main.jsonc --run-root runs
python run.py mermaid --config project/configs/main.jsonc --output reports/graph.mmd
python run.py ascii --config project/configs/main.jsonc --output reports/graph.txt
python run.py svg --config project/configs/main.jsonc --output reports/graph.svg
python run.py svg --config project/configs/main.jsonc --expand-nodesets --output reports/graph.expanded.svg
python run.py quality --path project
```

SVG export passes an expanded Mermaid CLI render config. Normal graphs default to `maxTextSize=200000`; `--expand-nodesets` defaults to `maxTextSize=500000`. Very large graphs can override this with `--mermaid-max-text-size` and `--mermaid-max-edges`.
Expanded SVG exports always use the deterministic `review-columns` composer: the main pipeline stays on the left, followed by plugins, base_lib, and expanded nodesets in top-level call order. Nodeset details use a recursive detail-panel layout: leaf nodesets render horizontally; parents with child nodesets keep collapsed call-sites and original edges, with direct child nodesets stacked to the right in call order.
`graph.expanded.mmd` is a Mermaid source debug artifact only. Do not render it directly with Mermaid CLI/mmdc for review SVG; detailed review SVG must be generated through `run.py svg --expand-nodesets`.
SVG rendering does not require Google Chrome to be preinstalled. After a normal `npm install`, VibeFlow first uses Puppeteer's installed/cached browser. `/snap/bin/chromium` is skipped because it commonly fails under Puppeteer/mermaid-cli with profile-lock launch errors.

## AI Development Workflow 🛠️

```text
Describe requirement
  -> AI abstracts it into a coarse standard flowchart
  -> Write planned nodesets into JSONC
  -> Export Mermaid or SVG for human review
  -> Expand nodesets after review
  -> Implement node/base_lib/plugin/config
  -> validate / quality / run
  -> Iterate
```

Major architecture changes use the same loop: planned first, diagram first, review first, implementation second. Anything still undecided stays as `status: "planned"`; VibeFlow allows it for design review but will not let it pretend to be runnable.

VibeFlow does not stop you from vibe coding. It makes every vibe return to a checkable structure.

## How It Works ⚙️

VibeFlow is a strict flowchart runtime. Nodes handle local pure computation, JSONC config declares control flow, the compiler builds an executable graph, and the health checker blocks structural drift and contract errors before runtime.

It turns project architecture from a verbal convention into executable checks.

## Core Features 🧩

### Standard Flowchart Constraints

Every node declares a standard `flow_kind`:

- `terminal`: start / end.
- `process`: normal processing.
- `decision`: branch / route.
- `io`: input / output action.
- `predefined`: predefined process / nodeset.
- `data_store`: data store request or reference.
- `document`: document generation or document structure.
- `preparation`: setup / initialization.

This means AI-written code must not only run; it must fit back into a reviewable flowchart.

### Explicit Flow Edges

Program control flow comes only from `pipeline.edges` in JSONC config.

`requires` / `provides` are data contracts, not hidden control-flow inference. This keeps multi-round AI edits from creating implicit paths and invisible dependencies.

Data contracts use strict structured fields: `provides` declares a unique `key` and logical `type`, while `requires` consumes by `type` plus `cardinality`. Runtime passes envelopes through node inboxes and edge payloads; nodes cannot read early upstream outputs through a multi-hop global Context, and final results keep only `pipeline.outputs`.

### Small Nodes And Pure Logic

Business nodes are pure by default:

- No file reads or writes.
- No network access.
- No database access.
- No browser or external process launches.
- No environment variable reads.
- No direct calls to other nodes.

Real IO is modeled through flowchart nodes such as `io`, `data_store`, and `document`. Third-party or externally maintained code is marked with `NodeInfo.external=True`.

### Pre-Run Health Checks

Before execution, VibeFlow checks:

- Node metadata completeness.
- Input and output contracts.
- Reachability from start to end.
- Whether cycles pass through a decision node.
- Node purity and structure rules.
- Whether config, plugins, or nodesets break project boundaries.

If checks fail, the run is refused with traceable reasons.

### Visual Artifacts

The same config can export:

- Mermaid flowcharts.
- ASCII terminal flowcharts.
- SVG diagrams.

Humans can review the system shape, and AI tools get a clearer project map.

## Repository Docs 📚

- `docs/kernel_target_vision.md`: vision.
- `docs/developer_guide.md`: user development guide.
- `docs/kernel_development_guide.md`: VibeFlow maintenance guide.
- `docs/strict_flowchart_kernel_redesign.md`, `docs/11_*.md`, `docs/12_*.md`, `docs/13_*.md`: historical design records and staged plans, not the current public API.
- `distribution/kernel_development_pack/`: release package template.

## License 📄

VibeFlow is licensed under the GNU Affero General Public License v3.0 (AGPLv3). See `LICENSE`.

## Status 🚧

VibeFlow is evolving quickly. The current focus is stabilizing structure discipline, flowchart representation, pre-run checks, and the release-package experience for AI-assisted development.

If more software will be maintained by humans and AI together, projects need more than stronger generation. They need harder structural boundaries.

VibeFlow is that boundary.
