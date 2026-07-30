import { createRequire } from "node:module";
import { existsSync, realpathSync } from "node:fs";
import { readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import { pathToFileURL } from "node:url";

const NODE_BUILTINS = new Set([
  "assert", "async_hooks", "buffer", "child_process", "cluster", "console",
  "constants", "crypto", "dgram", "diagnostics_channel", "dns", "domain",
  "events", "fs", "http", "http2", "https", "module", "net", "os", "path",
  "perf_hooks", "process", "punycode", "querystring", "readline", "repl",
  "stream", "string_decoder", "sys", "timers", "tls", "trace_events", "tty",
  "url", "util", "v8", "vm", "wasi", "worker_threads", "zlib",
]);

function fail(code, message, details = {}) {
  const error = new Error(message);
  error.code = code;
  error.details = details;
  throw error;
}

function visitChildren(ts, node, visitor) {
  if (typeof ts.forEachChild === "function") ts.forEachChild(node, visitor);
  else node.forEachChild(visitor);
}

function isKind(ts, node, legacyName, nativeName, syntaxName) {
  const predicate = ts[legacyName] || ts[nativeName];
  if (typeof predicate === "function") return predicate(node);
  return node?.kind === ts.SyntaxKind[syntaxName];
}

function isStringLiteralLike(ts, node) {
  return isKind(ts, node, "isStringLiteralLike", "isStringLiteral", "StringLiteral")
    || isKind(
      ts,
      node,
      "isNoSubstitutionTemplateLiteral",
      "isNoSubstitutionTemplateLiteral",
      "NoSubstitutionTemplateLiteral",
    );
}

async function packageTools(packageRoot) {
  const packageJson = path.join(packageRoot, "package.json");
  const require = createRequire(packageJson);
  let typescript;
  let esbuild;
  try {
    const version = require("typescript");
    if (typeof version.createProgram === "function") {
      typescript = version;
    } else {
      const astPath = require.resolve("typescript/unstable/ast");
      const apiPath = require.resolve("typescript/unstable/sync");
      const [ast, api] = await Promise.all([
        import(pathToFileURL(astPath).href),
        import(pathToFileURL(apiPath).href),
      ]);
      typescript = {
        ...ast,
        ...api,
        version: String(version.version || ""),
        __native: true,
      };
    }
  } catch (cause) {
    fail("VF_TOOLCHAIN_MISSING", "project-local package 'typescript' cannot be resolved", {
      packageRoot,
      cause: String(cause),
    });
  }
  try {
    esbuild = require("esbuild");
  } catch (cause) {
    fail("VF_TOOLCHAIN_MISSING", "project-local package 'esbuild' cannot be resolved", {
      packageRoot,
      cause: String(cause),
    });
  }
  return { typescript, esbuild };
}

function diagnosticText(ts, diagnostic) {
  if (diagnostic && typeof diagnostic.text === "string") {
    return {
      code: diagnostic.code,
      category: diagnostic.category,
      message: diagnostic.text,
      ...(diagnostic.fileName ? { file: path.resolve(diagnostic.fileName) } : {}),
    };
  }
  const message = ts.flattenDiagnosticMessageText(diagnostic.messageText, "\n");
  if (!diagnostic.file || diagnostic.start === undefined) {
    return { code: diagnostic.code, category: diagnostic.category, message };
  }
  const position = diagnostic.file.getLineAndCharacterOfPosition(diagnostic.start);
  return {
    code: diagnostic.code,
    category: diagnostic.category,
    message,
    file: path.resolve(diagnostic.file.fileName),
    line: position.line + 1,
    column: position.character + 1,
  };
}

function isRelativeRuntimeUrl(value) {
  return !/^[A-Za-z][A-Za-z0-9+.-]*:/.test(value)
    && !value.startsWith("//")
    && !value.startsWith("#");
}

function auditSingleEsmConstraints(ts, sourceFile) {
  const findings = [];
  function finding(node, code, message) {
    findings.push(importFinding(sourceFile, node, code, message));
  }
  function isNamedConstructor(node, names) {
    if (ts.isIdentifier(node)) return names.has(node.text);
    return ts.isPropertyAccessExpression(node) && names.has(node.name.text);
  }
  function localStringArgument(call, index = 0) {
    const argument = call.arguments?.[index];
    return argument && isStringLiteralLike(ts, argument)
      && isRelativeRuntimeUrl(argument.text);
  }
  function visit(node) {
    if (ts.isNewExpression(node)
        && isNamedConstructor(node.expression, new Set(["Worker", "SharedWorker"]))) {
      finding(
        node,
        "VF_SINGLE_ESM_WORKER",
        "single-esm cannot contain Worker or SharedWorker entry points",
      );
    }
    if (ts.isNewExpression(node)
        && isNamedConstructor(node.expression, new Set(["URL"]))
        && localStringArgument(node)
        && node.arguments?.[1]?.getText(sourceFile) === "import.meta.url") {
      finding(
        node,
        "VF_SINGLE_ESM_RESOURCE",
        "single-esm cannot retain a local URL relative to import.meta.url",
      );
    }
    if (ts.isCallExpression(node)) {
      const expression = node.expression;
      const propertyName = ts.isPropertyAccessExpression(expression)
        ? expression.name.text
        : "";
      const expressionText = expression.getText(sourceFile);
      if (propertyName === "register"
          && expressionText.endsWith(".serviceWorker.register")) {
        finding(
          node,
          "VF_SINGLE_ESM_WORKER",
          "single-esm cannot register a service worker module",
        );
      }
      if (propertyName === "addModule" && localStringArgument(node)) {
        finding(
          node,
          "VF_SINGLE_ESM_WORKER",
          "single-esm cannot reference a local worklet module",
        );
      }
      if ((expressionText === "fetch"
          || expressionText.endsWith(".fetch")
          || expressionText === "importScripts")
          && localStringArgument(node)) {
        finding(
          node,
          "VF_SINGLE_ESM_RESOURCE",
          "single-esm cannot retain a local runtime resource URL",
        );
      }
    }
    if (ts.isIdentifier(node)
        && node.text === "WebAssembly"
        && identifierIsReference(ts, node)) {
      finding(
        node,
        "VF_SINGLE_ESM_WASM",
        "single-esm cannot depend on an external WebAssembly resource",
      );
    }
    visitChildren(ts, node, visit);
  }
  visit(sourceFile);
  return findings;
}

function auditParsedSource(ts, sourceFile, target, profile) {
  const findings = [];
  function checkSpecifier(node, specifier) {
    if (target !== "browser") return;
    const root = specifier.startsWith("node:")
      ? specifier.slice(5).split("/")[0]
      : specifier.split("/")[0];
    if (specifier.startsWith("node:") || NODE_BUILTINS.has(root)) {
      findings.push(importFinding(
        sourceFile,
        node,
        "VF_IMPORT_TARGET",
        `browser target cannot import Node builtin '${specifier}'`,
      ));
    }
  }
  function visit(node) {
    if (ts.isImportDeclaration(node) || ts.isExportDeclaration(node)) {
      if (node.moduleSpecifier && isStringLiteralLike(ts, node.moduleSpecifier)) {
        checkSpecifier(node.moduleSpecifier, node.moduleSpecifier.text);
      }
    } else if (ts.isCallExpression(node)) {
      const dynamicImport = node.expression.kind === ts.SyntaxKind.ImportKeyword;
      const requireCall = ts.isIdentifier(node.expression) && node.expression.text === "require";
      const dynamicCodeCall = ts.isIdentifier(node.expression)
        && new Set([
          "eval",
          "Function",
          "AsyncFunction",
          "GeneratorFunction",
          "AsyncGeneratorFunction",
        ]).has(node.expression.text);
      const stringTimer = ts.isIdentifier(node.expression)
        && new Set(["setTimeout", "setInterval"]).has(node.expression.text)
        && node.arguments[0]
        && isStringLiteralLike(ts, node.arguments[0]);
      if (dynamicImport || requireCall) {
        const argument = node.arguments[0];
        if (!argument || !isStringLiteralLike(ts, argument)) {
          findings.push(importFinding(
            sourceFile,
            node,
            "VF_IMPORT_DYNAMIC",
            `${dynamicImport ? "dynamic import" : "require"} must use a static string literal`,
          ));
        } else {
          checkSpecifier(argument, argument.text);
        }
      }
      if (dynamicCodeCall || stringTimer) {
        findings.push(importFinding(
          sourceFile,
          node,
          "VF_IMPORT_DYNAMIC_CODE",
          "runtime string evaluation is forbidden in audited JS/TS sources",
        ));
      }
    } else if (ts.isNewExpression(node)
        && ts.isIdentifier(node.expression)
        && new Set([
          "Function",
          "AsyncFunction",
          "GeneratorFunction",
          "AsyncGeneratorFunction",
        ]).has(node.expression.text)) {
      findings.push(importFinding(
        sourceFile,
        node,
        "VF_IMPORT_DYNAMIC_CODE",
        "runtime function construction is forbidden in audited JS/TS sources",
      ));
    } else if (ts.isIdentifier(node)
        && new Set([
          "eval",
          "Function",
          "AsyncFunction",
          "GeneratorFunction",
          "AsyncGeneratorFunction",
        ]).has(node.text)
        && identifierIsReference(ts, node)) {
      const parent = node.parent;
      const alreadyReported = (
        (ts.isCallExpression(parent) || ts.isNewExpression(parent))
        && parent.expression === node
      );
      if (!alreadyReported) {
        findings.push(importFinding(
          sourceFile,
          node,
          "VF_IMPORT_DYNAMIC_CODE",
          `dynamic code primitive '${node.text}' cannot be referenced`,
        ));
      }
    }
    visitChildren(ts, node, visit);
  }
  visit(sourceFile);
  if (profile === "single-esm") {
    findings.push(...auditSingleEsmConstraints(ts, sourceFile));
  }
  return findings;
}

function auditSource(ts, fileName, source, target) {
  const findings = [];
  const scriptKind = /\.(?:tsx|mts|cts)$/i.test(fileName)
    ? ts.ScriptKind.TSX
    : /\.(?:ts)$/i.test(fileName)
      ? ts.ScriptKind.TS
      : ts.ScriptKind.JS;
  const sourceFile = ts.createSourceFile(
    fileName,
    source,
    ts.ScriptTarget.Latest,
    true,
    scriptKind,
  );
  const browserBlocked = new Set([
    "assert", "buffer", "child_process", "cluster", "crypto", "dgram", "dns",
    "events", "fs", "http", "https", "module", "net", "os", "path",
    "perf_hooks", "process", "readline", "stream", "string_decoder",
    "timers", "tls", "tty", "url", "util", "v8", "vm", "worker_threads", "zlib",
  ]);

  function checkSpecifier(node, specifier) {
    if (target !== "browser") return;
    const root = specifier.startsWith("node:")
      ? specifier.slice(5).split("/")[0]
      : specifier.split("/")[0];
    if (specifier.startsWith("node:") || browserBlocked.has(root)) {
      const position = sourceFile.getLineAndCharacterOfPosition(node.getStart(sourceFile));
      findings.push({
        code: "VF_IMPORT_TARGET",
        message: `browser target cannot import Node builtin '${specifier}'`,
        file: path.resolve(fileName),
        line: position.line + 1,
        column: position.character + 1,
      });
    }
  }

  function visit(node) {
    if (ts.isImportDeclaration(node) || ts.isExportDeclaration(node)) {
      if (node.moduleSpecifier && isStringLiteralLike(ts, node.moduleSpecifier)) {
        checkSpecifier(node.moduleSpecifier, node.moduleSpecifier.text);
      }
    } else if (ts.isCallExpression(node)) {
      const isDynamicImport = node.expression.kind === ts.SyntaxKind.ImportKeyword;
      const isRequire = ts.isIdentifier(node.expression) && node.expression.text === "require";
      if (isDynamicImport || isRequire) {
        const argument = node.arguments[0];
        if (!argument || !isStringLiteralLike(ts, argument)) {
          const position = sourceFile.getLineAndCharacterOfPosition(node.getStart(sourceFile));
          findings.push({
            code: "VF_IMPORT_DYNAMIC",
            message: `${isDynamicImport ? "dynamic import" : "require"} must use a static string literal`,
            file: path.resolve(fileName),
            line: position.line + 1,
            column: position.character + 1,
          });
        } else {
          checkSpecifier(argument, argument.text);
        }
      }
    }
    visitChildren(ts, node, visit);
  }
  visit(sourceFile);
  return findings;
}

function normalizeImportPolicy(raw) {
  const policy = raw && typeof raw === "object" ? raw : {};
  const owners = Array.isArray(policy.owners)
    ? policy.owners
      .filter((item) => item && typeof item === "object" && item.path && item.kind && item.id)
      .map((item) => ({
        path: path.resolve(item.path),
        realPath: path.resolve(item.path),
        kind: String(item.kind),
        id: String(item.id),
        export: String(item.export || "run"),
        completion: String(item.completion || "immediate"),
      }))
      .sort((left, right) => right.path.length - left.path.length)
    : [];
  return {
    owners,
    nodeBaseLibs: policy.nodeBaseLibs && typeof policy.nodeBaseLibs === "object"
      ? policy.nodeBaseLibs : {},
    baseLibDependencies: policy.baseLibDependencies && typeof policy.baseLibDependencies === "object"
      ? policy.baseLibDependencies : {},
    hostExtensionDependencies:
      policy.hostExtensionDependencies
      && typeof policy.hostExtensionDependencies === "object"
        ? policy.hostExtensionDependencies : {},
    allowedExternalPackages: new Set(
      Array.isArray(policy.allowedExternalPackages)
        ? policy.allowedExternalPackages.map(String)
        : [],
    ),
  };
}

function normalizedRealPath(ts, value) {
  const resolved = path.resolve(value);
  try {
    if (ts.sys?.realpath) return path.resolve(ts.sys.realpath(resolved));
    return path.resolve(realpathSync.native(resolved));
  } catch {
    return resolved;
  }
}

function ownerFor(ts, fileName, policy) {
  const candidate = normalizedRealPath(ts, fileName);
  for (const owner of policy.owners) {
    const ownerPath = normalizedRealPath(ts, owner.path);
    if (candidate === ownerPath || candidate.startsWith(`${ownerPath}${path.sep}`)) {
      return owner;
    }
  }
  return null;
}

function packageName(specifier) {
  if (specifier.startsWith("@")) return specifier.split("/").slice(0, 2).join("/");
  return specifier.split("/")[0];
}

function importSpecifiers(ts, sourceFile) {
  const imports = [];
  function visit(node) {
    if ((ts.isImportDeclaration(node) || ts.isExportDeclaration(node))
        && node.moduleSpecifier && isStringLiteralLike(ts, node.moduleSpecifier)) {
      imports.push({
        node: node.moduleSpecifier,
        value: node.moduleSpecifier.text,
        declaration: node,
      });
    } else if (ts.isCallExpression(node)) {
      const dynamicImport = node.expression.kind === ts.SyntaxKind.ImportKeyword;
      const requireCall = ts.isIdentifier(node.expression) && node.expression.text === "require";
      const argument = node.arguments[0];
      if ((dynamicImport || requireCall) && argument && isStringLiteralLike(ts, argument)) {
        imports.push({ node: argument, value: argument.text, declaration: node });
      }
    }
    visitChildren(ts, node, visit);
  }
  visit(sourceFile);
  return imports;
}

function importFinding(sourceFile, node, code, message) {
  const position = sourceFile.getLineAndCharacterOfPosition(node.getStart(sourceFile));
  return {
    code,
    message,
    file: path.resolve(sourceFile.fileName),
    line: position.line + 1,
    column: position.character + 1,
  };
}

function symbolDeclarationNodes(symbol, project) {
  return (symbol?.declarations || [])
    .map((declaration) =>
      typeof declaration?.resolve === "function"
        ? declaration.resolve(project)
        : declaration
    )
    .filter(Boolean);
}

function fallbackResolveSpecifier(specifier, sourceFileName) {
  if (!specifier.startsWith(".") && !path.isAbsolute(specifier)) {
    try {
      return createRequire(sourceFileName).resolve(specifier);
    } catch {
      return "";
    }
  }
  const base = path.resolve(path.dirname(sourceFileName), specifier);
  const candidates = [base];
  if (base.endsWith(".js")) {
    candidates.push(
      base.slice(0, -3) + ".ts",
      base.slice(0, -3) + ".tsx",
      base.slice(0, -3) + ".mts",
      base.slice(0, -3) + ".cts",
    );
  } else if (!path.extname(base)) {
    for (const extension of [".ts", ".tsx", ".mts", ".cts", ".js", ".mjs", ".cjs"]) {
      candidates.push(base + extension, path.join(base, `index${extension}`));
    }
  }
  return candidates.find((item) => existsSync(item)) || "";
}

function auditImportOwnership(ts, sourceFile, checker, project, policy) {
  const sourceOwner = ownerFor(ts, sourceFile.fileName, policy);
  if (!sourceOwner
      || !["node", "base_lib", "host_extension"].includes(sourceOwner.kind)) return [];
  const findings = [];
  for (const imported of importSpecifiers(ts, sourceFile)) {
    const specifier = imported.value;
    if (sourceOwner.kind === "base_lib" && isNodeBuiltinSpecifier(specifier)) {
      findings.push(importFinding(
        sourceFile,
        imported.node,
        "VF_BASE_LIB_HOST_IO",
        `base_lib '${sourceOwner.id}' cannot import Node builtin '${specifier}'; use a Capability`,
      ));
      continue;
    }
    const bare = !specifier.startsWith(".") && !path.isAbsolute(specifier);
    const symbol = checker.getSymbolAtLocation(imported.node);
    const declaration = symbolDeclarationNodes(symbol, project)[0];
    const resolvedFileName = declaration?.getSourceFile?.().fileName
      || fallbackResolveSpecifier(specifier, sourceFile.fileName);
    if (!resolvedFileName) {
      if (bare && policy.allowedExternalPackages.has(packageName(specifier))) continue;
      findings.push(importFinding(
        sourceFile,
        imported.node,
        "VF_IMPORT_RESOLVE",
        `cannot resolve import '${specifier}' from ${sourceOwner.kind} '${sourceOwner.id}'`,
      ));
      continue;
    }
    const resolvedFile = normalizedRealPath(ts, resolvedFileName);
    if (resolvedFile.includes(`${path.sep}node_modules${path.sep}`)) {
      const dependency = packageName(specifier);
      if (!policy.allowedExternalPackages.has(dependency)) {
        findings.push(importFinding(
          sourceFile,
          imported.node,
          "VF_IMPORT_EXTERNAL",
          `${sourceOwner.kind} '${sourceOwner.id}' imports undeclared external package '${dependency}'`,
        ));
      }
      continue;
    }
    const destination = ownerFor(ts, resolvedFile, policy);
    if (!destination) {
      findings.push(importFinding(
        sourceFile,
        imported.node,
        "VF_IMPORT_OWNER",
        `${sourceOwner.kind} '${sourceOwner.id}' imports unowned local source '${resolvedFile}'`,
      ));
      continue;
    }
    if (sourceOwner.kind === "node") {
      if (destination.kind === "node" && destination.id !== sourceOwner.id) {
        findings.push(importFinding(
          sourceFile,
          imported.node,
          "VF_IMPORT_NODE_TO_NODE",
          `node '${sourceOwner.id}' cannot import node '${destination.id}'`,
        ));
      } else if (destination.kind === "base_lib") {
        const allowed = new Set(policy.nodeBaseLibs[sourceOwner.id] || []);
        if (!allowed.has(destination.id)) {
          findings.push(importFinding(
            sourceFile,
            imported.node,
            "VF_IMPORT_BASE_LIB",
            `node '${sourceOwner.id}' imports base_lib '${destination.id}' without enabling it`,
          ));
        }
      } else if (["plugin", "runtime", "registry", "capability"].includes(destination.kind)) {
        findings.push(importFinding(
          sourceFile,
          imported.node,
          "VF_IMPORT_LAYER",
          `node '${sourceOwner.id}' cannot import ${destination.kind} '${destination.id}'`,
        ));
      }
    } else if (sourceOwner.kind === "base_lib") {
      if (["node", "plugin", "runtime", "registry", "capability"].includes(destination.kind)) {
        findings.push(importFinding(
          sourceFile,
          imported.node,
          "VF_IMPORT_LAYER",
          `base_lib '${sourceOwner.id}' cannot import ${destination.kind} '${destination.id}'`,
        ));
      } else if (destination.kind === "base_lib" && destination.id !== sourceOwner.id) {
        const allowed = new Set(policy.baseLibDependencies[sourceOwner.id] || []);
        if (!allowed.has(destination.id)) {
          findings.push(importFinding(
            sourceFile,
            imported.node,
            "VF_IMPORT_BASE_LIB",
            `base_lib '${sourceOwner.id}' imports undeclared base_lib dependency '${destination.id}'`,
          ));
        }
      }
    } else if (sourceOwner.kind === "host_extension") {
      if (destination.kind !== "host_extension") {
        findings.push(importFinding(
          sourceFile,
          imported.node,
          "VF_IMPORT_LAYER",
          `host_extension '${sourceOwner.id}' cannot import ${destination.kind} '${destination.id}'`,
        ));
      } else if (destination.id !== sourceOwner.id) {
        const allowed = new Set(
          policy.hostExtensionDependencies[sourceOwner.id] || [],
        );
        if (!allowed.has(destination.id)) {
          findings.push(importFinding(
            sourceFile,
            imported.node,
            "VF_IMPORT_HOST_EXTENSION",
            `host_extension '${sourceOwner.id}' imports undeclared host_extension dependency '${destination.id}'`,
          ));
        }
      }
    }
  }
  return findings;
}

function isNodeBuiltinSpecifier(specifier) {
  const root = specifier.startsWith("node:")
    ? specifier.slice(5).split("/")[0]
    : specifier.split("/")[0];
  return specifier.startsWith("node:") || NODE_BUILTINS.has(root);
}

function unwrapExpression(ts, node) {
  let current = node;
  while (current && (
    ts.isParenthesizedExpression(current)
    || ts.isAsExpression(current)
    || isKind(
      ts,
      current,
      "isTypeAssertionExpression",
      "isTypeAssertion",
      "TypeAssertionExpression",
    )
    || ts.isNonNullExpression(current)
    || (ts.isSatisfiesExpression && ts.isSatisfiesExpression(current))
  )) {
    current = current.expression;
  }
  return current;
}

function isAssignmentOperator(ts, kind) {
  return kind >= ts.SyntaxKind.FirstAssignment
    && kind <= ts.SyntaxKind.LastAssignment;
}

function isObjectFreezeCall(ts, node) {
  const value = unwrapExpression(ts, node);
  return ts.isCallExpression(value)
    && value.arguments.length === 1
    && ts.isPropertyAccessExpression(value.expression)
    && ts.isIdentifier(value.expression.expression)
    && value.expression.expression.text === "Object"
    && value.expression.name.text === "freeze";
}

function hasComputedPropertyName(ts, node) {
  return Boolean(
    node?.name
    && node.name.kind === ts.SyntaxKind.ComputedPropertyName
  );
}

function hasDecorator(ts, node) {
  let found = false;
  function visit(current) {
    if (found) return;
    if (current.kind === ts.SyntaxKind.Decorator
        || current.modifiers?.some(
          (modifier) => modifier.kind === ts.SyntaxKind.Decorator
        )) {
      found = true;
      return;
    }
    visitChildren(ts, current, visit);
  }
  visit(node);
  return found;
}

function isSafeHeritageExpression(ts, node) {
  const value = unwrapExpression(ts, node);
  return ts.isIdentifier(value)
    || value.kind === ts.SyntaxKind.NullKeyword;
}

function isImportSafeClass(ts, node) {
  if (hasDecorator(ts, node)) return false;
  for (const clause of node.heritageClauses || []) {
    for (const type of clause.types || []) {
      if (!isSafeHeritageExpression(ts, type.expression)) return false;
    }
  }
  return node.members.every((member) => {
    if (hasComputedPropertyName(ts, member)) return false;
    if (ts.isClassStaticBlockDeclaration?.(member)) return false;
    const isStatic = member.modifiers?.some(
      (item) => item.kind === ts.SyntaxKind.StaticKeyword
    );
    if (!isStatic) return true;
    return !isKind(
      ts,
      member,
      "isPropertyDeclaration",
      "isPropertyDeclaration",
      "PropertyDeclaration",
    );
  });
}

function isDeepFrozenLiteral(ts, node) {
  const value = unwrapExpression(ts, node);
  if (isObjectFreezeCall(ts, value)) {
    return isDeepFrozenLiteral(ts, value.arguments[0]);
  }
  if (ts.isArrayLiteralExpression(value)) {
    return value.elements.every((item) => {
      if (ts.isSpreadElement(item)) return false;
      const child = unwrapExpression(ts, item);
      if (ts.isArrayLiteralExpression(child) || ts.isObjectLiteralExpression(child)) {
        return false;
      }
      return isImmutableModuleInitializer(ts, child);
    });
  }
  if (ts.isObjectLiteralExpression(value)) {
    return value.properties.every((item) => {
      if (hasComputedPropertyName(ts, item)) return false;
      if (ts.isPropertyAssignment(item)) {
        const child = unwrapExpression(ts, item.initializer);
        if (ts.isArrayLiteralExpression(child) || ts.isObjectLiteralExpression(child)) {
          return false;
        }
        return isImmutableModuleInitializer(ts, child);
      }
      return ts.isMethodDeclaration(item)
        || ts.isGetAccessorDeclaration(item)
        || ts.isSetAccessorDeclaration(item);
    });
  }
  return false;
}

function isPureInitializer(ts, node) {
  const value = unwrapExpression(ts, node);
  if (!value) return true;
  node = value;
  if (!node) return true;
  if (ts.isLiteralExpression(node)
      || node.kind === ts.SyntaxKind.TrueKeyword
      || node.kind === ts.SyntaxKind.FalseKeyword
      || node.kind === ts.SyntaxKind.NullKeyword
      || ts.isFunctionExpression(node)
      || ts.isArrowFunction(node)) return true;
  if (ts.isClassExpression(node)) return isImportSafeClass(ts, node);
  if (ts.isIdentifier(node)) {
    return new Set(["undefined", "NaN", "Infinity"]).has(node.text);
  }
  if (ts.isPrefixUnaryExpression(node)) {
    if (node.operator === ts.SyntaxKind.PlusPlusToken
        || node.operator === ts.SyntaxKind.MinusMinusToken
        || node.operator === ts.SyntaxKind.DeleteKeyword) return false;
    return isPureInitializer(ts, node.operand);
  }
  if (ts.isPostfixUnaryExpression(node)) return false;
  if (ts.isBinaryExpression(node)) {
    if (isAssignmentOperator(ts, node.operatorToken.kind)
        || node.operatorToken.kind === ts.SyntaxKind.CommaToken) return false;
    return isPureInitializer(ts, node.left) && isPureInitializer(ts, node.right);
  }
  if (ts.isConditionalExpression(node)) {
    return isPureInitializer(ts, node.condition)
      && isPureInitializer(ts, node.whenTrue)
      && isPureInitializer(ts, node.whenFalse);
  }
  if (ts.isTemplateExpression(node)) {
    return node.templateSpans.every((item) => isPureInitializer(ts, item.expression));
  }
  if (ts.isNoSubstitutionTemplateLiteral(node)) return true;
  return false;
}

function isImmutableModuleInitializer(ts, node) {
  const value = unwrapExpression(ts, node);
  if (!value) return true;
  if (ts.isArrayLiteralExpression(value) || ts.isObjectLiteralExpression(value)) {
    return false;
  }
  if (isObjectFreezeCall(ts, value)) {
    return isDeepFrozenLiteral(ts, value.arguments[0]);
  }
  return isPureInitializer(ts, value);
}

function importDeclarationHasRuntimeBindings(ts, statement) {
  const clause = statement.importClause;
  if (!clause || clause.isTypeOnly) return Boolean(clause?.isTypeOnly);
  if (clause.name) return true;
  const bindings = clause.namedBindings;
  if (!bindings) return false;
  if (isKind(ts, bindings, "isNamespaceImport", "isNamespaceImport", "NamespaceImport")) {
    return true;
  }
  if (isKind(ts, bindings, "isNamedImports", "isNamedImports", "NamedImports")) {
    return bindings.elements.length > 0;
  }
  return false;
}

function auditTopLevelPurity(ts, sourceFile, policy) {
  const owner = ownerFor(ts, sourceFile.fileName, policy);
  if (!owner
      || !["node", "base_lib", "host_extension"].includes(owner.kind)) return [];
  const findings = [];
  if (hasDecorator(ts, sourceFile)) {
    findings.push(importFinding(
      sourceFile,
      sourceFile,
      "VF_IMPORT_SIDE_EFFECT",
      `${owner.kind} '${owner.id}' cannot use decorators`,
    ));
  }
  for (const statement of sourceFile.statements) {
    let allowed = (ts.isImportDeclaration(statement)
        && importDeclarationHasRuntimeBindings(ts, statement))
      || ts.isImportEqualsDeclaration(statement)
      || ts.isExportDeclaration(statement)
      || ts.isFunctionDeclaration(statement)
      || ts.isInterfaceDeclaration(statement)
      || ts.isTypeAliasDeclaration(statement)
      || ts.isEmptyStatement(statement);
    if (ts.isClassDeclaration(statement)) {
      allowed = isImportSafeClass(ts, statement);
    } else if (ts.isVariableStatement(statement)) {
      const immutable = Boolean(statement.declarationList.flags & ts.NodeFlags.Const);
      allowed = immutable && statement.declarationList.declarations.every(
        (declaration) => isImmutableModuleInitializer(ts, declaration.initializer),
      );
    } else if (ts.isExportAssignment(statement)) {
      allowed = isImmutableModuleInitializer(ts, statement.expression);
    } else if (ts.isExpressionStatement(statement)
        && isStringLiteralLike(ts, statement.expression)) {
      allowed = true;
    }
    if (!allowed) {
      findings.push(importFinding(
        sourceFile,
        statement,
        "VF_IMPORT_SIDE_EFFECT",
        `${owner.kind} '${owner.id}' has forbidden top-level executable or mutable state`,
      ));
    }
  }
  return findings;
}

function hasModifier(ts, node, kind) {
  return Boolean(node?.modifiers?.some((modifier) => modifier.kind === kind));
}

function implementationDeclaration(ts, sourceFile, exportName) {
  for (const statement of sourceFile.statements) {
    if (ts.isFunctionDeclaration(statement)
        && statement.name?.text === exportName) {
      return statement;
    }
    if (!ts.isVariableStatement(statement)) continue;
    for (const declaration of statement.declarationList.declarations) {
      if (ts.isIdentifier(declaration.name)
          && declaration.name.text === exportName
          && declaration.initializer
          && (ts.isArrowFunction(declaration.initializer)
            || ts.isFunctionExpression(declaration.initializer))) {
        return declaration.initializer;
      }
    }
  }
  return null;
}

function callableReturnTypeText(ts, checker, declaration) {
  try {
    const location = declaration.name || declaration;
    const type = checker.getTypeAtLocation(location);
    const signatures = checker.getSignaturesOfType(type, ts.SignatureKind.Call);
    const signature = signatures[0];
    if (!signature) return "";
    const returnType = typeof checker.getReturnTypeOfSignature === "function"
      ? checker.getReturnTypeOfSignature(signature)
      : signature.getReturnType();
    return checker.typeToString(returnType);
  } catch {
    return declaration.type?.getText?.() || "";
  }
}

function promiseLikeTypeText(value) {
  return /\b(?:Promise|PromiseLike)\s*</.test(value)
    || value === "Promise<unknown>"
    || value === "PromiseLike<unknown>";
}

function auditCompletionAndPromiseOwnership(ts, sourceFile, checker, policy) {
  const owner = ownerFor(ts, sourceFile.fileName, policy);
  if (!owner || owner.kind !== "node") return [];
  const declaration = implementationDeclaration(ts, sourceFile, owner.export);
  if (!declaration) return [];
  const findings = [];
  const completion = owner.completion || "immediate";
  const declaredAsync = hasModifier(ts, declaration, ts.SyntaxKind.AsyncKeyword);
  const returnType = callableReturnTypeText(ts, checker, declaration);
  const returnsPromise = promiseLikeTypeText(returnType);
  if (completion === "immediate" && (declaredAsync || returnsPromise)) {
    findings.push(importFinding(
      sourceFile,
      declaration,
      "VF_COMPLETION_IMMEDIATE_PROMISE",
      `node '${owner.id}' declares immediate completion but '${owner.export}' is async or returns ${returnType || "a Promise"}`,
    ));
  }
  if (completion === "suspend" && !declaredAsync && !returnsPromise) {
    findings.push(importFinding(
      sourceFile,
      declaration,
      "VF_COMPLETION_SUSPEND_NON_PROMISE",
      `node '${owner.id}' declares suspend completion but '${owner.export}' does not return a Promise`,
    ));
  }

  function callName(node) {
    if (!ts.isCallExpression(node)) return "";
    const expression = node.expression;
    if (ts.isIdentifier(expression)) return expression.text;
    if (ts.isPropertyAccessExpression(expression)) return expression.name.text;
    return "";
  }

  function visit(node) {
    if (node !== declaration
        && (ts.isFunctionDeclaration(node)
          || ts.isFunctionExpression(node)
          || ts.isArrowFunction(node)
          || ts.isMethodDeclaration(node))) {
      return;
    }
    if (ts.isVoidExpression(node)) {
      let discardedPromise = false;
      try {
        discardedPromise = promiseLikeTypeText(
          checker.typeToString(checker.getTypeAtLocation(node.expression)),
        );
      } catch {
        // A plain `void value` remains legal when the checker cannot prove
        // that the operand is Promise-like.
      }
      if (discardedPromise) {
        findings.push(importFinding(
          sourceFile,
          node,
          "VF_PROMISE_UNOWNED",
          `node '${owner.id}' cannot discard Promise work with void`,
        ));
      }
    }
    if (ts.isCallExpression(node)) {
      const name = callName(node);
      let callReturnsPromise = false;
      try {
        callReturnsPromise = promiseLikeTypeText(
          checker.typeToString(checker.getTypeAtLocation(node)),
        );
      } catch {
        // The syntax checks below remain authoritative when a checker cannot
        // expose a type for this expression.
      }
      if (new Set([
        "addEventListener",
        "eventOn",
        "on",
        "once",
        "setInterval",
        "setTimeout",
      ]).has(name)) {
        findings.push(importFinding(
          sourceFile,
          node,
          "VF_NODE_LONG_LIVED_LISTENER",
          `node '${owner.id}' cannot register listeners or timers outside an explicit TaskPlan or host_extension`,
        ));
      }
      const isPromiseChain = ts.isPropertyAccessExpression(node.expression)
        && new Set(["then", "catch", "finally"]).has(node.expression.name.text);
      if (isPromiseChain && ts.isExpressionStatement(node.parent)) {
        findings.push(importFinding(
          sourceFile,
          node,
          "VF_PROMISE_UNOWNED",
          `node '${owner.id}' cannot start an unowned Promise chain`,
        ));
      }
      if ((completion === "immediate" && callReturnsPromise)
          || (callReturnsPromise && ts.isExpressionStatement(node.parent))) {
        findings.push(importFinding(
          sourceFile,
          node,
          completion === "immediate"
            ? "VF_COMPLETION_IMMEDIATE_PROMISE"
            : "VF_PROMISE_UNOWNED",
          completion === "immediate"
            ? `immediate node '${owner.id}' cannot call Promise-returning code`
            : `node '${owner.id}' cannot discard Promise-returning work`,
        ));
      } else if (completion === "immediate"
          && ((ts.isIdentifier(node.expression)
              && node.expression.text === "Promise")
            || (ts.isPropertyAccessExpression(node.expression)
              && (node.expression.expression.getText(sourceFile) === "Promise"
                || new Set(["then", "catch", "finally"]).has(node.expression.name.text))))) {
        findings.push(importFinding(
          sourceFile,
          node,
          "VF_COMPLETION_IMMEDIATE_PROMISE",
          `immediate node '${owner.id}' cannot create or chain Promise work`,
        ));
      }
    }
    if (completion === "immediate"
        && (ts.isAwaitExpression(node)
          || (ts.isNewExpression(node)
            && node.expression.getText(sourceFile) === "Promise"))) {
      findings.push(importFinding(
        sourceFile,
        node,
        "VF_COMPLETION_IMMEDIATE_PROMISE",
        `immediate node '${owner.id}' cannot await or construct Promise work`,
      ));
    }
    visitChildren(ts, node, visit);
  }
  visit(declaration);
  return findings;
}

function auditModuleRegExpState(ts, sourceFile, policy) {
  const owner = ownerFor(ts, sourceFile.fileName, policy);
  if (!owner
      || !["node", "base_lib", "host_extension"].includes(owner.kind)) return [];
  const findings = [];

  function isFunctionBoundary(node) {
    return ts.isFunctionDeclaration(node)
      || ts.isFunctionExpression(node)
      || ts.isArrowFunction(node)
      || ts.isMethodDeclaration(node)
      || ts.isGetAccessorDeclaration(node)
      || ts.isSetAccessorDeclaration(node)
      || isKind(
        ts,
        node,
        "isConstructorDeclaration",
        "isConstructorDeclaration",
        "Constructor",
      );
  }

  function inspect(node) {
    if (!node || isFunctionBoundary(node)) return;
    if (node.kind === ts.SyntaxKind.RegularExpressionLiteral) {
      const source = node.getText(sourceFile);
      const match = /\/([dgimsuvy]*)$/.exec(source);
      const flags = match?.[1] || "";
      if (flags.includes("g") || flags.includes("y")) {
        findings.push(importFinding(
          sourceFile,
          node,
          "VF_MODULE_STATE",
          `${owner.kind} '${owner.id}' cannot retain a global or sticky RegExp at module scope because test/exec mutates lastIndex across workflow calls`,
        ));
      }
      return;
    }
    visitChildren(ts, node, inspect);
  }

  for (const statement of sourceFile.statements) {
    if (ts.isVariableStatement(statement)) {
      for (const declaration of statement.declarationList.declarations) {
        inspect(declaration.initializer);
      }
    } else if (ts.isExportAssignment(statement)) {
      inspect(statement.expression);
    }
  }
  return findings;
}

function auditModuleStateWrites(ts, sourceFile, checker, project, policy) {
  const owner = ownerFor(ts, sourceFile.fileName, policy);
  if (!owner
      || !["node", "base_lib", "host_extension"].includes(owner.kind)) return [];
  const moduleBindings = new Set();
  const aliases = new Set();
  const builtinPrototypeAliases = new Set();
  const builtinObjectAliases = new Set();
  const builtinConstructors = new Set([
    "Object", "Function", "Array", "Number", "String", "Boolean", "BigInt",
    "Symbol", "Date", "RegExp", "Error", "EvalError", "RangeError",
    "ReferenceError", "SyntaxError", "TypeError", "URIError", "Map", "Set",
    "WeakMap", "WeakSet", "Promise", "ArrayBuffer", "SharedArrayBuffer",
    "DataView", "Int8Array", "Uint8Array", "Uint8ClampedArray", "Int16Array",
    "Uint16Array", "Int32Array", "Uint32Array", "Float32Array",
    "Float64Array", "BigInt64Array", "BigUint64Array", "WeakRef",
    "FinalizationRegistry", "URL", "URLSearchParams",
  ]);
  const builtinObjects = new Set([
    ...builtinConstructors,
    "Math", "JSON", "Reflect", "Atomics", "Intl", "WebAssembly",
  ]);
  const findings = [];

  function addBindingName(name) {
    if (!name) return;
    if (ts.isIdentifier(name)) {
      const symbol = checker.getSymbolAtLocation(name);
      if (symbol) moduleBindings.add(symbol);
      return;
    }
    if (ts.isObjectBindingPattern(name) || ts.isArrayBindingPattern(name)) {
      for (const element of name.elements || []) {
        if (element?.name) addBindingName(element.name);
      }
    }
  }

  for (const statement of sourceFile.statements) {
    if (ts.isFunctionDeclaration(statement)
        || ts.isClassDeclaration(statement)
        || ts.isEnumDeclaration?.(statement)) {
      addBindingName(statement.name);
    } else if (ts.isVariableStatement(statement)) {
      for (const declaration of statement.declarationList.declarations) {
        addBindingName(declaration.name);
      }
    } else if (ts.isImportDeclaration(statement)) {
      const clause = statement.importClause;
      addBindingName(clause?.name);
      const bindings = clause?.namedBindings;
      if (bindings && ts.isNamespaceImport(bindings)) {
        addBindingName(bindings.name);
      } else if (bindings && ts.isNamedImports(bindings)) {
        for (const element of bindings.elements) addBindingName(element.name);
      }
    } else if (ts.isImportEqualsDeclaration(statement)) {
      addBindingName(statement.name);
    }
  }
  for (const symbol of moduleBindings) aliases.add(symbol);

  function rootSymbol(node) {
    let value = unwrapExpression(ts, node);
    while (value && (
      ts.isPropertyAccessExpression(value)
      || ts.isElementAccessExpression(value)
    )) {
      value = unwrapExpression(ts, value.expression);
    }
    if (!value || !ts.isIdentifier(value)) return null;
    return checker.getSymbolAtLocation(value) || null;
  }

  function hasLocalImplementation(node) {
    return symbolDeclarationNodes(
      checker.getSymbolAtLocation(node),
      project,
    ).some((declaration) => {
      const declarationFile = declaration.getSourceFile();
      return !declarationFile.isDeclarationFile
        && normalizedRealPath(ts, declarationFile.fileName)
          === normalizedRealPath(ts, sourceFile.fileName);
    });
  }

  function staticMemberName(node) {
    if (ts.isPropertyAccessExpression(node)) return node.name.text;
    if (!ts.isElementAccessExpression(node)) return null;
    const argument = unwrapExpression(ts, node.argumentExpression);
    return argument && isStringLiteralLike(ts, argument) ? argument.text : null;
  }

  function isUnshadowedNamedGlobal(node, names) {
    const value = unwrapExpression(ts, node);
    return Boolean(
      value
      && ts.isIdentifier(value)
      && names.has(value.text)
      && !hasLocalImplementation(value)
    );
  }

  function isBuiltinPrototypeSource(node) {
    const value = unwrapExpression(ts, node);
    if (!value) return false;
    if (ts.isIdentifier(value)) {
      return builtinPrototypeAliases.has(checker.getSymbolAtLocation(value));
    }
    return (
      (ts.isPropertyAccessExpression(value) || ts.isElementAccessExpression(value))
      && staticMemberName(value) === "prototype"
      && isUnshadowedNamedGlobal(value.expression, builtinConstructors)
    );
  }

  function isBuiltinObjectSource(node) {
    const value = unwrapExpression(ts, node);
    if (!value || !ts.isIdentifier(value)) return false;
    const symbol = checker.getSymbolAtLocation(value);
    return builtinObjectAliases.has(symbol)
      || isUnshadowedNamedGlobal(value, builtinObjects);
  }

  function writesBuiltinPrototype(node) {
    let value = unwrapExpression(ts, node);
    while (value) {
      if (isBuiltinPrototypeSource(value)) return true;
      if (!ts.isPropertyAccessExpression(value)
          && !ts.isElementAccessExpression(value)) return false;
      value = unwrapExpression(ts, value.expression);
    }
    return false;
  }

  function writesBuiltinObject(node) {
    let value = unwrapExpression(ts, node);
    if (!value) return false;
    if (ts.isIdentifier(value)) {
      return isUnshadowedNamedGlobal(value, builtinObjects);
    }
    if (!ts.isPropertyAccessExpression(value)
        && !ts.isElementAccessExpression(value)) return false;
    while (ts.isPropertyAccessExpression(value)
        || ts.isElementAccessExpression(value)) {
      value = unwrapExpression(ts, value.expression);
    }
    return isBuiltinObjectSource(value);
  }

  let changed = true;
  while (changed) {
    changed = false;
    function collect(node) {
      if (ts.isVariableDeclaration(node)
          && ts.isIdentifier(node.name)
          && node.initializer) {
        const source = rootSymbol(node.initializer);
        const destination = checker.getSymbolAtLocation(node.name);
        if (source && aliases.has(source)) {
          if (destination && !aliases.has(destination)) {
            aliases.add(destination);
            changed = true;
          }
        }
        if (isBuiltinPrototypeSource(node.initializer)
            && destination
            && !builtinPrototypeAliases.has(destination)) {
          builtinPrototypeAliases.add(destination);
          changed = true;
        }
        if (isBuiltinObjectSource(node.initializer)
            && destination
            && !builtinObjectAliases.has(destination)) {
          builtinObjectAliases.add(destination);
          changed = true;
        }
      } else if (ts.isBinaryExpression(node)
          && node.operatorToken.kind === ts.SyntaxKind.EqualsToken
          && ts.isIdentifier(unwrapExpression(ts, node.left))
          && isBuiltinPrototypeSource(node.right)) {
        const destination = checker.getSymbolAtLocation(
          unwrapExpression(ts, node.left),
        );
        if (destination && !builtinPrototypeAliases.has(destination)) {
          builtinPrototypeAliases.add(destination);
          changed = true;
        }
      } else if (ts.isBinaryExpression(node)
          && node.operatorToken.kind === ts.SyntaxKind.EqualsToken
          && ts.isIdentifier(unwrapExpression(ts, node.left))
          && isBuiltinObjectSource(node.right)) {
        const destination = checker.getSymbolAtLocation(
          unwrapExpression(ts, node.left),
        );
        if (destination && !builtinObjectAliases.has(destination)) {
          builtinObjectAliases.add(destination);
          changed = true;
        }
      }
      visitChildren(ts, node, collect);
    }
    collect(sourceFile);
  }

  function report(node) {
    findings.push(importFinding(
      sourceFile,
      node,
      "VF_MODULE_STATE",
      `${owner.kind} '${owner.id}' cannot mutate module-scoped state across workflow calls`,
    ));
  }

  function reportBuiltinPrototype(node) {
    findings.push(importFinding(
      sourceFile,
      node,
      "VF_MODULE_STATE",
      `${owner.kind} '${owner.id}' cannot mutate a shared JavaScript builtin prototype across workflow calls`,
    ));
  }

  function reportBuiltinObject(node) {
    findings.push(importFinding(
      sourceFile,
      node,
      "VF_MODULE_STATE",
      `${owner.kind} '${owner.id}' cannot mutate a shared JavaScript builtin object across workflow calls`,
    ));
  }

  function writesAlias(node) {
    const symbol = rootSymbol(node);
    return Boolean(symbol && aliases.has(symbol));
  }

  function visit(node) {
    if (ts.isBinaryExpression(node)
        && isAssignmentOperator(ts, node.operatorToken.kind)) {
      if (writesAlias(node.left)) report(node.left);
      else if (writesBuiltinPrototype(node.left)) {
        reportBuiltinPrototype(node.left);
      } else if (writesBuiltinObject(node.left)) {
        reportBuiltinObject(node.left);
      }
    } else if (isKind(
      ts,
      node,
      "isDeleteExpression",
      "isDeleteExpression",
      "DeleteExpression",
    )) {
      if (writesAlias(node.expression)) report(node.expression);
      else if (writesBuiltinPrototype(node.expression)) {
        reportBuiltinPrototype(node.expression);
      } else if (writesBuiltinObject(node.expression)) {
        reportBuiltinObject(node.expression);
      }
    } else if ((ts.isPrefixUnaryExpression(node)
        || ts.isPostfixUnaryExpression(node))
        && new Set([
          ts.SyntaxKind.PlusPlusToken,
          ts.SyntaxKind.MinusMinusToken,
          ts.SyntaxKind.DeleteKeyword,
        ]).has(node.operator)) {
      if (writesAlias(node.operand)) report(node.operand);
      else if (writesBuiltinPrototype(node.operand)) {
        reportBuiltinPrototype(node.operand);
      } else if (writesBuiltinObject(node.operand)) {
        reportBuiltinObject(node.operand);
      }
    } else if (ts.isCallExpression(node)
        && (ts.isPropertyAccessExpression(node.expression)
          || ts.isElementAccessExpression(node.expression))) {
      const receiver = node.expression.expression;
      const operation = staticMemberName(node.expression);
      const firstArgument = node.arguments[0];
      const mutatesFirstArgument = (
        (isUnshadowedNamedGlobal(receiver, new Set(["Object"]))
          && new Set([
            "assign",
            "defineProperty",
            "defineProperties",
            "setPrototypeOf",
            "freeze",
            "seal",
            "preventExtensions",
          ]).has(operation))
        || (isUnshadowedNamedGlobal(receiver, new Set(["Reflect"]))
          && new Set([
            "set",
            "deleteProperty",
            "defineProperty",
            "setPrototypeOf",
          ]).has(operation))
      );
      if (mutatesFirstArgument && firstArgument) {
        if (writesAlias(firstArgument)) report(firstArgument);
        else if (writesBuiltinPrototype(firstArgument)) {
          reportBuiltinPrototype(firstArgument);
        } else if (writesBuiltinObject(firstArgument)
            || isBuiltinObjectSource(firstArgument)) {
          reportBuiltinObject(firstArgument);
        }
      }
    }
    visitChildren(ts, node, visit);
  }
  visit(sourceFile);
  return findings;
}

function auditBaseLibHostIo(ts, sourceFile, checker, project, policy, target) {
  const owner = ownerFor(ts, sourceFile.fileName, policy);
  if (!owner || owner.kind !== "base_lib") return [];
  const targetGlobals = target === "browser"
    ? new Set([
      "fetch", "XMLHttpRequest", "WebSocket", "EventSource", "document",
      "window", "self", "globalThis", "localStorage", "sessionStorage",
      "indexedDB", "caches", "navigator", "location",
    ])
    : new Set(["process", "global", "globalThis", "fetch", "WebSocket"]);
  const nondeterministicGlobals = new Set([
    "Date",
    "performance",
    "crypto",
    "webcrypto",
    "process",
  ]);
  const mathGlobals = new Set(["Math"]);
  const findings = [];

  function hasLocalImplementation(node) {
    const symbol = checker.getSymbolAtLocation(node);
    return symbolDeclarationNodes(symbol, project).some((declaration) => {
      const declarationFile = declaration.getSourceFile();
      return !declarationFile.isDeclarationFile
        && normalizedRealPath(ts, declarationFile.fileName)
          === normalizedRealPath(ts, sourceFile.fileName);
    });
  }

  function isUnshadowedGlobal(node, names) {
    return ts.isIdentifier(node)
      && names.has(node.text)
      && !hasLocalImplementation(node);
  }

  function memberName(node) {
    if (ts.isPropertyAccessExpression(node)) return node.name.text;
    if (!ts.isElementAccessExpression(node)) return null;
    const argument = unwrapExpression(ts, node.argumentExpression);
    return argument && isStringLiteralLike(ts, argument) ? argument.text : null;
  }

  function directMemberAccess(root) {
    let current = root;
    while (current.parent
        && unwrapExpression(ts, current.parent) === unwrapExpression(ts, current)) {
      current = current.parent;
    }
    const parent = current.parent;
    if (!parent
        || (!ts.isPropertyAccessExpression(parent)
          && !ts.isElementAccessExpression(parent))) return null;
    return unwrapExpression(ts, parent.expression) === unwrapExpression(ts, current)
      ? parent
      : null;
  }

  function reportHostGlobal(node, name) {
    findings.push(importFinding(
      sourceFile,
      node,
      "VF_BASE_LIB_HOST_IO",
      `base_lib '${owner.id}' cannot access host global '${name}'; use a Capability`,
    ));
  }

  function reportNondeterminism(node, effect) {
    findings.push(importFinding(
      sourceFile,
      node,
      "VF_BASE_LIB_HOST_IO",
      `base_lib '${owner.id}' cannot access nondeterministic host primitive '${effect}'; obtain it in a node through a Capability`,
    ));
  }

  function visit(node) {
    if (ts.isIdentifier(node) && identifierIsReference(ts, node)) {
      if (isUnshadowedGlobal(node, targetGlobals)) {
        reportHostGlobal(node, node.text);
      } else if (isUnshadowedGlobal(node, nondeterministicGlobals)) {
        reportNondeterminism(node, node.text);
      } else if (isUnshadowedGlobal(node, mathGlobals)) {
        const member = directMemberAccess(node);
        if (!member) {
          reportNondeterminism(node, "Math object escape");
        } else {
          const name = memberName(member);
          if (name === "random") reportNondeterminism(member, "Math.random");
          else if (name === null) {
            reportNondeterminism(member, "Math[computed]");
          }
        }
      }
    }
    visitChildren(ts, node, visit);
  }
  visit(sourceFile);
  return findings;
}

function identifierIsReference(ts, node) {
  const parent = node.parent;
  if (!parent) return true;
  if ((ts.isPropertyAccessExpression(parent) && parent.name === node)
      || (ts.isPropertyAssignment(parent) && parent.name === node)
      || (ts.isMethodDeclaration(parent) && parent.name === node)
      || (ts.isPropertyDeclaration(parent) && parent.name === node)
      || (ts.isVariableDeclaration(parent) && parent.name === node)
      || (isKind(ts, parent, "isParameter", "isParameterDeclaration", "Parameter") && parent.name === node)
      || ts.isImportSpecifier(parent)
      || ts.isExportSpecifier(parent)
      || ts.isBindingElement(parent)
      || isKind(ts, parent, "isPropertySignature", "isPropertySignatureDeclaration", "PropertySignature")
      || isKind(ts, parent, "isMethodSignature", "isMethodSignatureDeclaration", "MethodSignature")
      || (ts.isTypeQueryNode && ts.isTypeQueryNode(parent))
      || ts.isTypeReferenceNode(parent)) return false;
  return true;
}

function auditTargetGlobals(ts, sourceFile, checker, project, target) {
  const blocked = target === "browser"
    ? new Set([
      "process", "Buffer", "global", "require", "module", "__dirname",
      "__filename",
    ])
    : new Set([
      "document", "window", "self", "localStorage", "sessionStorage",
      "navigator", "location", "fetch", "XMLHttpRequest", "WebSocket",
      "EventSource", "indexedDB", "caches", "Worker", "SharedWorker",
    ]);
  const hostRoots = new Set(["globalThis", "window", "self", "global"]);
  const hostAliases = new Set();
  const findings = [];

  function symbolHasLocalImplementation(symbol) {
    return symbolDeclarationNodes(symbol, project).some(
      (declaration) => {
        const declarationFile = declaration.getSourceFile();
        return !declarationFile.isDeclarationFile
          && !declarationFile.fileName.includes(`${path.sep}node_modules${path.sep}`);
      },
    );
  }

  function unshadowedHostRoot(node) {
    if (!ts.isIdentifier(node) || !hostRoots.has(node.text)) return false;
    return !symbolHasLocalImplementation(checker.getSymbolAtLocation(node));
  }

  function propertyName(node) {
    if (ts.isPropertyAccessExpression(node)) return node.name.text;
    if (!ts.isElementAccessExpression(node)) return null;
    const argument = unwrapExpression(ts, node.argumentExpression);
    return argument && isStringLiteralLike(ts, argument) ? argument.text : null;
  }

  function isHostObject(node) {
    const value = unwrapExpression(ts, node);
    if (!value) return false;
    if (unshadowedHostRoot(value)) return true;
    if (ts.isIdentifier(value)) {
      return hostAliases.has(checker.getSymbolAtLocation(value));
    }
    if (ts.isPropertyAccessExpression(value) || ts.isElementAccessExpression(value)) {
      const name = propertyName(value);
      return Boolean(name && hostRoots.has(name) && isHostObject(value.expression));
    }
    return false;
  }

  let changed = true;
  while (changed) {
    changed = false;
    function collectAliases(node) {
      if ((ts.isVariableDeclaration(node)
          || isKind(ts, node, "isParameter", "isParameterDeclaration", "Parameter"))
          && ts.isIdentifier(node.name)
          && node.initializer
          && isHostObject(node.initializer)) {
        const symbol = checker.getSymbolAtLocation(node.name);
        if (symbol && !hostAliases.has(symbol)) {
          hostAliases.add(symbol);
          changed = true;
        }
      }
      visitChildren(ts, node, collectAliases);
    }
    collectAliases(sourceFile);
  }

  function report(node, name) {
    findings.push(importFinding(
      sourceFile,
      node,
      "VF_IMPORT_TARGET_GLOBAL",
      `${target} target cannot use host global '${name}' without an adapter`,
    ));
  }

  function outerRuntimeExpression(node) {
    let current = node;
    while (current.parent && unwrapExpression(ts, current.parent) === current) {
      current = current.parent;
    }
    return current;
  }

  function isStaticMemberBase(node) {
    const outer = outerRuntimeExpression(node);
    const parent = outer.parent;
    if (!parent
        || (!ts.isPropertyAccessExpression(parent)
          && !ts.isElementAccessExpression(parent))) return false;
    return unwrapExpression(ts, parent.expression) === unwrapExpression(ts, outer);
  }

  function inspectBindingPattern(node, initializer) {
    if (!ts.isObjectBindingPattern(node) || !isHostObject(initializer)) return;
    for (const element of node.elements) {
      if (element.dotDotDotToken) {
        report(element, "<computed>");
        continue;
      }
      const rawName = element.propertyName || element.name;
      const name = ts.isIdentifier(rawName) || isStringLiteralLike(ts, rawName)
        ? rawName.text
        : null;
      if (name === null) report(element, "<computed>");
      else if (blocked.has(name)) report(element, name);
    }
  }

  function visit(node) {
    if (ts.isIdentifier(node)
        && identifierIsReference(ts, node)
        && (unshadowedHostRoot(node)
          || hostAliases.has(checker.getSymbolAtLocation(node)))
        && !isStaticMemberBase(node)) {
      report(node, "<host-object-escape>");
    }
    if (ts.isIdentifier(node) && blocked.has(node.text) && identifierIsReference(ts, node)) {
      const symbol = checker.getSymbolAtLocation(node);
      if (!symbolHasLocalImplementation(symbol)) report(node, node.text);
    }
    if ((ts.isPropertyAccessExpression(node) || ts.isElementAccessExpression(node))
        && isHostObject(node.expression)) {
      const name = propertyName(node);
      if (name === null) report(node, "<computed>");
      else if (blocked.has(name)) report(node, name);
    }
    if ((ts.isPropertyAccessExpression(node) || ts.isElementAccessExpression(node))
        && isHostObject(node)
        && !isStaticMemberBase(node)) {
      report(node, "<host-object-escape>");
    }
    if ((ts.isVariableDeclaration(node)
        || isKind(ts, node, "isParameter", "isParameterDeclaration", "Parameter"))
        && node.initializer) {
      inspectBindingPattern(node.name, node.initializer);
    }
    visitChildren(ts, node, visit);
  }
  visit(sourceFile);
  return findings;
}

async function typecheck(ts, request, extraFiles = [], checkDiagnostics = true) {
  const files = [...new Set([...(request.typecheckFiles || []), ...extraFiles])]
    .map((item) => path.resolve(item));
  const findings = [];
  const jsonCompilerOptions = {
    allowJs: true,
    checkJs: true,
    noEmit: true,
    strict: true,
    noImplicitAny: true,
    noUncheckedIndexedAccess: true,
    exactOptionalPropertyTypes: true,
    skipLibCheck: true,
    target: "ES2022",
    module: "ESNext",
    moduleResolution: "Bundler",
    resolveJsonModule: true,
    allowImportingTsExtensions: true,
    lib: request.target === "browser"
      ? ["ES2022", "DOM", "DOM.Iterable"]
      : ["ES2022"],
  };
  let program;
  let checker;
  let project = null;
  let sourceFiles;
  let diagnostics = [];
  let dispose = () => {};
  if (ts.__native) {
    const configPath = path.join(
      path.dirname(request.workflowEntry),
      checkDiagnostics ? "tsconfig.vibeflow.json" : "tsconfig.vibeflow-closure.json",
    );
    await writeFile(configPath, JSON.stringify({
      compilerOptions: jsonCompilerOptions,
      files,
    }), "utf8");
    const api = new ts.API({ cwd: path.resolve(request.packageRoot) });
    let snapshot;
    try {
      snapshot = api.updateSnapshot({ openProjects: [configPath] });
      project = snapshot.getProject(configPath) || snapshot.getProjects()[0];
      if (!project) fail("VF_TYPESCRIPT", "TypeScript did not create a project for AOT validation");
      program = project.program;
      checker = project.checker;
      sourceFiles = program.getSourceFileNames()
        .map((fileName) => program.getSourceFile(fileName))
        .filter(Boolean);
      if (checkDiagnostics) {
        diagnostics = [
          ...program.getConfigFileParsingDiagnostics(),
          ...program.getProgramDiagnostics(),
          ...program.getGlobalDiagnostics(),
          ...program.getSyntacticDiagnostics(),
          ...program.getBindDiagnostics(),
          ...program.getSemanticDiagnostics(),
        ].map((item) => diagnosticText(ts, item));
      }
    } catch (cause) {
      try {
        snapshot?.dispose();
      } finally {
        api.close();
      }
      throw cause;
    }
    dispose = () => {
      try {
        snapshot.dispose();
      } finally {
        api.close();
      }
    };
  } else {
    const compilerOptions = {
      ...jsonCompilerOptions,
      target: ts.ScriptTarget.ES2022,
      module: ts.ModuleKind.ESNext,
      moduleResolution: ts.ModuleResolutionKind.Bundler,
      lib: request.target === "browser"
        ? ["lib.es2022.d.ts", "lib.dom.d.ts", "lib.dom.iterable.d.ts"]
        : ["lib.es2022.d.ts"],
    };
    program = ts.createProgram({ rootNames: files, options: compilerOptions });
    checker = program.getTypeChecker();
    sourceFiles = program.getSourceFiles();
    diagnostics = checkDiagnostics
      ? ts.getPreEmitDiagnostics(program).map((item) => diagnosticText(ts, item))
      : [];
  }
  const policy = normalizeImportPolicy(request.importPolicy);
  const rootFiles = new Set(files.map((item) => path.resolve(item)));
  try {
    for (const sourceFile of sourceFiles) {
      if (sourceFile.isDeclarationFile) continue;
      const owned = ownerFor(ts, sourceFile.fileName, policy);
      if (!owned && !rootFiles.has(path.resolve(sourceFile.fileName))) continue;
      findings.push(...auditParsedSource(
        ts,
        sourceFile,
        request.target,
        request.profile,
      ));
      findings.push(...auditImportOwnership(ts, sourceFile, checker, project, policy));
      findings.push(...auditTopLevelPurity(ts, sourceFile, policy));
      findings.push(...auditCompletionAndPromiseOwnership(
        ts,
        sourceFile,
        checker,
        policy,
      ));
      findings.push(...auditModuleRegExpState(ts, sourceFile, policy));
      findings.push(...auditModuleStateWrites(
        ts,
        sourceFile,
        checker,
        project,
        policy,
      ));
      const sourceOwner = ownerFor(ts, sourceFile.fileName, policy);
      if (sourceOwner?.kind !== "host_extension") {
        findings.push(...auditTargetGlobals(ts, sourceFile, checker, project, request.target));
      }
      findings.push(...auditBaseLibHostIo(
        ts,
        sourceFile,
        checker,
        project,
        policy,
        request.target,
      ));
    }
    if (findings.length) {
      fail("VF_IMPORT_POLICY", "JavaScript/TypeScript import policy failed", { diagnostics: findings });
    }
    if (diagnostics.length) {
      fail("VF_TYPESCRIPT", "TypeScript validation failed", { diagnostics });
    }
  } finally {
    dispose();
  }
}

const VIRTUAL_WORKFLOW_SPECIFIER = "vibeflow:workflow-entry";
const VIRTUAL_WORKFLOW_NAMESPACE = "vibeflow-generated";

function workflowVirtualPlugin(workflowEntry) {
  return {
    name: "vibeflow-workflow-virtual-entry",
    setup(build) {
      build.onResolve(
        { filter: /^(?:@vibeflow\/workflow|vibeflow:workflow-entry)$/ },
        () => ({
          path: "workflow-entry.mjs",
          namespace: VIRTUAL_WORKFLOW_NAMESPACE,
        }),
      );
      build.onLoad({
        filter: /^workflow-entry\.mjs$/,
        namespace: VIRTUAL_WORKFLOW_NAMESPACE,
      }, async () => ({
        contents: await readFile(workflowEntry, "utf8"),
        loader: "js",
        resolveDir: path.dirname(workflowEntry),
      }));
    },
  };
}

async function build(request, tools) {
  await typecheck(tools.typescript, request);
  const profile = request.profile;
  const common = {
    absWorkingDir: path.resolve(request.packageRoot),
    bundle: true,
    format: "esm",
    platform: request.target === "browser" ? "browser" : "node",
    target: ["es2022"],
    sourcemap: request.sourcemap === "none" ? false : request.sourcemap,
    sourcesContent: true,
    charset: "utf8",
    legalComments: "none",
    treeShaking: true,
    external: request.external || [],
    metafile: true,
    logLevel: "silent",
    write: true,
    plugins: [workflowVirtualPlugin(request.workflowEntry)],
  };
  let result;
  if (profile === "esm-module") {
    const entryKey = request.entryName.replace(/\.js$/i, "");
    result = await tools.esbuild.build({
      ...common,
      entryPoints: { [entryKey]: VIRTUAL_WORKFLOW_SPECIFIER },
      outdir: request.outDir,
      entryNames: "[name]",
      chunkNames: "chunks/[name]-[hash]",
      splitting: true,
    });
  } else if (profile === "single-esm") {
    result = await tools.esbuild.build({
      ...common,
      entryPoints: [VIRTUAL_WORKFLOW_SPECIFIER],
      outfile: path.join(request.outDir, request.entryName),
      splitting: false,
    });
  } else if (profile === "web-app") {
    result = await tools.esbuild.build({
      ...common,
      entryPoints: [request.appEntry],
      outfile: path.join(request.outDir, request.entryName),
      splitting: false,
    });
  } else {
    fail("VF_BUILD_PROFILE", `unsupported build profile '${profile}'`);
  }
  const closureFiles = Object.keys(result.metafile?.inputs || {})
    .map((item) => path.isAbsolute(item) ? item : path.resolve(request.packageRoot, item))
    .filter((item) => !item.startsWith("<")
      && !item.includes(`${path.sep}${VIRTUAL_WORKFLOW_NAMESPACE}:`));
  await typecheck(tools.typescript, request, closureFiles, false);
  return {
    outputs: Object.keys(result.metafile?.outputs || {}).sort(),
    inputs: Object.keys(result.metafile?.inputs || {}).sort(),
  };
}

async function main() {
  if (process.argv.length !== 3) {
    fail("VF_PROTOCOL", "usage: node toolchain_driver.mjs REQUEST.json");
  }
  const requestPath = path.resolve(process.argv[2]);
  const request = JSON.parse(await readFile(requestPath, "utf8"));
  const packageRoot = path.resolve(request.packageRoot);
  const tools = await packageTools(packageRoot);
  const probe = {
    node: process.versions.node,
    typescript: String(tools.typescript.version || ""),
    esbuild: String(tools.esbuild.version || ""),
  };
  if (request.command === "probe") return { ok: true, probe };
  if (request.command === "build") {
    return { ok: true, probe, build: await build(request, tools) };
  }
  fail("VF_PROTOCOL", `unknown driver command '${String(request.command)}'`);
}

try {
  const result = await main();
  process.stdout.write(JSON.stringify(result));
} catch (error) {
  process.stdout.write(JSON.stringify({
    ok: false,
    error: {
      code: error?.code || "VF_TOOLCHAIN_INTERNAL",
      message: error instanceof Error ? error.message : String(error),
      details: error?.details || {},
    },
  }));
  process.exitCode = 1;
}
