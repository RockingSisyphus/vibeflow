import { createRequire } from "node:module";
import { readFileSync, statSync } from "node:fs";
import { format } from "node:util";
import path from "node:path";
import process from "node:process";
import readline from "node:readline";
import { pathToFileURL } from "node:url";

import {sdkPlugin} from "./sdk_loader.mjs";

const PLUGIN_ABI = "vibeflow.plugin.v3";
const RULE_ABI = "vibeflow.rule.v1";
const instances = new Map();
const sourceAnalyses = new Map();
// Keep trusted implementations' ordinary logging outside the JSONL protocol.
console.log = (...values) => process.stderr.write(format(...values) + "\n");

function failure(code, message, details = {}) {
  const error = new Error(message);
  error.code = code;
  error.details = details;
  throw error;
}
function deepFreeze(value) {
  if (!value || typeof value !== "object" || Object.isFrozen(value)) return value;
  for (const child of Object.values(value)) deepFreeze(child);
  return Object.freeze(value);
}
function jsonValue(value, pathName = "result") {
  if (value === undefined) return null;
  if (value === null || typeof value === "string" || typeof value === "boolean") return value;
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (Array.isArray(value)) return value.map((item, index) => jsonValue(item, `${pathName}[${index}]`));
  if (typeof value === "object") {
    const output = {};
    for (const [key, item] of Object.entries(value)) output[key] = jsonValue(item, `${pathName}.${key}`);
    return output;
  }
  failure("RULE.RESULT.INVALID", `${pathName} must contain portable JSON values`);
}
function ruleJsonValue(value, pathName = "result", active = new Set()) {
  if (value === null || typeof value === "string" || typeof value === "boolean") return value;
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (value && typeof value === "object") {
    const proto = Object.getPrototypeOf(value);
    if ((!Array.isArray(value) && proto !== Object.prototype && proto !== null) || active.has(value)) {
      failure("RULE.RESULT.INVALID", `${pathName} must contain acyclic plain JSON data`);
    }
    active.add(value);
    try {
      if (Array.isArray(value)) {
        return Array.from(value, (item, index) => ruleJsonValue(item, `${pathName}[${index}]`, active));
      }
      if (Reflect.ownKeys(value).some(key => typeof key !== "string")) {
        failure("RULE.RESULT.INVALID", `${pathName} must have string keys`);
      }
      const output = Object.create(null);
      for (const [key, item] of Object.entries(value)) output[key] = ruleJsonValue(item, `${pathName}.${key}`, active);
      return output;
    } finally { active.delete(value); }
  }
  failure("RULE.RESULT.INVALID", `${pathName} must contain portable JSON values`);
}
async function localTools(packageRoot) {
  const require = createRequire(path.join(packageRoot, "package.json"));
  const version = require("typescript");
  let ts = version;
  if (typeof version.createSourceFile !== "function") {
    const [ast, api] = await Promise.all([import(pathToFileURL(require.resolve("typescript/unstable/ast")).href), import(pathToFileURL(require.resolve("typescript/unstable/sync")).href)]);
    ts = {...ast, ...api};
  }
  return { ts, esbuild: require("esbuild") };
}
function sourceService(ts, packageRoot, facts) {
  const provided = new Map();
  for (const source of facts.sources || []) {
    if (source && source.path && typeof source.text === "string") provided.set(path.resolve(source.path), source.text);
  }
  const cache = new Map();
  let api = null;
  const snapshots = [];
  function parsed(file) {
    const absolute = path.resolve(packageRoot, file);
    const text = provided.get(absolute) ?? readFileSync(absolute, "utf8");
    const cached = cache.get(absolute);
    if (cached?.text === text) return cached;
    if(cached){for(const snapshot of snapshots.splice(0))snapshot.dispose();api?.close();api=null;cache.clear();}
    let tree;
    if (typeof ts.createSourceFile === "function") tree = ts.createSourceFile(absolute, text, ts.ScriptTarget.Latest, true);
    else {
      if (!api) api = new ts.API({cwd: packageRoot, fs: {readFile: name => provided.get(path.resolve(name)), fileExists: name => provided.has(path.resolve(name)) ? true : undefined}});
      const snapshot = api.updateSnapshot({openFiles: [absolute]});
      snapshots.push(snapshot);
      tree = snapshot.getDefaultProjectForFile(absolute)?.program.getSourceFile(absolute);
      if (!tree) failure("RULE.SOURCE.UNAVAILABLE", `TypeScript did not parse ${absolute}`);
    }
    const result = { text, tree };
    cache.set(absolute, result);
    return result;
  }
  function location(tree, node) {
    const start = tree.getLineAndCharacterOfPosition(node.getStart(tree));
    const end = tree.getLineAndCharacterOfPosition(node.getEnd());
    return { path: path.resolve(tree.fileName), line: start.line + 1, column: start.character + 1, end_line: end.line + 1, end_column: end.character + 1 };
  }
  function children(node) {
    const result = [];
    if (typeof ts.forEachChild === "function") ts.forEachChild(node, child => { result.push(child); });
    else node.forEachChild(child => { result.push(child); });
    return result;
  }
  function describe(tree, node, recursive = false) {
    return { kind: ts.SyntaxKind[node.kind] || String(node.kind), name: node.name?.getText(tree) || "", text: node.getText(tree), ...location(tree, node), ...(recursive ? { children: children(node).map(child => describe(tree, child, true)) } : {}) };
  }
  function resolvedImport(file, specifier) {
    if (!specifier.startsWith(".")) return null;
    const base = path.resolve(path.dirname(file), specifier);
    const stem = /\.(?:js|jsx|mjs|cjs)$/.test(base) ? base.replace(/\.[^.]+$/, "") : base;
    const candidates = [base, ...[".ts", ".tsx", ".js", ".mjs", ".mts", ".cts"].map(suffix => stem + suffix), path.join(base, "index.ts"), path.join(base, "index.js")];
    return candidates.find(candidate => provided.has(candidate) || (statSync(candidate, {throwIfNoEntry: false})?.isFile() && !path.extname(candidate).includes("json"))) || null;
  }
  function imports(file) {
    const {tree} = parsed(file);
    const result = [];
    function visit(node) {
      const argument = node.moduleSpecifier || (ts.SyntaxKind[node.kind] === "CallExpression" &&
        (ts.SyntaxKind[node.expression.kind] === "ImportKeyword" || node.expression.getText(tree) === "require")
        ? node.arguments?.[0] : null);
      if (argument && ["StringLiteral", "NoSubstitutionTemplateLiteral"].includes(ts.SyntaxKind[argument.kind])) {
        const typeOnly = Boolean(node.importClause?.isTypeOnly || node.isTypeOnly
          || (node.importClause?.namedBindings?.elements?.length && node.importClause.namedBindings.elements.every(item=>item.isTypeOnly)));
        result.push({specifier: argument.text, resolved_path: resolvedImport(tree.fileName, argument.text), type_only: typeOnly, ...location(tree, node)});
      }
      for (const child of children(node)) visit(child);
    }
    visit(tree);
    return result;
  }
  function reachable(file) {
    const found = new Set();
    function visit(current) { const absolute = path.resolve(packageRoot, current); if (found.has(absolute)) return; found.add(absolute); for (const item of imports(absolute)) if (item.resolved_path) visit(item.resolved_path); }
    visit(file); return [...found];
  }
  return Object.freeze({
    dispose() { for (const snapshot of snapshots) snapshot.dispose(); api?.close(); },
    text(file) { const absolute=path.resolve(packageRoot,file);return provided.get(absolute)??readFileSync(absolute,"utf8"); },
    ast(file) { const value = parsed(file);return value.description??=deepFreeze(describe(value.tree,value.tree,true)); },
    symbols(file) {
      const {tree} = parsed(file); const result = [];
      function visit(node, owners = []) {
        const kind = ts.SyntaxKind[node.kind] || "";
        const named = node.name && /Declaration$/.test(kind);
        const name = named ? node.name.getText(tree) : "";
        if (named) result.push({ ...describe(tree, node), qualname: [...owners, name].join(".") });
        for (const child of children(node)) visit(child, named ? [...owners, name] : owners);
      }
      visit(tree); return deepFreeze(result);
    },
    imports(file) { return deepFreeze(imports(file)); },
    reachable(file) { return Object.freeze(reachable(file)); },
    ownership(file, currentFacts = facts) {
      const absolute = path.resolve(packageRoot, file);
      const declared = (currentFacts.source_owners || []).filter(item => path.resolve(item.path) === absolute);
      const nodeTypes = new Set();
      for (const source of currentFacts.sources || []) if (currentFacts.node_types?.[source.owner] && (currentFacts.source_files || []).includes(source.path) && reachable(source.path).includes(absolute)) nodeTypes.add(source.owner);
      return deepFreeze({path: absolute, declared, node_types: [...nodeTypes]});
    },
    nodes(file, kind) {
      const {tree} = parsed(file); const result = [];
      function visit(node) { if ((ts.SyntaxKind[node.kind] || String(node.kind)) === kind) result.push(describe(tree, node)); for (const child of children(node)) visit(child); }
      visit(tree); return deepFreeze(result);
    },
  });
}
function sharedSourceService(record,facts){
  const key=JSON.stringify([record.packageRoot,(facts.sources||[]).map(source=>[source.path,source.text]).sort((a,b)=>String(a[0]).localeCompare(String(b[0])))]);
  if(!sourceAnalyses.has(key))sourceAnalyses.set(key,{service:sourceService(record.tools.ts,record.packageRoot,facts),references:0});
  const analysis=sourceAnalyses.get(key);
  record.analysisKeys??=new Set();
  if(!record.analysisKeys.has(key)){record.analysisKeys.add(key);analysis.references+=1;}
  return analysis.service;
}
function releaseSourceServices(record){
  const errors=[];
  for(const key of record.analysisKeys||[]){
    const analysis=sourceAnalyses.get(key);if(!analysis)continue;
    if(--analysis.references===0){sourceAnalyses.delete(key);try{analysis.service.dispose();}catch(error){errors.push(error);}}
  }
  record.analysisKeys?.clear();
  if(errors.length)throw errors[0];
}
const contributionCallbacks = new Map();
async function loadImplementation(request, isRule) {
  const declaration = isRule ? request.rule : request.plugin;
  const packageRoot = path.resolve(request.packageRoot);
  const source = path.resolve(declaration.module);
  const tools = await localTools(packageRoot);
  const exported = String(declaration.export || (isRule ? "check" : "createPlugin"));
  let callback = contributionCallbacks.get(`${isRule ? "rule" : "plugin"}:${declaration.id}`);
  let bundled;
  if (!callback) {
  try {
    const result = await tools.esbuild.build({ absWorkingDir: packageRoot, entryPoints: [source], bundle: true, write: false, format: "esm", platform: "node", target: ["es2022"], sourcemap: "inline", legalComments: "none", logLevel: "silent", plugins: [sdkPlugin(tools.ts)] });
    bundled = result.outputFiles?.find(item => item.path.endsWith(".js"))?.text || result.outputFiles?.[0]?.text;
  } catch (cause) {
    failure(isRule ? "RULE.IMPLEMENTATION" : "VF_PLUGIN_IMPLEMENTATION", `${declaration.id} could not be bundled`, { cause: String(cause), diagnostics: cause?.errors || [] });
  }
  const module = await import(`data:text/javascript;base64,${Buffer.from(bundled, "utf8").toString("base64")}`);
  callback = exported.split(".").reduce((value, key) => value?.[key], module);
  }
  if (typeof callback !== "function") failure(isRule ? "RULE.IMPLEMENTATION" : "VF_PLUGIN_FACTORY", `${declaration.id} does not export ${exported}()`);
  const controller = new AbortController();
  if (isRule) return { declaration, callback, controller, tools, packageRoot, isRule };
  const pluginType = String(declaration.type || declaration.plugin_type);
  if (!["compiler", "runtime"].includes(pluginType)) failure("VF_PLUGIN_ABI", "Policy plugins were replaced by Rule resources");
  const context = Object.freeze({ abiVersion: PLUGIN_ABI, pluginId: String(declaration.id), pluginType, target: String(request.target), workflowId: String(request.workflowId || ""), config: deepFreeze(jsonValue(declaration.config || {}, "config")), signal: controller.signal });
  const instance = callback(context);
  if (!instance || typeof instance !== "object" || Array.isArray(instance) || typeof instance.then === "function") failure("VF_PLUGIN_FACTORY", `${declaration.id} factory must synchronously return an object`);
  const removed = ["extendPolicy", "validateNode", "validateGraph", "validateNodeset", "validateCompiledGraph"];
  if (removed.some(hook => hook in instance)) failure("VF_PLUGIN_ABI", `${declaration.id} uses removed policy hooks; contribute Rules instead`);
  return { declaration, instance, controller, isRule };
}
async function declarations(request) {
  const packageRoot = path.resolve(request.packageRoot);
  const tools = await localTools(packageRoot);
  const result = await tools.esbuild.build({absWorkingDir: packageRoot, entryPoints: [request.module], bundle: true,
    write: false, metafile: true, format: "esm", platform: "node", target: ["es2022"], sourcemap: "inline", logLevel: "silent",
    plugins: [sdkPlugin(tools.ts)]});
  const text = result.outputFiles[0].text;
  const module = await import(`data:text/javascript;base64,${Buffer.from(text).toString("base64")}`);
  const plugin = module[request.export || "plugin"];
  if (!plugin || typeof plugin !== "object" || plugin.abi !== PLUGIN_ABI || !Array.isArray(plugin.resources)) {
    failure("PLUGIN.DECLARATION.EXPORT", "plugin export must be a fixed SDK plugin object");
  }
  for (const resource of plugin.resources) {
    const descriptor = resource.descriptor;
    const callback = descriptor.kind === "rule" ? resource.check :
      descriptor.kind === "plugin" ? plugin[descriptor.type] : undefined;
    if (typeof callback === "function") contributionCallbacks.set(`${descriptor.kind}:${descriptor.id}`, callback);
  }
  return ruleJsonValue({id: plugin.id, abi: plugin.abi, config_schema: plugin.config_schema,
    config_defaults: plugin.config_defaults, origin: plugin.origin, declaration: plugin.declaration,
    included_sources: Object.keys(result.metafile.inputs).map(file => path.resolve(packageRoot,file)),
    loaded_sources: [...new Set([path.resolve(request.module), ...plugin.resources.map(resource => resource.origin?.path).filter(Boolean)])],
    resources: plugin.resources.map(resource => ({descriptor: resource.descriptor, origin: resource.origin}))});
}
async function dispatch(request) {
  const command = String(request.command || "");
  if (command === "declarations") return declarations(request);
  const sessionId = String(request.sessionId || "");
  if (!sessionId) failure("VF_PLUGIN_PROCESS", "worker request requires sessionId");
  if (command === "open" || command === "openRule") {
    if (instances.has(sessionId)) failure("VF_PLUGIN_PROCESS", `duplicate session '${sessionId}'`);
    instances.set(sessionId, await loadImplementation(request, command === "openRule"));
    return { opened: true };
  }
  const record = instances.get(sessionId);
  if (!record) failure("VF_PLUGIN_PROCESS", `unknown session '${sessionId}'`);
  if (command === "evaluateRule") {
    if (!record.isRule) failure("RULE.IMPLEMENTATION", "session does not contain a Rule");
    const supplied = deepFreeze(jsonValue(request.context || {}, "context"));
    const sourceAnalysis = sharedSourceService(record, supplied.facts || {});
    const {dispose, ownership, ...syntaxSources} = sourceAnalysis;
    const publicSources = {...syntaxSources,ownership:file=>ownership(file,supplied.facts||{})};
    const context = Object.freeze({ ...supplied, abiVersion: RULE_ABI, ruleId: String(record.declaration.id), signal: record.controller.signal, sources: Object.freeze(publicSources) });
    const result = await record.callback(context, deepFreeze(jsonValue(request.inputs || {}, "inputs")), deepFreeze(jsonValue(request.params || {}, "params")));
    return { implemented: true, result: ruleJsonValue(result, "result") };
  }
  if (command === "invoke") {
    const hook = String(request.hook || ""); const callback = record.instance[hook];
    if (callback === undefined) return { implemented: false, result: null };
    if (typeof callback !== "function") failure("VF_PLUGIN_HOOK_RESULT", `${record.declaration.id}.${hook} is not callable`);
    let returned;
    try { returned = callback(deepFreeze(jsonValue(request.payload || {}, "payload"))); }
    catch (cause) { failure("VF_PLUGIN_HOOK_RESULT", `${record.declaration.id}.${hook} failed: ${cause instanceof Error ? cause.message : cause}`); }
    if (record.declaration.completion !== "suspend" && returned && typeof returned.then === "function") failure("VF_PLUGIN_COMPLETION", `${record.declaration.id}.${hook} returned a Promise with immediate completion`);
    const result = await returned;
    return { implemented: true, result: jsonValue(result, "result") };
  }
  if (command === "close") {
    record.controller.abort("session closed");
    let error;
    try {
      if (typeof record.instance?.dispose === "function") await record.instance.dispose();
    } catch(cause){error=cause;}
    finally {
      instances.delete(sessionId);
      try{releaseSourceServices(record);}catch(cause){if(!error)error=cause;else error.details={...error.details,cleanup_errors:[{phase:"source-analysis",message:String(cause)}]};}
    }
    if(error)throw error;
    return { closed: true };
  }
  failure("VF_PLUGIN_PROCESS", `unknown worker command '${command}'`);
}
const input = readline.createInterface({ input: process.stdin, crlfDelay: Infinity });
for await (const line of input) {
  if (!line.trim()) continue;
  try {
    const result = await dispatch(JSON.parse(line));
    process.stdout.write(`${JSON.stringify({ ok: true, result })}\n`);
  } catch (error) {
    process.stdout.write(`${JSON.stringify({ ok: false, error: { code: error?.code || "RULE.EXECUTION", message: error instanceof Error ? error.message : String(error), details: error?.details || {} } })}\n`);
  }
}
