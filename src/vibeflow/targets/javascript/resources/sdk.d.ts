/** Plugin ABI v3 declarations. Resource objects are fixed, not factories. */
export type Json = null | boolean | number | string | Json[] | {[key: string]: Json};
export interface Source {kind: "file" | "module" | "package"; ref: string; export?: string}
export interface Resource {readonly descriptor: Readonly<Record<string, unknown>>}
import type {RuleContext, RuleResult, RuleRecord, CheckRule} from "./rule_abi";
export type {RuleContext, RuleResult, RuleRecord, Finding, SourceNode, SourceAnalysis} from "./rule_abi";
export interface RuleCall {readonly id: string; readonly rule_id?: string; readonly ruleset_id?: string; readonly params?: Readonly<Record<string, Json>>}
export interface RuleRelation {readonly source: string; readonly target: string; readonly kind: "includes" | "requires" | "overrides"; readonly bindings?: Readonly<Record<string, string>>; readonly params?: Readonly<Record<string, Json>>; readonly replace_rule?: string}
export interface Presentation {readonly fill?: string; readonly stroke?: string; readonly text?: string; readonly shape?: string; readonly icon?: string}
export interface Options {id?: string; source?: Source; implementations?: readonly unknown[]; implementation_files?: readonly (string | Source)[]; presentation?: Presentation; base_libs?: readonly string[]; rulesets?: readonly string[]; [key: string]: unknown}
export interface NodeRunContext {
  readonly signal?: AbortSignal;
  readonly capabilities: Readonly<Record<string, any>>;
  trace(kind: string, details?: Readonly<Record<string, unknown>>): void;
  updateInfo(info: readonly Readonly<Record<string, unknown>>[]): void;
}
export interface NodeOptions<Context = NodeRunContext> extends Options {type_key: string; contract: Readonly<Record<string, unknown>>; run?: (inputs: any, params: any, context: Context) => any}
export interface RuleOptions extends Options {id: string; check?: CheckRule}
export interface BaseLibOptions extends Options {id: string; implementation?: (...args: any[]) => any}
export interface HostExtensionOptions extends Options {id: string; targets: readonly ("node" | "browser")[]; createHost?: (context: any) => any}
export function defineNode<T extends NodeOptions>(options: T): Resource & Readonly<Pick<T, "run">>;
// Named implementations keep their specialized context for the AOT contract check.
export function defineNode<T extends NodeOptions<any>>(options: T): Resource & Readonly<Pick<T, "run">>;
export function defineRule<T extends RuleOptions>(options: T): Resource & Readonly<Pick<T, "check">>;
export function defineRuleset(options: Options & {id: string; calls?: readonly RuleCall[]; relations?: readonly RuleRelation[]; entrypoints?: Readonly<Record<string, readonly string[]>>}): Resource;
export function defineDataSchema(options: Options): Resource;
export function defineBaseLib<T extends BaseLibOptions>(options: T): Resource & Readonly<Pick<T, "implementation">>;
export function defineCapability(options: Options): Resource;
export function defineHostExtension<T extends HostExtensionOptions>(options: T): Resource & Readonly<Pick<T, "createHost">>;
export function defineResource(options: Options & {kind: string}): Resource;
export interface PluginOptions extends Options {id: string; resources: readonly Resource[]; config_schema?: Readonly<Record<string, Json>>; config_defaults?: Readonly<Record<string, Json>>; compiler?: Source | ((context: any) => any); runtime?: Source | ((context: any) => any); targets?: readonly ("node" | "browser")[]; declaration_rulesets?: readonly string[]; priority?: number; display_name?: string; description?: string; version?: string}
export function definePlugin<T extends PluginOptions>(options: T): Readonly<T & {abi: "vibeflow.plugin.v3"}>;
