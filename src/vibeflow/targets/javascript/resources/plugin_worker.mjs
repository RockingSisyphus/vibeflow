import { createRequire } from "node:module";
import { mkdtemp, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import process from "node:process";
import readline from "node:readline";
import { pathToFileURL } from "node:url";

const PLUGIN_ABI = "vibeflow.plugin.v1";
const instances = new Map();

function visitChildren(ts, node, visitor) {
  if (typeof ts.forEachChild === "function") ts.forEachChild(node, visitor);
  else if (typeof node.forEachChild === "function") node.forEachChild(visitor);
}

function isKind(ts, node, legacyName, nativeName, syntaxName) {
  const predicate = ts[legacyName] || ts[nativeName];
  if (typeof predicate === "function") return predicate(node);
  return node?.kind === ts.SyntaxKind[syntaxName];
}

function isStringLiteralLike(ts, node) {
  return isKind(
    ts,
    node,
    "isStringLiteralLike",
    "isStringLiteral",
    "StringLiteral",
  ) || isKind(
    ts,
    node,
    "isNoSubstitutionTemplateLiteral",
    "isNoSubstitutionTemplateLiteral",
    "NoSubstitutionTemplateLiteral",
  );
}

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
  if (value === null || typeof value === "string" || typeof value === "boolean") {
    return value;
  }
  if (typeof value === "number") {
    if (!Number.isFinite(value)) failure("VF_PLUGIN_HOOK_RESULT", `${pathName} contains a non-finite number`);
    return value;
  }
  if (Array.isArray(value)) {
    return value.map((item, index) => jsonValue(item, `${pathName}[${index}]`));
  }
  if (typeof value === "object") {
    const output = {};
    for (const [key, item] of Object.entries(value)) {
      output[key] = jsonValue(item, `${pathName}.${key}`);
    }
    return output;
  }
  failure("VF_PLUGIN_HOOK_RESULT", `${pathName} must contain JSON values`);
}

async function localTools(packageRoot) {
  const require = createRequire(path.join(packageRoot, "package.json"));
  let ts;
  let esbuild;
  try {
    const version = require("typescript");
    if (typeof version.createProgram === "function") {
      ts = version;
    } else {
      const astPath = require.resolve("typescript/unstable/ast");
      const apiPath = require.resolve("typescript/unstable/sync");
      const [ast, api] = await Promise.all([
        import(pathToFileURL(astPath).href),
        import(pathToFileURL(apiPath).href),
      ]);
      ts = {
        ...ast,
        ...api,
        version: String(version.version || ""),
        __native: true,
      };
    }
    esbuild = require("esbuild");
  } catch (cause) {
    failure("VF_PLUGIN_TYPECHECK", "project-local TypeScript/esbuild cannot be resolved", {
      cause: String(cause),
    });
  }
  return { ts, esbuild };
}

function callableReturnsPromise(ts, checker, node) {
  if (!checker) return false;
  try {
    let signature = typeof checker.getSignatureFromDeclaration === "function"
      ? checker.getSignatureFromDeclaration(node)
      : null;
    if (!signature) {
      const type = checker.getTypeAtLocation(node.name || node);
      signature = checker.getSignaturesOfType(type, ts.SignatureKind.Call)[0];
    }
    if (!signature) return false;
    const returnType = typeof checker.getReturnTypeOfSignature === "function"
      ? checker.getReturnTypeOfSignature(signature)
      : signature.getReturnType();
    const text = checker.typeToString(returnType);
    if (/\bPromise(?:Like)?\s*</.test(text)) return true;
    if (typeof checker.getPromisedTypeOfPromise === "function"
        && checker.getPromisedTypeOfPromise(returnType)) return true;
    return Boolean(checker.getPropertyOfType?.(returnType, "then"));
  } catch {
    return false;
  }
}

function unwrapExpression(ts, node) {
  let current = node;
  while (current) {
    if (ts.isParenthesizedExpression?.(current)
        || ts.isAsExpression?.(current)
        || ts.isTypeAssertionExpression?.(current)
        || ts.isNonNullExpression?.(current)
        || ts.isSatisfiesExpression?.(current)) {
      current = current.expression;
      continue;
    }
    return current;
  }
  return current;
}

function isAssignmentOperator(ts, kind) {
  return kind >= ts.SyntaxKind.FirstAssignment
    && kind <= ts.SyntaxKind.LastAssignment;
}

