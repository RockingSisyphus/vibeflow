/** Pure declarations: importing a resource does not register it. */
const ABI = "vibeflow.plugin.v3";
function freeze(value) {
  if (value && typeof value === "object" && !Object.isFrozen(value)) {
    for (const item of Object.values(value)) freeze(item);
    Object.freeze(value);
  }
  return value;
}
function define(kind, options, member) {
  const {__origin = {}, source, [member || "__none"]: callable, ...data} = options;
  if (member && typeof callable !== "function" && !source && !data.implementations && !(kind === "rule" && data.handler)) throw new TypeError(`${kind}.${member} must be a function or use an explicit source`);
  const locator = source || {kind: "file", ref: __origin.path, ...(member ? {export: __origin.symbol + "." + member} : {})};
  const descriptor = {kind, ...data};
  if (["node", "rule", "base_lib", "host_extension", "plugin"].includes(kind) && !(kind === "rule" && data.handler && !source && !callable && !data.implementations)) {
    descriptor.implementations ??= [{language: __origin.language || "javascript", source: locator,
      ...(kind === "rule" ? {} : {targets: data.targets || ["node", "browser"], completion: data.completion || "immediate"})}];
    if (kind === "node" || kind === "base_lib") delete descriptor.targets;
    delete descriptor.completion;
  }
  if (kind === "base_lib") {
    descriptor.display_name ??= descriptor.id;
    descriptor.description ??= descriptor.id;
  }
  if (kind === "node") {
    descriptor.display_name ??= descriptor.type_key;
    descriptor.description ??= descriptor.type_key;
    descriptor.version ??= "1.0.0";
    descriptor.flow_kind ??= "process";
  }
  return freeze({descriptor, origin: __origin, ...(member && callable ? {[member]: callable} : {})});
}
export const defineNode = options => define("node", options, "run");
export const defineRule = options => define("rule", options, "check");
export const defineRuleset = options => define("ruleset", options);
export const defineDataSchema = options => define("data_schema", options);
export const defineCapability = options => define("capability", options);
export const defineBaseLib = options => define("base_lib", options, typeof options.implementation === "function" ? "implementation" : undefined);
export const defineHostExtension = options => define("host_extension", options, "createHost");
/** Low-level fixed Descriptor contribution; callable declarations use defineNode/Rule. */
export const defineResource = options => {
  const {__origin = {}, ...descriptor} = options;
  return freeze({descriptor, origin: __origin});
};
export function definePlugin(options) {
  const {__origin = {}, id, resources = [], compiler, runtime, config_schema = {}, config_defaults = {},
    priority = 100, rulesets = [], targets = ["node", "browser"], display_name=id, description="", version=""} = options;
  if (!id || typeof id !== "string") throw new TypeError("plugin id must be a non-empty string");
  if (!Array.isArray(resources) || resources.some(value => !value?.descriptor)) {
    throw new TypeError("plugin resources must be fixed SDK resource objects");
  }
  const contributions = [...resources];
  for (const [type, factory] of [["compiler", compiler], ["runtime", runtime]]) {
    if (factory !== undefined) {
      const delayed = factory && typeof factory === "object" && ["file","module","package"].includes(factory.kind) && typeof factory.ref === "string";
      if (typeof factory !== "function" && !delayed) throw new TypeError(`plugin.${type} must be a lifecycle factory or source`);
      contributions.push(define("plugin", {id: `${id}.${type}`, type, targets, priority, rulesets, display_name, description, version,
        config: {schema: config_schema, defaults: config_defaults},
        source: delayed ? factory : {kind: "file", ref: __origin.path, export: `${__origin.symbol}.${type}`},
        __origin}, undefined));
    }
  }
  return freeze({abi: ABI, id, resources: contributions, config_schema, config_defaults,
    ...(compiler ? {compiler} : {}), ...(runtime ? {runtime} : {}), origin: __origin});
}
