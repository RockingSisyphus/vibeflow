export type {NodeRunContext, NodeOptions} from "./node_contracts";
export {defineNode} from "./node_contracts";
/** Plugin ABI v3 declarations. Resource objects are fixed, not factories. */
export type Json = null | boolean | number | string | Json[] | {[key: string]: Json};
export interface Source {kind: "file" | "module" | "package"; ref: string; export?: string}
export interface Resource {readonly descriptor: Readonly<Record<string, unknown>>}
import type {RuleContext, RuleResult, RuleRecord, CheckRule} from "./rule_abi";
export type {RuleContext, RuleResult, RuleRecord, Finding, SourceNode, SourceAnalysis} from "./rule_abi";
export interface RuleCall {readonly id: string; readonly rule_id?: string; readonly ruleset_id?: string; readonly params?: Readonly<Record<string, Json>>}
export interface RuleRelation {readonly source: string; readonly target: string; readonly kind: "includes" | "requires" | "overrides"; readonly bindings?: Readonly<Record<string, string>>; readonly params?: Readonly<Record<string, Json>>; readonly replace_rule?: string}
export interface Presentation {readonly fill?: string; readonly stroke?: string; readonly text?: string; readonly shape?: string; readonly icon?: string}
export interface Options {id?: string; source?: Source; implementations?: readonly unknown[]; implementation_files?: readonly (string | Source)[]; presentation?: Presentation; base_libs?: readonly string[]; rulesets?: readonly (string | {rule_id: string; params?: Readonly<Record<string, Json>>})[]; [key: string]: unknown}
export interface RuleOptions extends Options {id: string; level?: "node" | "graph" | "root" | "project"; scope?: "call" | "source"; check?: CheckRule}
export interface BaseLibOptions extends Options {id: string; implementation?: (...args: any[]) => any}
export function defineRule<T extends RuleOptions>(options: T): Resource & Readonly<Pick<T, "check">>;
export function defineRuleset(options: Options & {id: string; workflow_default?: boolean; graph_scope?: "current_graph" | "effective_subtree"; calls?: readonly RuleCall[]; relations?: readonly RuleRelation[]; entrypoints?: Readonly<Record<string, readonly string[]>>}): Resource;
export function defineDataSchema(options: Options): Resource;
export function defineBaseLib<T extends BaseLibOptions>(options: T): Resource & Readonly<Pick<T, "implementation">>;
export function defineCapability(options: Options): Resource;
export function defineNodeType(options: Options & {id: string; display_name?: string; description?: string}): Resource;
export function defineResource(options: Options & {kind: string}): Resource;
export interface PluginOptions extends Options {id: string; resources: readonly Resource[]; config_schema?: Readonly<Record<string, Json>>; config_defaults?: Readonly<Record<string, Json>>; compiler?: Source | ((context: any) => any); runtime?: Source | ((context: any) => any); targets?: readonly ("node" | "browser")[]; declaration_rulesets?: readonly (string | {rule_id: string; params?: Readonly<Record<string, Json>>})[]; priority?: number; display_name?: string; description?: string; version?: string}
export function definePlugin<T extends PluginOptions>(options: T): Readonly<T & {abi: "vibeflow.plugin.v4"}>;