function isDeepFrozenLiteral(ts, node, insideFreeze = false) {
  const value = unwrapExpression(ts, node);
  if (!value) return true;
  if (isStringLiteralLike(ts, value)
      || ts.isNumericLiteral(value)
      || value.kind === ts.SyntaxKind.TrueKeyword
      || value.kind === ts.SyntaxKind.FalseKeyword
      || value.kind === ts.SyntaxKind.NullKeyword
      || value.kind === ts.SyntaxKind.UndefinedKeyword
      || ts.isArrowFunction(value)
      || ts.isFunctionExpression(value)) return true;
  if (ts.isNoSubstitutionTemplateLiteral(value)) return true;
  if (ts.isArrayLiteralExpression(value)) {
    return insideFreeze && value.elements.every(
      (item) => isDeepFrozenLiteral(ts, item),
    );
  }
  if (ts.isObjectLiteralExpression(value)) {
    return insideFreeze && value.properties.every((item) => {
      if (ts.isPropertyAssignment(item)) {
        return isDeepFrozenLiteral(ts, item.initializer);
      }
      return ts.isMethodDeclaration(item)
        || ts.isGetAccessorDeclaration?.(item)
        || ts.isSetAccessorDeclaration?.(item);
    });
  }
  if (ts.isCallExpression(value)
      && ts.isPropertyAccessExpression(value.expression)
      && ts.isIdentifier(value.expression.expression)
      && value.expression.expression.text === "Object"
      && value.expression.name.text === "freeze"
      && value.arguments.length === 1) {
    return isDeepFrozenLiteral(ts, value.arguments[0], true);
  }
  if (ts.isPrefixUnaryExpression(value)) {
    return value.operator !== ts.SyntaxKind.PlusPlusToken
      && value.operator !== ts.SyntaxKind.MinusMinusToken
      && value.operator !== ts.SyntaxKind.DeleteKeyword
      && isDeepFrozenLiteral(ts, value.operand);
  }
  if (ts.isBinaryExpression(value)) {
    return !isAssignmentOperator(ts, value.operatorToken.kind)
      && value.operatorToken.kind !== ts.SyntaxKind.CommaToken
      && isDeepFrozenLiteral(ts, value.left)
      && isDeepFrozenLiteral(ts, value.right);
  }
  if (ts.isConditionalExpression(value)) {
    return isDeepFrozenLiteral(ts, value.condition)
      && isDeepFrozenLiteral(ts, value.whenTrue)
      && isDeepFrozenLiteral(ts, value.whenFalse);
  }
  return ts.isIdentifier(value)
    && new Set(["undefined", "NaN", "Infinity"]).has(value.text);
}

function auditPluginModuleState(ts, sourceFile, plugin) {
  const findings = [];
  const report = (node, code, message) => {
    const position = sourceFile.getLineAndCharacterOfPosition(node.getStart(sourceFile));
    findings.push({
      code,
      message,
      owner: plugin.id,
      file: path.resolve(sourceFile.fileName),
      line: position.line + 1,
      column: position.character + 1,
    });
  };
  for (const statement of sourceFile.statements) {
    if (ts.isImportDeclaration(statement)) {
      const clause = statement.importClause;
      if (!clause || (!clause.name && !clause.namedBindings)) {
        report(
          statement,
          "VF_MODULE_STATE",
          `plugin '${plugin.id}' cannot use a side-effect-only import`,
        );
      }
      continue;
    }
    if (ts.isImportEqualsDeclaration?.(statement)
        || ts.isExportDeclaration(statement)
        || ts.isFunctionDeclaration(statement)
        || ts.isInterfaceDeclaration(statement)
        || ts.isTypeAliasDeclaration(statement)
        || ts.isEmptyStatement(statement)) continue;
    if (ts.isVariableStatement(statement)) {
      const immutable = Boolean(
        statement.declarationList.flags & ts.NodeFlags.Const
      );
      if (immutable && statement.declarationList.declarations.every(
        (item) => isDeepFrozenLiteral(ts, item.initializer),
      )) continue;
    }
    if (ts.isExpressionStatement(statement)
        && isStringLiteralLike(ts, statement.expression)) continue;
    report(
      statement,
      "VF_MODULE_STATE",
      `plugin '${plugin.id}' cannot retain mutable or executable module state`,
    );
  }
  return findings;
}

