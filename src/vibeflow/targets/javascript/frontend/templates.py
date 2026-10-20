from __future__ import annotations

from vibeflow.targets.javascript.resources import read_text


def _runtime_source() -> str:
    names = ("runtime_helpers.mjs", "capability_helpers.mjs", "plugin_helpers.mjs",
             "root_helpers.mjs", "status_helpers.mjs", "execution_helpers.mjs")
    return "\n".join(read_text(name) for name in names)



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
