"""Language-neutral contract used by the delegated CLI application mode."""

from __future__ import annotations

from dataclasses import replace
from typing import Mapping

from vibeflow.core.findings import HealthFinding, HealthReport


CLI_ARGV_TYPE = "cli.argv"
CLI_EXIT_CODE_TYPE = "cli.exit_code"


def validate_delegate_cli_graph_contract(
    graph: object,
    report: HealthReport,
) -> HealthReport:
    findings: list[HealthFinding] = []
    argv_inputs = [
        item
        for item in graph.inputs
        if item.key == CLI_ARGV_TYPE or item.type == CLI_ARGV_TYPE
    ]
    if (
        len(argv_inputs) != 1
        or argv_inputs[0].key != CLI_ARGV_TYPE
        or argv_inputs[0].type != CLI_ARGV_TYPE
    ):
        findings.append(
            _contract_finding(
                "CLI.DELEGATE.ARGV_INPUT",
                "delegate-cli requires exactly one pipeline input with "
                "key and type 'cli.argv'",
                details={
                    "matches": len(argv_inputs),
                    "inputs": [
                        {"key": item.key, "type": item.type}
                        for item in argv_inputs
                    ],
                },
            )
        )

    exit_outputs = [
        item for item in graph.outputs if item.type == CLI_EXIT_CODE_TYPE
    ]
    if (
        len(exit_outputs) != 1
        or exit_outputs[0].cardinality != "exactly_one"
    ):
        findings.append(
            _contract_finding(
                "CLI.DELEGATE.EXIT_OUTPUT",
                "delegate-cli requires exactly one pipeline output of "
                "type 'cli.exit_code' with cardinality 'exactly_one'",
                details={
                    "matches": len(exit_outputs),
                    "cardinalities": [
                        item.cardinality for item in exit_outputs
                    ],
                },
            )
        )

    exit_providers = [
        (node.id, provider.key, provider.type, node.async_mode)
        for node in graph.nodes
        for provider in node.provides
        if (
            provider.key == CLI_EXIT_CODE_TYPE
            or provider.type == CLI_EXIT_CODE_TYPE
        )
    ]
    if (
        len(exit_providers) != 1
        or exit_providers[0][1] != CLI_EXIT_CODE_TYPE
        or exit_providers[0][2] != CLI_EXIT_CODE_TYPE
        or exit_providers[0][3] == "detached"
    ):
        findings.append(
            _contract_finding(
                "CLI.DELEGATE.EXIT_PROVIDER",
                "delegate-cli requires exactly one provider whose key and "
                "type are both 'cli.exit_code'",
                details={
                    "matches": len(exit_providers),
                    "providers": [
                        {
                            "node": node_id,
                            "key": key,
                            "type": data_type,
                            "async": async_mode,
                        }
                        for (
                            node_id,
                            key,
                            data_type,
                            async_mode,
                        ) in exit_providers
                    ],
                },
            )
        )

    if not findings:
        return report
    status = "ERROR" if report.status == "ERROR" else "FAIL"
    return replace(
        report,
        status=status,
        errors=(*report.errors, *findings),
    )


def extract_delegate_cli_exit_code(
    context: object,
) -> tuple[int | None, str | None]:
    if context is None or not hasattr(context, "get"):
        return None, "delegate CLI result does not expose cli.exit_code"
    try:
        payload = context.get(CLI_EXIT_CODE_TYPE)
    except (KeyError, TypeError, ValueError):
        return None, "delegate CLI result is missing cli.exit_code"
    if not isinstance(payload, Mapping):
        return (
            None,
            "delegate CLI result cli.exit_code must be a DataEnvelope payload",
        )
    if (
        payload.get("key") != CLI_EXIT_CODE_TYPE
        or payload.get("type") != CLI_EXIT_CODE_TYPE
    ):
        return (
            None,
            "delegate CLI exit provider must use key and type cli.exit_code",
        )
    value = payload.get("value")
    if type(value) is not int or not 0 <= value <= 255:
        return (
            None,
            "delegate CLI exit value must be an integer from 0 to 255",
        )
    return value, None


def _contract_finding(
    rule_id: str,
    message: str,
    *,
    details: Mapping[str, object],
) -> HealthFinding:
    return HealthFinding(
        rule_id=rule_id,
        severity="error",
        object_type="pipeline",
        object_id="pipeline",
        failure_layer="contract",
        message=message,
        suggested_fix_type="fix_config",
        details=dict(details),
    )


__all__ = [
    "CLI_ARGV_TYPE",
    "CLI_EXIT_CODE_TYPE",
    "extract_delegate_cli_exit_code",
    "validate_delegate_cli_graph_contract",
]