function identifierIsRuntimeReference(ts, node) {
  const parent = node.parent;
  if (!parent) return true;
  if ((ts.isPropertyAccessExpression(parent) && parent.name === node)
      || (ts.isPropertyAssignment(parent) && parent.name === node)
      || (ts.isMethodDeclaration(parent) && parent.name === node)
      || (ts.isVariableDeclaration(parent) && parent.name === node)
      || ts.isImportSpecifier(parent)
      || ts.isExportSpecifier(parent)
      || ts.isBindingElement(parent)
      || ts.isTypeReferenceNode(parent)
      || ts.isTypeQueryNode?.(parent)) return false;
  let current = parent;
  while (current && !ts.isSourceFile(current)) {
    if (ts.isTypeNode?.(current)) return false;
    if (ts.isAsExpression?.(current) && current.expression === node) return true;
    current = current.parent;
  }
  return true;
}

function auditPluginHostGlobals(ts, sourceFile, plugin, checker) {
  const findings = [];
  // This is a plugin/host-extension responsibility boundary, not a platform
  // compatibility list. It is intentionally the union of common browser and
  // Node host primitives for every selected build target.
  const hostRoots = new Set([
    "globalThis", "window", "self", "global", "document", "process",
    "localStorage", "sessionStorage", "navigator", "location", "fetch",
    "XMLHttpRequest", "WebSocket", "EventSource", "indexedDB", "caches",
    "Worker", "SharedWorker",
  ]);
  function locallyDeclared(node) {
    try {
      const symbol = checker?.getSymbolAtLocation(node);
      return Boolean(symbol?.declarations?.some((item) => {
        const file = item.getSourceFile();
        return !file.isDeclarationFile && path.resolve(file.fileName) === path.resolve(sourceFile.fileName);
      }));
    } catch {
      return false;
    }
  }
  function visit(node) {
    if (ts.isIdentifier(node)
        && hostRoots.has(node.text)
        && identifierIsRuntimeReference(ts, node)
        && !locallyDeclared(node)) {
      const position = sourceFile.getLineAndCharacterOfPosition(node.getStart(sourceFile));
      findings.push({
        code: "VF_PLUGIN_HOST_IO",
        message: `plugin '${plugin.id}' cannot access host primitive '${node.text}'; use a host_extension`,
        owner: plugin.id,
        file: path.resolve(sourceFile.fileName),
        line: position.line + 1,
        column: position.character + 1,
      });
    }
    visitChildren(ts, node, visit);
  }
  visit(sourceFile);
  return findings;
}

function pluginSourceAudit(ts, sourceFile, plugin, checker) {
  const findings = [
    ...auditPluginModuleState(ts, sourceFile, plugin),
    ...auditPluginHostGlobals(ts, sourceFile, plugin, checker),
  ];
  const report = (node, code, message) => {
    const position = sourceFile.getLineAndCharacterOfPosition(node.getStart(sourceFile));
    findings.push({
      code,
      message,
      owner: plugin.id,
      file: path.resolve(sourceFile.fileName),
      line: position.line + 1,
      column: position.character + 1,
    });
  };
  function visit(node) {
    if (ts.isCallExpression(node)) {
      const expression = node.expression;
      const name = ts.isIdentifier(expression)
        ? expression.text
        : ts.isPropertyAccessExpression(expression)
          ? expression.name.text
          : "";
      if (new Set(["addEventListener", "eventOn", "on", "once", "setInterval", "setTimeout"]).has(name)) {
        report(
          node,
          "VF_PLUGIN_LONG_LIVED_LISTENER",
          `plugin '${plugin.id}' cannot register long-lived listeners or timers`,
        );
      }
      const dynamicImport = expression.kind === ts.SyntaxKind.ImportKeyword;
      const requireCall = ts.isIdentifier(expression) && expression.text === "require";
      if ((dynamicImport || requireCall)
          && (!node.arguments[0] || !isStringLiteralLike(ts, node.arguments[0]))) {
        report(node, "VF_PLUGIN_IMPORT_POLICY", "plugin imports must use static string literals");
      }
      const promiseChain = ts.isPropertyAccessExpression(expression)
        && new Set(["then", "catch", "finally"]).has(expression.name.text);
      if (promiseChain && ts.isExpressionStatement(node.parent)) {
        report(node, "VF_PLUGIN_PROMISE_UNOWNED", `plugin '${plugin.id}' discards Promise work`);
      }
    }
    if (plugin.completion === "immediate"
        && (ts.isFunctionDeclaration(node)
          || ts.isFunctionExpression(node)
          || ts.isArrowFunction(node)
          || ts.isMethodDeclaration(node))
        && (node.modifiers?.some((item) => item.kind === ts.SyntaxKind.AsyncKeyword)
          || callableReturnsPromise(ts, checker, node))) {
      report(node, "VF_COMPLETION_IMMEDIATE_PROMISE", `immediate plugin '${plugin.id}' cannot declare async functions`);
    }
    visitChildren(ts, node, visit);
  }
  visit(sourceFile);
  return findings;
}

