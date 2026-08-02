export const VIBEFLOW_PLUGIN_ABI: "vibeflow.plugin.v1";

export type PluginType = "policy" | "compiler" | "runtime";
export type PluginTarget = "node" | "browser";
export type PluginCompletion = "immediate" | "suspend";
export type JsonValue =
  | null
  | boolean
  | number
  | string
  | readonly JsonValue[]
  | { readonly [key: string]: JsonValue };

export interface PluginFactoryContext {
  readonly abiVersion: "vibeflow.plugin.v1";
  readonly pluginId: string;
  readonly pluginType: PluginType;
  readonly target: PluginTarget;
  readonly workflowId: string;
  readonly config: Readonly<Record<string, JsonValue>>;
  readonly signal: AbortSignal;
}

export interface PolicyPluginContext extends PluginFactoryContext {
  readonly pluginType: "policy";
}

export interface CompilerPluginContext extends PluginFactoryContext {
  readonly pluginType: "compiler";
}

export interface RuntimePluginContext extends PluginFactoryContext {
  readonly pluginType: "runtime";
}

export interface PolicyPlugin {
  extendPolicy?(payload: Readonly<Record<string, JsonValue>>): JsonValue | void;
  validateNode?(payload: Readonly<Record<string, JsonValue>>): JsonValue | void;
  validateGraph?(payload: Readonly<Record<string, JsonValue>>): JsonValue | void;
  validateNodeset?(payload: Readonly<Record<string, JsonValue>>): JsonValue | void;
}

export interface CompilerPlugin {
  beforeCompile?(payload: Readonly<Record<string, JsonValue>>): JsonValue | void;
  afterCompile?(payload: Readonly<Record<string, JsonValue>>): JsonValue | void;
  validateCompiledGraph?(payload: Readonly<Record<string, JsonValue>>): JsonValue | void;
}

export interface RuntimeHookSummary {
  readonly workflowId: string;
  readonly entryMode: "sync" | "async";
  readonly [key: string]: JsonValue;
}

export interface RuntimePlugin {
  beforeRun?(summary: RuntimeHookSummary): void | Promise<void>;
  afterRun?(summary: RuntimeHookSummary): void | Promise<void>;
  runFailed?(summary: RuntimeHookSummary): void | Promise<void>;
  beforeNode?(summary: RuntimeHookSummary): void | Promise<void>;
  afterNode?(summary: RuntimeHookSummary): void | Promise<void>;
  beforeNodeset?(summary: RuntimeHookSummary): void | Promise<void>;
  afterNodeset?(summary: RuntimeHookSummary): void | Promise<void>;
  nodesetFailed?(summary: RuntimeHookSummary): void | Promise<void>;
  beforeBlock?(summary: RuntimeHookSummary): void | Promise<void>;
  afterBlock?(summary: RuntimeHookSummary): void | Promise<void>;
  blockFailed?(summary: RuntimeHookSummary): void | Promise<void>;
  dispose?(): void | Promise<void>;
}

export type PluginInstance = PolicyPlugin | CompilerPlugin | RuntimePlugin;

export type CreatePlugin = (
  context: Readonly<PluginFactoryContext>,
) => PluginInstance;

/** Narrow factory alias for projects that publish only runtime plugins. */
export type CreateRuntimePlugin = (
  context: Readonly<PluginFactoryContext>,
) => RuntimePlugin;

export declare const createPlugin: CreatePlugin;
