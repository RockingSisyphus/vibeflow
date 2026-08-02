from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import tempfile

from vibeflow.tooling.application.javascript.build import ProjectBuildResult

from sandbox_support import PROJECT_ROOT


def _typecheck_consumer(
    result: ProjectBuildResult,
    source: str,
) -> str:
    declarations = next(result.out_dir.glob("*.d.ts"), None)
    if declarations is None:
        raise AssertionError("build did not produce a declaration file")
    with tempfile.TemporaryDirectory(prefix="vibeflow-ts-consumer-") as raw:
        root = Path(raw)
        shutil.copy2(result.entry, root / result.entry.name)
        shutil.copy2(declarations, root / declarations.name)
        consumer = root / "consumer.mts"
        consumer.write_text(source.lstrip(), encoding="utf-8")
        compiler = PROJECT_ROOT / "node_modules/typescript/bin/tsc"
        completed = subprocess.run(
            [
                "node",
                str(compiler),
                "--noEmit",
                "--strict",
                "--target",
                "ES2022",
                "--module",
                "NodeNext",
                "--moduleResolution",
                "NodeNext",
                "--lib",
                "ES2022,DOM",
                str(consumer),
            ],
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=30,
        )
        if completed.returncode != 0:
            raise AssertionError(
                "generated declarations failed consumer typecheck: "
                f"{completed.stdout.strip() or completed.stderr.strip()}"
            )
    return declarations.name


def typecheck_declarations(result: ProjectBuildResult) -> dict[str, str]:
    declarations = _typecheck_consumer(
        result,
        f"""
import {{
  runWorkflow,
  type WorkflowInputs,
  type WorkflowOutputs,
}} from "./{result.entry.name}";

const inputs: WorkflowInputs = {{ x: 10, a: 8, b: 3 }};
const result = runWorkflow(inputs, {{
  trace: "full",
}});
const checkedResult: WorkflowOutputs = result;

// @ts-expect-error required input b is missing
void runWorkflow({{ x: 1, a: 2 }});
// @ts-expect-error x must be numeric
void runWorkflow({{ x: "wrong", a: 2, b: 1 }});

const answer: number = result.result;
// @ts-expect-error the result is numeric, not an untyped value
const wrongType: string = result.result;
// @ts-expect-error the public output has no envelope or unknown field
const missing: string = result.unknownField;
void answer;
void wrongType;
void missing;
void checkedResult;
""",
    )
    return {
        "declarations": declarations,
        "typescript": "strict consumer passed",
    }


def typecheck_optional_declarations(
    result: ProjectBuildResult,
) -> dict[str, str]:
    declarations = _typecheck_consumer(
        result,
        f"""
import {{
  runWorkflow,
  type WorkflowInputs,
  type WorkflowOutputs,
}} from "./{result.entry.name}";

const omitted: WorkflowInputs = {{ x: 10 }};
const supplied: WorkflowInputs = {{ x: 10, offset: 7 }};
const result = runWorkflow(omitted);
const checkedResult: WorkflowOutputs = result;
void runWorkflow(supplied);

// @ts-expect-error x remains required
void runWorkflow({{ offset: 1 }});
// @ts-expect-error optional offset remains numeric when present
void runWorkflow({{ x: 1, offset: "wrong" }});

const answer: number = result.result;
// @ts-expect-error the numeric result must not degrade to any
const wrongType: string = result.result;
void answer;
void wrongType;
void checkedResult;
""",
    )
    return {
        "declarations": declarations,
        "typescript": "optional input consumer passed",
    }


def typecheck_capability_declarations(
    result: ProjectBuildResult,
) -> dict[str, str]:
    declarations = _typecheck_consumer(
        result,
        f"""
import {{
  runWorkflowAsync,
  type WorkflowCapabilities,
}} from "./{result.entry.name}";

const capabilities: WorkflowCapabilities = {{
  "sandbox.storage": {{
    read: async (input, context) => {{
      const key: string = input.key;
      const signal: AbortSignal | undefined = context.signal;
      return {{ value: `typed:${{key}}` }};
    }},
  }},
}};
void runWorkflowAsync({{ x: 2, key: "alpha" }}, {{ capabilities }});

const missingOperation: WorkflowCapabilities = {{
  // @ts-expect-error the required read operation is missing
  "sandbox.storage": {{}},
}};
const wrongOutput: WorkflowCapabilities = {{
  "sandbox.storage": {{
    // @ts-expect-error read must return a string value
    read: async () => ({{ value: 42 }}),
  }},
}};
void missingOperation;
void wrongOutput;
""",
    )
    return {
        "declarations": declarations,
        "typescript": "Capability consumer passed",
    }


__all__ = [
    "typecheck_capability_declarations",
    "typecheck_declarations",
    "typecheck_optional_declarations",
]