async function loadPlugin(request) {
  const plugin = request.plugin || {};
  const packageRoot = path.resolve(request.packageRoot);
  const source = path.resolve(plugin.module || "");
  if (!source.startsWith(`${packageRoot}${path.sep}`) && source !== packageRoot) {
    failure("VF_PLUGIN_IMPLEMENTATION", `plugin '${plugin.id}' source escapes package_root`, { source });
  }
  const tools = await localTools(packageRoot);
  const jsonCompilerOptions = {
    allowJs: true,
    checkJs: true,
    target: "ES2022",
    module: "ESNext",
    moduleResolution: "Bundler",
    strict: true,
    noEmit: true,
    skipLibCheck: true,
    lib: request.target === "browser"
      ? ["ES2022", "DOM", "DOM.Iterable"]
      : ["ES2022"],
  };
  let sourceFile;
  let sourceFiles = [];
  let checker;
  let dispose = () => {};
  let temporaryRoot = null;
  if (tools.ts.__native) {
    temporaryRoot = await mkdtemp(path.join(os.tmpdir(), "vibeflow-plugin-ts-"));
    const configPath = path.join(temporaryRoot, "tsconfig.json");
    await writeFile(configPath, JSON.stringify({
      compilerOptions: jsonCompilerOptions,
      files: [source],
    }), "utf8");
    const api = new tools.ts.API({ cwd: packageRoot });
    let snapshot;
    try {
      snapshot = api.updateSnapshot({ openProjects: [configPath] });
      const project = snapshot.getProject(configPath) || snapshot.getProjects()[0];
      if (!project) {
        failure("VF_PLUGIN_TYPECHECK", "TypeScript did not create a plugin project");
      }
      const program = project.program;
      checker = project.checker;
      sourceFile = program.getSourceFile(source);
      sourceFiles = program.getSourceFileNames()
        .map((name) => program.getSourceFile(name))
        .filter(Boolean);
    } catch (cause) {
      snapshot?.dispose();
      api.close();
      throw cause;
    }
    dispose = () => {
      snapshot.dispose();
      api.close();
    };
  } else {
    const compilerOptions = {
      ...jsonCompilerOptions,
      target: tools.ts.ScriptTarget.ES2022,
      module: tools.ts.ModuleKind.ESNext,
      moduleResolution: tools.ts.ModuleResolutionKind.Bundler,
      lib: request.target === "browser"
        ? ["lib.es2022.d.ts", "lib.dom.d.ts", "lib.dom.iterable.d.ts"]
        : ["lib.es2022.d.ts"],
    };
    const program = tools.ts.createProgram({ rootNames: [source], options: compilerOptions });
    checker = program.getTypeChecker();
    sourceFile = program.getSourceFile(source);
    sourceFiles = program.getSourceFiles();
  }
  try {
    const packagePrefix = `${packageRoot}${path.sep}`;
    const localSources = sourceFiles.filter((item) => {
      const file = path.resolve(item.fileName);
      return !item.isDeclarationFile
        && (file === packageRoot || file.startsWith(packagePrefix))
        && !file.includes(`${path.sep}node_modules${path.sep}`);
    });
    const findings = localSources.flatMap(
      (item) => pluginSourceAudit(tools.ts, item, plugin, checker),
    );
    if (sourceFile && !localSources.includes(sourceFile)) {
      findings.push({
        code: "VF_PLUGIN_IMPORT_POLICY",
        message: `plugin '${plugin.id}' source is outside package_root`,
        owner: plugin.id,
        file: path.resolve(sourceFile.fileName),
        line: 1,
        column: 1,
      });
    }
    if (findings.length) {
      failure("VF_PLUGIN_TYPECHECK", `plugin '${plugin.id}' failed static validation`, {
        diagnostics: findings,
      });
    }
  } finally {
    dispose();
    if (temporaryRoot) await rm(temporaryRoot, { recursive: true, force: true });
  }
  let bundled;
  try {
    const result = await tools.esbuild.build({
      absWorkingDir: packageRoot,
      entryPoints: [source],
      bundle: true,
      write: false,
      format: "esm",
      platform: request.target === "browser" ? "browser" : "node",
      target: ["es2022"],
      sourcemap: "inline",
      legalComments: "none",
      logLevel: "silent",
    });
    bundled = result.outputFiles?.find((item) => item.path.endsWith(".js"))?.text
      || result.outputFiles?.[0]?.text;
  } catch (cause) {
    failure("VF_PLUGIN_TYPECHECK", `plugin '${plugin.id}' could not be bundled`, {
      cause: String(cause),
    });
  }
  const url = `data:text/javascript;base64,${Buffer.from(bundled, "utf8").toString("base64")}`;
  let module;
  try {
    module = await import(url);
  } catch (cause) {
    failure("VF_PLUGIN_IMPLEMENTATION", `plugin '${plugin.id}' module failed to load`, {
      cause: String(cause),
    });
  }
  const exported = String(plugin.export || "createPlugin");
  const factory = module[exported];
  if (typeof factory !== "function") {
    failure("VF_PLUGIN_FACTORY", `plugin '${plugin.id}' does not export ${exported}()`);
  }
  const controller = new AbortController();
  const context = Object.freeze({
    abiVersion: PLUGIN_ABI,
    pluginId: String(plugin.id),
    pluginType: String(plugin.plugin_type),
    target: String(request.target),
    workflowId: String(request.workflowId || ""),
    config: deepFreeze(jsonValue(plugin.config || {}, "config")),
    signal: controller.signal,
  });
  let instance;
  try {
    instance = factory(context);
  } catch (cause) {
    failure("VF_PLUGIN_FACTORY", `plugin '${plugin.id}' factory failed`, { cause: String(cause) });
  }
  if (!instance || typeof instance !== "object" || Array.isArray(instance)) {
    failure("VF_PLUGIN_FACTORY", `plugin '${plugin.id}' factory must return an object`);
  }
  return { plugin, instance, controller };
}

