import type {Options, Resource} from "./sdk";

export interface NodeRunContext {
  readonly workflow: Readonly<{self(): {id: string}}>;
  readonly signal?: AbortSignal;
  readonly capabilities: Readonly<Record<string, any>>;
  trace(kind: string, details?: Readonly<Record<string, unknown>>): void;
  updateInfo(info: readonly Readonly<Record<string, unknown>>[]): void;
}
export interface NodeOptions<Context = NodeRunContext> extends Options {id: string; node_type: string; contract: Readonly<Record<string, unknown>>; run?: (inputs: any, params: any, context: Context) => any}

export function defineNode<T extends NodeOptions>(options: T): Resource & Readonly<Pick<T, "run">>;
// Named implementations keep their specialized context for the AOT contract check.
export function defineNode<T extends NodeOptions<any>>(options: T): Resource & Readonly<Pick<T, "run">>;
