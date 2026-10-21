export const VIBEFLOW_RULE_ABI: "vibeflow.rule.v3";
export type JsonValue = null | boolean | number | string | readonly JsonValue[] | { readonly [key: string]: JsonValue };
export interface RuleRecord { readonly type_id: string; readonly value: JsonValue; }
export interface Finding {
  readonly code?: string; readonly rule_id?: string; readonly definition_id?: string; readonly severity: "error" | "warning" | "info";
  readonly subject_type?: string; readonly subject_id?: string;
  readonly message: string;
  readonly source_location?: Readonly<{path?: string; line?: number; column?: number}>;
  readonly details?: Readonly<Record<string, JsonValue>>;
}
export interface SourceNode {
  readonly kind: string; readonly name: string; readonly text: string; readonly path: string;
  readonly line: number; readonly column: number; readonly end_line: number; readonly end_column: number;
  readonly qualname?: string; readonly children?: readonly SourceNode[];
}
export interface SourceAnalysis {
  text(path: string): string;
  ast(path: string): SourceNode;
  symbols(path: string): readonly SourceNode[];
  imports(path: string): readonly Readonly<{specifier: string; resolved_path: string | null; path: string; line: number; column: number; type_only: boolean}>[];
  reachable(path: string): readonly string[];
  ownership(path: string): Readonly<{path: string; declared: readonly JsonValue[]; node_definitions: readonly string[]}>;
  nodes(path: string, kind: string): readonly SourceNode[];
}
export interface RuleContext {
  readonly abiVersion: "vibeflow.rule.v3"; readonly ruleId: string;
  readonly phase: "static" | "run" | "import"; readonly target: string;
  /** Workflow graph facts contain finite Nodeset declarations; nested graph.nodeset_refs refer to graph.nodeset_types. compiled exists only after native compilation. */
  readonly facts: Readonly<Record<string, JsonValue>>;
  readonly subject: Readonly<Record<string, JsonValue>>;
  readonly scope: Readonly<Record<string, JsonValue>>;
  readonly sources: SourceAnalysis;
  readonly signal: AbortSignal;
}
export interface RuleResult {
  readonly records?: Readonly<Record<string, RuleRecord>>;
  readonly findings?: readonly Finding[];
  readonly state?: "completed" | "failed" | "unavailable";
}
export type CheckRule = (context: Readonly<RuleContext>, inputs: Readonly<Record<string, RuleRecord>>, params: Readonly<Record<string, JsonValue>>) => RuleResult | Promise<RuleResult>;
export declare const check: CheckRule;
