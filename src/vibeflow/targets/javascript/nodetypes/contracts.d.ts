import type {Options, Resource} from "../resources/sdk";

export interface TaskRef { readonly run_id: string; readonly task_id: string; }
export interface TaskError {
  readonly code: string;
  readonly message: string;
  readonly node_path: string;
  readonly source_location?: {readonly path?: string; readonly symbol?: string; readonly line?: number};
  readonly exception_type?: string;
  readonly stack?: string;
  readonly cause?: TaskError;
  readonly errors?: readonly TaskError[];
  readonly task_errors?: readonly TaskOutcome[];
  readonly cleanup_errors?: readonly TaskError[];
}
export interface TaskOutcome {
  readonly task: TaskRef;
  readonly status: "succeeded" | "failed" | "cancelled";
  readonly outputs?: Readonly<Record<string, any>>;
  readonly error?: TaskError;
}
export interface StopAck {readonly task: TaskRef; readonly state: "stop_requested" | "already_exited";}
export interface TaskController {
  start(key: string, inputs?: Readonly<Record<string, any>>): TaskRef;
  waitAny(refs: readonly TaskRef[]): Promise<TaskOutcome | null>;
  requestStop(refs: readonly TaskRef[], reason?: any): readonly StopAck[];
  waitAllExited(refs: readonly TaskRef[]): Promise<readonly TaskOutcome[]>;
}
export interface TaskManagerContext extends NodeRunContext {readonly tasks: TaskController;}
export interface NodeRunContext {
  readonly signal?: AbortSignal;
  readonly capabilities: Readonly<Record<string, any>>;
  trace(kind: string, details?: Readonly<Record<string, unknown>>): void;
  updateInfo(info: readonly Readonly<Record<string, unknown>>[]): void;
}
export interface NodeOptions<Context = NodeRunContext> extends Options {type_key: string; contract: Readonly<Record<string, unknown>>; run?: (inputs: any, params: any, context: Context) => any}

export function defineNode<T extends NodeOptions>(options: T): Resource & Readonly<Pick<T, "run">>;
// Named implementations keep their specialized context for the AOT contract check.
export function defineNode<T extends NodeOptions<any>>(options: T): Resource & Readonly<Pick<T, "run">>;
