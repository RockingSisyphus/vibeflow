import {nodeDefinition} from "./node_declarations.mjs";
/** Pure declarations: importing a resource does not register it. */
const ABI = "vibeflow.plugin.v4";
const directBindings = new WeakMap();
// Source references are literal filesystem paths, including %, # and spaces.
function resolveFileReference(ref, base) {
  const encodePath = path => String(path).split("/").map(encodeURIComponent).join("/");
  return decodeURIComponent(new URL(encodePath(ref), `file://${encodePath(base)}`).pathname);
}
function freeze(value) {
  if (value && typeof value === "object" && !Object.isFrozen(value)) {
    for (const item of Object.values(value)) freeze(item);
    Object.freeze(value);
  }
  return value;
}
function define(kind, options, member) {
  const {__origin = {}, __resolveExport, __sourceRoot, source, implementation_files = [], [member || "__none"]: callable, ...data} = options;
  const files = implementationFiles(implementation_files, __origin);
  if (member && typeof callable !== "function" && !source && !data.implementations && !(kind === "rule" && data.handler)) throw new TypeError(`${kind}.${member} must be a function or use an explicit source`);
  const locator = source || {kind: "file", ref: __origin.path, ...(member ? {export: __origin.symbol + "." + member} : {})};
  const descriptor = {kind, ...data};
  if (["node", "rule", "base_lib", "plugin"].includes(kind) && !(kind === "rule" && data.handler && !source && !callable && !data.implementations)) {
    descriptor.implementations ??= [{language: __origin.language || "javascript", source: locator,
      ...(kind === "rule" ? {} : {targets: data.targets || ["node", "browser"], completion: data.completion || "immediate",
        ...(files.length ? {implementation_files: files} : {})})}];
    if (kind !== "rule" && data.implementations && Array.isArray(data.implementations)) {
      descriptor.implementations = data.implementations.map(item => ({...item,
        implementation_files: [...implementationFiles(item.implementation_files || [], __origin), ...files]}));
    }
    if (kind === "node" || kind === "base_lib") delete descriptor.targets;
    delete descriptor.completion;
  }
  if (kind === "base_lib") {
    descriptor.display_name ??= descriptor.id;
    descriptor.description ??= descriptor.id;
  }

  const resource = freeze({descriptor, origin: __origin, ...(member && callable ? {[member]: callable} : {})});
  if (member && typeof callable === "function") directBindings.set(resource,
    {member, callable, resolveExport: __resolveExport, sourceRoot: __sourceRoot});
  return resource;
}
function normalizeDirect(resource) {
  const binding = directBindings.get(resource);
  if (!binding) return resource;
  const {descriptor, origin} = resource;
  const actual = {kind:"file", ref:origin.path, export:`${origin.symbol}.${binding.member}`};
  const implementations = descriptor.implementations || [];
  const compatible = implementations.filter(item => ["javascript", "typescript"].includes(item.language));
  const conflict = (field, declared) => {
    const error = new TypeError(`declared source for '${descriptor.id || descriptor.type_key}' does not identify its direct JavaScript implementation`);
    error.code = "RESOURCE.IMPLEMENTATION.CONFLICT";
    error.details = {location:{...origin, field}, actual:{path:actual.ref, symbol:actual.export}, declared};
    throw error;
  };
  const field = `${descriptor.kind}.${descriptor.id || descriptor.type_key}.implementations`;
  if (descriptor.kind === "rule" && descriptor.handler) conflict("rule.handler", {handler:descriptor.handler});
  if (compatible.length !== 1) conflict(field, implementations);
  const implementation = compatible[0], source = implementation.source;
  const paths = source?.kind === "file" && typeof source.ref === "string"
    ? [origin.path, `${binding.sourceRoot || ""}/__source__`].map(base => {
        try { return resolveFileReference(source.ref, base); }
        catch { return ""; }
      }) : [];
  let matches = paths.includes(actual.ref) && (!source.export || source.export === actual.export);
  if (!matches && paths.includes(actual.ref) && source.export && binding.resolveExport) {
    const [name, ...members] = source.export.split(".");
    try {
      const exported = members.reduce((value, key) => value?.[key], binding.resolveExport(name));
      matches = exported === binding.callable;
    } catch { /* Uninitialized aliases are unavailable, not a different source. */ }
  }
  if (!matches) conflict(field + `[${implementations.indexOf(implementation)}].source`, source);
  return freeze({...resource, descriptor:{...descriptor, implementations:implementations.map(item =>
    item === implementation ? {...item, source:actual} : item)}});
}
function implementationFiles(values, origin) {
  function invalid(message) {
    const error = new TypeError(message);
    error.code = "DESCRIPTOR.INVALID";
    error.details = {location: {...origin, field: "implementation_files"}};
    throw error;
  }
  if (!Array.isArray(values)) invalid("implementation_files must be an array of explicit files");
  return values.map(value => {
    const source = typeof value === "string" ? {kind: "file", ref: value} : value;
    if (!source || source.kind !== "file" || typeof source.ref !== "string" || !source.ref.trim()) invalid("implementation_files accepts file source references");
    if (/[*?\[\]]/.test(source.ref)) invalid("implementation_files requires explicit files, not glob patterns");
    const base = String(origin.path || "").replaceAll("\\", "/");
    const ref = source.ref.startsWith("/") ? source.ref : resolveFileReference(source.ref, `${base.startsWith("/") ? "" : "/"}${base}`);
    return {...source, ref};
  });
}
export const defineNode = options => nodeDefinition(define, options);
export const defineNodeType = options => define("node_type", options);
export function __discoverResources(namespace, filename) {
  return [...new Set(Object.values(namespace))]
    .filter(value => value?.descriptor && value.origin?.path === filename)
    .map(normalizeDirect);
}
export const defineRule = options => define("rule", options, "check");
export const defineRuleset = options => define("ruleset", options);
export const defineDataSchema = options => define("data_schema", options);
export const defineCapability = options => define("capability", options);
export const defineBaseLib = options => define("base_lib", options, typeof options.implementation === "function" ? "implementation" : undefined);
/** Low-level fixed Descriptor contribution; callable declarations use defineNode/Rule. */
export const defineResource = options => {
  const {__origin = {}, __resolveExport, __sourceRoot, ...descriptor} = options;
  return freeze({descriptor, origin: __origin});
};
export function definePlugin(options) {
  const {__origin = {}, id, resources = [], compiler, runtime, config_schema = {}, config_defaults = {},
    priority = 100, rulesets = [], targets = ["node", "browser"], display_name=id, description="", version="",
    declaration_rulesets = [], implementation_files = [], presentation = {}, base_libs = []} = options;
  const files = implementationFiles(implementation_files, __origin);
  if (!id || typeof id !== "string") throw new TypeError("plugin id must be a non-empty string");
  if (!Array.isArray(resources) || resources.some(value => !value?.descriptor)) {
    throw new TypeError("plugin resources must be fixed SDK resource objects");
  }
  const contributions = resources.map(normalizeDirect);
  if (contributions.some(resource=>resource.descriptor.kind === "node")) throw new TypeError("Plugins contribute NodeTypes; business Nodes belong in project/root nodes/");
  for (const [type, factory] of [["compiler", compiler], ["runtime", runtime]]) {
    if (factory !== undefined) {
      const delayed = factory && typeof factory === "object" && ["file","module","package"].includes(factory.kind) && typeof factory.ref === "string";
      if (typeof factory !== "function" && !delayed) throw new TypeError(`plugin.${type} must be a lifecycle factory or source`);
      contributions.push(define("plugin", {id: `${id}.${type}`, type, targets, priority, rulesets, display_name, description, version,
        implementation_files: files, presentation, base_libs,
        config: {schema: config_schema, defaults: config_defaults},
        source: delayed ? factory : {kind: "file", ref: __origin.path, export: `${__origin.symbol}.${type}`},
        __origin}, undefined));
    }
  }
  const declaration = {kind: "plugin_declaration", id, display_name, description, version,
    rulesets: declaration_rulesets, presentation, base_libs,
    implementations: [{language: __origin.language || "javascript", targets, source: {kind: "file", ref: __origin.path, export: __origin.symbol}, implementation_files: files}]};
  return freeze({abi: ABI, id, resources: contributions, config_schema, config_defaults, declaration,
    ...(compiler ? {compiler} : {}), ...(runtime ? {runtime} : {}), origin: __origin});
}
