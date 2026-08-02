from __future__ import annotations

from importlib.resources import files


def _runtime_source() -> str:
    resource = files("vibeflow.targets.javascript.resources").joinpath(
        "runtime_helpers.mjs"
    )
    return resource.read_text(encoding="utf-8").strip()


RUNTIME_SOURCE = _runtime_source()


ABORT_SIGNAL_DECLARATION = """\
export interface VibeFlowAbortSignal {
  readonly aborted: boolean;
  readonly reason: unknown;
  readonly onabort: ((event: any) => unknown) | null;
  throwIfAborted(): void;
  addEventListener(type: string, listener: any, options?: any): void;
  removeEventListener(type: string, listener: any, options?: any): void;
  dispatchEvent(event: any): boolean;
}
"""


DECLARATION_PREAMBLE = (
    """\
export type WorkflowTraceMode = "off" | "boundary" | "full";

"""
    + ABORT_SIGNAL_DECLARATION
    + """
export interface WorkflowTraceEvent {
  readonly kind: string;
  readonly workflowId: string;
  readonly nodeId?: string;
  readonly nodePath?: string;
  readonly path?: readonly string[];
  readonly [key: string]: unknown;
}

export class VibeFlowWorkflowError extends Error {
  readonly code: string;
  readonly workflowId: string;
  readonly nodePath: string;
  readonly blockPath: string;
}
"""
)


__all__ = [
    "ABORT_SIGNAL_DECLARATION",
    "DECLARATION_PREAMBLE",
    "RUNTIME_SOURCE",
]
