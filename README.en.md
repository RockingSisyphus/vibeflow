# VibeFlow

[中文](README.md)

VibeFlow structures AI-assisted programs as explicit workflows that can be executed, checked, and rendered as architecture views. Business logic lives in small Nodes, Config declares control flow, port contracts declare data flow, and Core validates the structure before execution or build.

```text
terminal start → input I/O → process / nodeset → output I/O → terminal end
```

![VibeFlow comprehensive flowchart](docs/assets/comprehensive_flowchart.svg)

## Main capabilities

- Python Runtime, relocatable Python AOT packages, and JavaScript/TypeScript AOT;
- Python and JS/TS plugin SDKs for code-defined Nodes, Rules, Rulesets, and other resources explicitly selected by each workflow;
- composable Rules and Rulesets, plus Nodes, Nodesets, Loops, Capabilities, and explicit effect boundaries;
- explicit multi-file implementations, source ownership, per-file reviews, and default presentation for Nodes, BaseLibs, Plugins, and Hosts;
- deterministic Architecture JSONC and offline HTML previews with history, expandable calls and resource views; optional Mermaid, ASCII and SVG exports;
- config, contract, reachability, control-flow, quality, build, and execution-evidence checks;
- collaborative and autonomous development protocols over the same Core and machine rules.

VibeFlow reviews engineering structure, source health, and selected domain constraints. Project tests and production-environment acceptance verify business results and external behavior.

## Getting started

Download and extract one release package:

- `vibeflow-distribution-<version>.zip` for human-reviewed collaboration;
- `vibeflow-distribution-autonomous-<version>.zip` for unattended development.

The root `AGENTS.md` routes AI agents to task-specific documentation. Human readers can start at `kernel/docs/README.md`. Both packages include minimal `python_project/` and `javascript_project/` roots.

Python smoke run:

```bash
python run.py validate --config python_project/configs/main.jsonc
python run.py run --config python_project/configs/main.jsonc --input python_project/probe_input.json
```

JavaScript smoke run:

```bash
npm ci --prefix javascript_project
python run.py build --config javascript_project/configs/main.jsonc --target node --profile esm-module --out-dir javascript_project/build/node
node javascript_project/scripts/workflow_execution_probe.mjs
```

## Documentation

- [Project overview](distribution/docs/overview.md)
- [User development guides](docs/README.md#使用者开发)
- [Offline previews and history](distribution/docs/user/local-preview.md)
- [Multi-file resources and presentation](distribution/docs/user/multifile-resources.md)
- [System design](docs/README.md#系统设计)
- [Kernel maintenance](docs/README.md#内核维护)

Run the complete source-repository gate with:

```bash
python tools/verify_project.py --full
```

Current distribution version: `1.4.1`. Workflow ABI: `vibeflow.workflow.v11`. AOT manifest: `vibeflow.aot-build.v5`. Workflow launch manifest: v2. Plugin ABI: `vibeflow.plugin.v4`.
Python supports native asynchronous nodes. Python and JavaScript support official synchronous workflow calls and asynchronous in-process collaboration; Node and browsers share the same generic JS coordinator. Migrate older launch configurations and rebuild older AOT artifacts. Preview snapshots remain v4. Planned calls remain visible for review and are excluded from service launch declarations. See the [distribution build instructions](docs/maintainers/release.md).
Both profiles include the offline HTML viewer, workflow history, and project/root navigation. Named entries and independent workflow coordination are supported. Project/root governance checks shared-resource boundaries; Python AOT carries declared support files of permitted cross-root dependencies. Rebuild older AOT artifacts for the current ABI. See the [coordination guide](distribution/docs/user/workflow-coordination.md), [project governance](distribution/docs/user/project-governance.md), and [distribution build instructions](docs/maintainers/release.md).
