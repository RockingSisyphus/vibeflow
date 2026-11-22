import type {Options, Resource} from "./sdk";
import type {WorkflowNodeContext} from "./workflow_contracts";

export interface NodeRunContext {
  readonly workflow: WorkflowNodeContext["workflow"];
  readonly signal?: AbortSignal;
  trace(kind: string, details?: Readonly<Record<string, unknown>>): void;
  updateInfo(info: readonly Readonly<Record<string, unknown>>[]): void;
}
export type WorkflowOperation =
  | {readonly operation: "call"; readonly wait?: boolean}
  | {readonly operation: "invoke_sync" | "wait" | "send" | "receive" | "kill"};
export interface NodeOptions<Context = NodeRunContext> extends Options {id: string; node_type: string; contract: Readonly<Record<string, unknown>>; workflow_operations?: readonly WorkflowOperation[]; run?: (inputs: any, params: any, context: Context) => any}

export function defineNode<T extends NodeOptions>(options: T): Resource & Readonly<Pick<T, "run">>;
// Named implementations keep their specialized context for the AOT contract check.
export function defineNode<T extends NodeOptions<any>>(options: T): Resource & Readonly<Pick<T, "run">>;