async function dispatch(request) {
  const command = String(request.command || "");
  const sessionId = String(request.sessionId || "");
  if (!sessionId) failure("VF_PLUGIN_PROCESS", "plugin worker request requires sessionId");
  if (command === "open") {
    if (instances.has(sessionId)) failure("VF_PLUGIN_PROCESS", `duplicate plugin session '${sessionId}'`);
    instances.set(sessionId, await loadPlugin(request));
    return { opened: true };
  }
  const record = instances.get(sessionId);
  if (!record) failure("VF_PLUGIN_PROCESS", `unknown plugin session '${sessionId}'`);
  if (command === "invoke") {
    const hook = String(request.hook || "");
    const callback = record.instance[hook];
    if (callback === undefined) return { implemented: false, result: null };
    if (typeof callback !== "function") {
      failure("VF_PLUGIN_HOOK_RESULT", `plugin '${record.plugin.id}' hook '${hook}' is not callable`);
    }
    try {
      const result = await callback(deepFreeze(jsonValue(request.payload || {}, "payload")));
      return { implemented: true, result: jsonValue(result, "result") };
    } catch (cause) {
      failure("VF_PLUGIN_HOOK_RESULT", `plugin '${record.plugin.id}' hook '${hook}' failed`, {
        cause: String(cause),
      });
    }
  }
  if (command === "close") {
    record.controller.abort("plugin build session closed");
    instances.delete(sessionId);
    return { closed: true };
  }
  failure("VF_PLUGIN_PROCESS", `unknown plugin worker command '${command}'`);
}

const input = readline.createInterface({ input: process.stdin, crlfDelay: Infinity });
for await (const line of input) {
  if (!line.trim()) continue;
  let request;
  try {
    request = JSON.parse(line);
    const result = await dispatch(request);
    process.stdout.write(`${JSON.stringify({ ok: true, result })}\n`);
  } catch (error) {
    process.stdout.write(`${JSON.stringify({
      ok: false,
      error: {
        code: error?.code || "VF_PLUGIN_PROCESS",
        message: error instanceof Error ? error.message : String(error),
        details: error?.details || {},
      },
    })}\n`);
  }
}
