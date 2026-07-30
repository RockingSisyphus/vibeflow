from __future__ import annotations

import pytest

from vibeflow.runtime.errors import PipelineRuntimeError
from vibeflow.runtime.helpers import condition_matches


@pytest.mark.parametrize(
    ("expression", "value", "expected"),
    [
        ("route == true", True, True),
        ("route == true", 1, False),
        ("route != true", 1, True),
        ('route == "1"', "1", True),
        ('route == "1"', 1, False),
    ],
)
def test_conditions_use_portable_json_literal_equality(
    expression: str,
    value: object,
    expected: bool,
) -> None:
    assert condition_matches(expression, {"route": value}) is expected


def test_conditions_still_reject_unsupported_expressions() -> None:
    with pytest.raises(PipelineRuntimeError, match="unsupported edge condition"):
        condition_matches("route > true", {"route": True})
