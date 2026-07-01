# Security Policy

VibeFlow is early-stage software. Please do not publicly disclose vulnerabilities with working exploit details before the maintainer has had time to respond.

## Reporting

Use GitHub private vulnerability reporting if it is available for this repository. If it is not available, open a minimal issue asking for a private contact channel and do not include exploit details in the issue body.

Please include:

- Affected version or commit.
- Impacted command, API, or release-package workflow.
- Minimal reproduction steps.
- Whether the issue affects generated project code, the VibeFlow kernel, or the GitHub release package.

## Scope

Security-sensitive areas include:

- Purity and side-effect checks that are supposed to block file, network, database, process, browser, or environment access.
- Plugin loading and policy relaxation behavior.
- Release-package templates and `AGENTS.md` workflows.
- JSONC config parsing, schema validation, and runtime execution.
