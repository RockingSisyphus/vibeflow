# VibeFlow Documentation Index

This directory contains current user documentation, maintainer documentation, and historical design records. The release package also carries topic-specific user docs and a separate AI instruction file; these artifacts have different responsibilities and must stay semantically aligned. Start with the current docs unless you are researching why a design changed.

## Start Here

- `../README.md`: project overview and release-package workflow.
- `developer_guide.md`: how to build business nodes, base_lib helpers, plugins, nodesets, and JSONC configs.
- Config node/resource visual metadata (`display_name`, `description`, `style`, `similar_to` where applicable), symbol-table nodeset parsing and forward references, explicit-edge mainline analysis / data bypass / async edge semantics, first-class loop nodes, safe OR join / `join_policy`, SVG color rules and native-text label enhancement, actionable and aggregated health/quality `details`, config parse tracing, and nested runtime trace fields are documented in `developer_guide.md` and `kernel_development_guide.md`.
- `kernel_target_vision.md`: target vision and current public architecture principles.
- `kernel_development_guide.md`: checks and workflow for maintaining VibeFlow itself.

## Documentation Responsibilities

- `kernel_target_vision.md` records long-lived product invariants and architecture-review principles. It should describe what must remain true, not implementation history.
- `kernel_development_guide.md` is the maintainer contract for VibeFlow itself, including CLI orchestration, failure semantics, regression coverage, and repository checks.
- `developer_guide.md` is the shared user guide. It is also the source copied into the release package as `kernel/docs/10_Kernel能力与项目开发指南.md`; edit the source once rather than patching generated output.
- `../distribution/kernel_development_pack/docs/` contains topic-specific source documents for release-package users. The build places them under `kernel/docs/`.
- `../distribution/kernel_development_pack/project_template/AGENTS.md` is the additional high-salience instruction set for AI agents. It carries operational prohibitions and review gates, while the human README should stay concise.
- `../README.md` and `../README.en.md` provide the repository overview and a short two-path quick start for greenfield and existing projects.

All current user- and AI-facing layers must agree that existing workflows are edited in place, formal review uses the VibeFlow `review` command and fails closed, Mermaid CLI/mmdc is an internal implementation detail, and human approval requires an explicit later message when requested. They must also use the public name “CLI 让渡模式 / `delegate-cli`”, keep `run` and `review` responsibilities unchanged, and describe the same derived effect-scope matrix (`none`, `terminal`, `python_io`, `trusted`) without reverting to the obsolete claim that `flow_kind` never authorizes IO or that `external=True` is not a purity bypass.

## Current Design

- `kernel_target_vision.md`: target vision and core architecture principles.
- `developer_guide.md`: current user-facing node/config/nodeset/plugin/base_lib guide.
- `kernel_development_guide.md`: current maintainer workflow.

## Maintainers

- `kernel_development_guide.md`: checks and workflow for maintaining VibeFlow itself.

## Research References

- `14_AI辅助软件开发架构护栏参考论文.md`: 2024–2026 literature on coding-agent maintainability, architecture erosion, executable specifications, software-architecture benchmarks, and structural guardrails relevant to VibeFlow.

## Design Records And Historical Notes

- `strict_flowchart_kernel_redesign.md`: design record for the strict flowchart redesign.
- `11_训练性能导向内核改进计划.md`: historical/completed runtime-performance roadmap. Some Context wording predates the current inbox result model and should not be treated as public config API.
- `12_CompiledBlock完整代码生成计划.md`: historical compiled-block implementation plan.
- `13_CompiledBlock分阶段实施计划.md`: historical staged compiled-block plan.
