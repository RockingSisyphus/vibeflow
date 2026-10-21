import { createRequire, isBuiltin } from "node:module";
import { existsSync, realpathSync } from "node:fs";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import process from "node:process";
import { pathToFileURL } from "node:url";

import {sdkPlugin, sdkTypes} from "./sdk_loader.mjs";
import {AnalysisSession,analysisProgram} from "./analysis_program.mjs";
import {ownershipImportStatements} from "./source_ownership.mjs";
import readline from "node:readline";
let analysisSession=null;

function fail(code, message, details = {}) {
  const error = new Error(message);
  error.code = code;
  error.details = details;
  throw error;
}

function visitChildren(ts, node, visitor) {
  if (node.implementationStatements) {
    for (const statement of node.implementationStatements) visitor(statement);
    return;
  }
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

async function packageTools(packageRoot, { requireEsbuild = true } = {}) {
  const packageJson = path.join(packageRoot, "package.json");
  const require = createRequire(packageJson);
  let typescript;
  let esbuild = null;
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
  if (requireEsbuild) {
    try {
      esbuild = require("esbuild");
    } catch (cause) {
      fail("VF_TOOLCHAIN_MISSING", "project-local package 'esbuild' cannot be resolved", {
        packageRoot,
        cause: String(cause),
      });
    }
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

function auditParsedSource(ts, sourceFile, profile) {
  const findings = [];
  function visit(node) {
    if (ts.isCallExpression(node)) {
      const dynamicImport = node.expression.kind === ts.SyntaxKind.ImportKeyword;
      const requireCall = ts.isIdentifier(node.expression) && node.expression.text === "require";
      if (dynamicImport || requireCall) {
        const argument = node.arguments[0];
        if (!argument || !isStringLiteralLike(ts, argument)) {
          findings.push(importFinding(
            sourceFile,
            node,
            "VF_IMPORT_DYNAMIC",
            `${dynamicImport ? "dynamic import" : "require"} must use a static string literal`,
          ));
        }
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

function normalizeImportPolicy(raw, packageRoot) {
  const policy = raw && typeof raw === "object" ? raw : {};
  const normalizeOwners = values => Array.isArray(values)
    ? values
      .filter((item) => item && typeof item === "object" && item.path && item.kind && item.id)
      .map((item) => ({
        path: path.resolve(item.path),
        realPath: path.resolve(item.path),
        pluginId: String(item.pluginId || ""),
        packagePath: item.packagePath ? path.resolve(item.packagePath) : "",
        kind: String(item.kind),
        id: String(item.id),
        export: String(item.export ?? "run"),
        role: String(item.role || "entry"),
        completion: String(item.completion || "immediate"),
        flowKind: String(item.flowKind || item.flow_kind || ""),
      }))
      .sort((left, right) => right.path.length - left.path.length)
    : [];
  const owners = normalizeOwners(policy.owners);
  return {
    owners,
    knownOwners: normalizeOwners(policy.knownOwners),
    packageRoot: normalizedRealPath({ sys: null }, packageRoot),
    sourceRoots: (policy.sourceRoots || []).map(value => normalizedRealPath({ sys: null }, value)),
    derivedOwners: new Map(),
    resourceBaseLibs: policy.resourceBaseLibs || {},
    pluginContributions: policy.pluginContributions || {},
    nodeBaseLibs: policy.nodeBaseLibs && typeof policy.nodeBaseLibs === "object"
      ? policy.nodeBaseLibs : {},
    baseLibDependencies: policy.baseLibDependencies && typeof policy.baseLibDependencies === "object"
      ? policy.baseLibDependencies : {},
    pluginDependencies:
      policy.pluginDependencies
      && typeof policy.pluginDependencies === "object"
        ? policy.pluginDependencies : {},
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

function directOwnerFor(ts, fileName, policy, preferred = null) {
  const candidate = normalizedRealPath(ts, fileName);
  if (preferred) {
    const same = policy.owners.find(owner => owner.kind === preferred.kind
      && owner.id === preferred.id
      && candidate === normalizedRealPath(ts, owner.path));
    if (same) return same;
  }
  for (const owner of policy.owners) {
    const ownerPath = normalizedRealPath(ts, owner.path);
    if (candidate === ownerPath || candidate.startsWith(`${ownerPath}${path.sep}`)) {
      return owner;
    }
  }
  return null;
}

function ownerFor(ts, fileName, policy) {
  const direct = directOwnerFor(ts, fileName, policy);
  if (direct) return direct;
  return policy.derivedOwners.get(normalizedRealPath(ts, fileName)) || null;
}

function importDestinationOwner(ts, fileName, policy, sourceOwner, imported) {
  const candidate = normalizedRealPath(ts, fileName);
  let owners = [...policy.owners, ...policy.knownOwners].filter(owner => candidate === normalizedRealPath(ts, owner.path));
  const bindings = imported.declaration?.importClause?.namedBindings;
  const names = imported.importedName ? new Set([imported.importedName]) : bindings && ts.isNamedImports(bindings)
    ? new Set(bindings.elements.map(item => (item.propertyName || item.name).text)) : new Set();
  const named = owners.filter(owner => names.has(String(owner.export || "").split(".")[0]));
  if (named.length) owners = named;
  const same = owners.find(owner => owner.kind === sourceOwner.kind && owner.id === sourceOwner.id);
  if (same) return same;
  const libraries = sourceOwner.kind === "node" ? policy.nodeBaseLibs[sourceOwner.id] || []
    : sourceOwner.kind === "base_lib" ? policy.baseLibDependencies[sourceOwner.id] || []
    : policy.resourceBaseLibs[`${sourceOwner.kind}:${sourceOwner.id}`] || [];
  const library = owners.find(owner => owner.kind === "base_lib" && libraries.includes(owner.id));
  return library || owners[0] || directOwnerFor(ts, fileName, policy, sourceOwner);
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

function resolvedImportFile(ts, checker, project, imported, sourceFileName) {
  if (isBuiltin(imported.value)) return "";
  const symbol = checker.getSymbolAtLocation(imported.node);
  const declaration = symbolDeclarationNodes(symbol, project)[0];
  return declaration?.getSourceFile?.().fileName
    || fallbackResolveSpecifier(imported.value, sourceFileName);
}

function deriveTransitiveOwners(ts, sourceFiles, checker, project, policy) {
  const available = new Map(
    sourceFiles
      .filter((sourceFile) => !sourceFile.isDeclarationFile)
      .map((sourceFile) => [
        normalizedRealPath(ts, sourceFile.fileName),
        sourceFile,
      ]),
  );
  let changed = true;
  while (changed) {
    changed = false;
    for (const [sourcePath, sourceFile] of available) {
      const sourceOwner = directOwnerFor(ts, sourcePath, policy)
        || policy.derivedOwners.get(sourcePath);
      if (!sourceOwner) continue;
      for (const imported of importSpecifiers(ts, sourceFile)) {
        const resolved = resolvedImportFile(
          ts,
          checker,
          project,
          imported,
          sourceFile.fileName,
        );
        if (!resolved) continue;
        const destinationPath = normalizedRealPath(ts, resolved);
        if (!available.has(destinationPath)
            || directOwnerFor(ts, destinationPath, policy)
            || policy.derivedOwners.has(destinationPath)) continue;
        policy.derivedOwners.set(destinationPath, sourceOwner);
        changed = true;
      }
    }
  }
}

function isWithinPath(root, candidate) {
  return candidate === root || candidate.startsWith(`${root}${path.sep}`);
}

function auditImportOwnership(ts, sourceFile, checker, project, policy) {
  const sourceOwner = ownerFor(ts, sourceFile.fileName, policy);
  if (!sourceOwner
      || !["node", "base_lib", "plugin", "plugin_declaration"].includes(sourceOwner.kind)) return [];
  const findings = [];
  const imports = importSpecifiers(ts, sourceFile).flatMap(imported => {
    const bindings = imported.declaration?.importClause?.namedBindings;
    return bindings && ts.isNamedImports(bindings) && bindings.elements.length
      ? bindings.elements.map(item => ({...imported, importedName: (item.propertyName || item.name).text})) : [imported];
  });
  for (const imported of imports) {
    const specifier = imported.value;
    // Explicit Node builtin imports are platform facts.  esbuild decides
    // whether the selected build target can resolve them; they do not affect
    // VibeFlow ownership between nodes/base_lib/plugins/extensions.
    if (isBuiltin(specifier) || specifier === "@vibeflow/plugin") continue;
    const bare = !specifier.startsWith(".") && !path.isAbsolute(specifier);
    const resolvedFileName = resolvedImportFile(
      ts,
      checker,
      project,
      imported,
      sourceFile.fileName,
    );
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
    if (![policy.packageRoot, ...policy.sourceRoots].some(root => isWithinPath(root, resolvedFile))) {
      findings.push(importFinding(
        sourceFile,
        imported.node,
        "VF_IMPORT_PACKAGE_ROOT",
        `${sourceOwner.kind} '${sourceOwner.id}' imports source outside package_root: '${resolvedFile}'`,
      ));
      continue;
    }
    // Package ownership is already validated at loading. Private support code
    // is part of that atomic Plugin, rather than a separate business resource.
    if (sourceOwner.pluginId && sourceOwner.packagePath && isWithinPath(sourceOwner.packagePath, resolvedFile)) continue;
    const destination = importDestinationOwner(ts, resolvedFile, policy, sourceOwner, imported);
    if (!destination) {
      findings.push(importFinding(
        sourceFile,
        imported.node,
        "VF_IMPORT_OWNER",
        `${sourceOwner.kind} '${sourceOwner.id}' imports unowned local source '${resolvedFile}'`,
      ));
      continue;
    }
    if (sourceOwner.kind === "plugin_declaration") {
      const contributed = policy.pluginContributions[sourceOwner.id] || [];
      if (destination.kind === "plugin_declaration" && destination.id === sourceOwner.id
          || contributed.some(item => item.kind === destination.kind && item.id === destination.id)
          || destination.kind === "base_lib" && (policy.resourceBaseLibs[`plugin_declaration:${sourceOwner.id}`] || []).includes(destination.id)) continue;
      findings.push(importFinding(sourceFile, imported.node, "VF_IMPORT_LAYER", `plugin declaration '${sourceOwner.id}' imports a resource outside its contributions`));
    } else if (sourceOwner.kind === "node") {
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
      } else if (["plugin", "plugin_declaration"].includes(destination.kind)) {
        findings.push(importFinding(
          sourceFile,
          imported.node,
          "VF_IMPORT_LAYER",
          `node '${sourceOwner.id}' cannot import ${destination.kind} '${destination.id}'`,
        ));
      }
    } else if (sourceOwner.kind === "base_lib") {
      if (["node", "plugin", "plugin_declaration"].includes(destination.kind)) {
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
    } else if (sourceOwner.kind === "plugin") {
      if (destination.kind === "base_lib" && (policy.resourceBaseLibs[`plugin:${sourceOwner.id}`] || []).includes(destination.id)) continue;
      if (destination.kind !== "plugin") {
        findings.push(importFinding(
          sourceFile,
          imported.node,
          "VF_PLUGIN_IMPORT_POLICY",
          `plugin '${sourceOwner.id}' cannot import ${destination.kind} '${destination.id}'`,
        ));
      } else if (destination.id !== sourceOwner.id) {
        const allowed = new Set(policy.pluginDependencies[sourceOwner.id] || []);
        if (!allowed.has(destination.id)) {
          findings.push(importFinding(
            sourceFile,
            imported.node,
            "VF_PLUGIN_IMPORT_POLICY",
            `plugin '${sourceOwner.id}' imports undeclared plugin dependency '${destination.id}'`,
          ));
        }
      }
    }
  }
  return findings;
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

function isStateInitializer(ts, node) {
  const value = unwrapExpression(ts, node);
  if (!value) return true;
  if (ts.isArrayLiteralExpression(value)) {
    return value.elements.every(item => !ts.isSpreadElement(item) && isStateInitializer(ts, item));
  }
  if (ts.isObjectLiteralExpression(value)) {
    return value.properties.every(item => !hasComputedPropertyName(ts, item)
      && (ts.isPropertyAssignment(item) && isStateInitializer(ts, item.initializer)
          || ts.isMethodDeclaration(item) || ts.isGetAccessorDeclaration(item) || ts.isSetAccessorDeclaration(item)));
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

function isSdkDeclaration(ts, sourceFile, value) {
  if (!value || !ts.isCallExpression(value)) return false;
  const expression = value.expression, imports = new Map();
  for (const statement of sourceFile.statements) {
    if (statement.moduleSpecifier?.text !== "@vibeflow/plugin") continue;
    const bindings = statement.importClause?.namedBindings;
    if (bindings?.elements) for (const item of bindings.elements) imports.set(item.name.text, (item.propertyName || item.name).text);
    else if (bindings?.name) imports.set(bindings.name.text, "*");
  }
  const names = new Set(["defineNode", "defineNodeType", "defineRule", "defineRuleset", "definePlugin", "defineDataSchema", "defineBaseLib", "defineCapability", "defineResource"]);
  const identified = names.has(imports.get(expression.text)) ||
    (imports.get(expression.expression?.text) === "*" && names.has(expression.name?.text));
  // Constructor arguments remain ordinary expressions. Inline implementations
  // are declarations; calls inside their bodies are checked by their own Rules.
  function data(argument) {
    if (ts.isIdentifier(argument) || ts.isFunctionExpression(argument) || ts.isArrowFunction(argument)) return true;
    if (ts.isArrayLiteralExpression(argument)) return argument.elements.every(data);
    if (ts.isObjectLiteralExpression(argument)) return argument.properties.every(item =>
      ts.isMethodDeclaration(item) || ts.isShorthandPropertyAssignment(item)
      || (ts.isSpreadAssignment(item) && data(item.expression))
      || (ts.isPropertyAssignment(item) && data(item.initializer)));
    return isPureInitializer(ts, argument);
  }
  return identified && value.arguments.every(data);
}

function auditTopLevelPurity(ts, sourceFile, policy, ruleParams = {}) {
  const owner = ownerFor(ts, sourceFile.fileName, policy);
  if (!owner
      || !["node", "base_lib", "plugin", "plugin_declaration"].includes(owner.kind)) return [];
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
      allowed = (immutable || ruleParams.effect_scope === "global_state") && statement.declarationList.declarations.every(
        (declaration) => isSdkDeclaration(ts, sourceFile, declaration.initializer)
          || isImmutableModuleInitializer(ts, declaration.initializer)
          || ruleParams.effect_scope === "global_state" && isStateInitializer(ts, declaration.initializer),
      );
    } else if (ts.isExportAssignment(statement)) {
      allowed = isImmutableModuleInitializer(ts, statement.expression)
        || ruleParams.effect_scope === "global_state" && isStateInitializer(ts, statement.expression);
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

function implementationDeclaration(ts, sourceFile, exportName, seen = new Set()) {
  if (seen.has(exportName)) return null;
  seen.add(exportName);
  const [name, member] = exportName.split(".");
  for (const statement of sourceFile.statements) {
    if (ts.isFunctionDeclaration(statement) && statement.name?.text === name && !member) return statement;
    if (!ts.isVariableStatement(statement)) continue;
    for (const declaration of statement.declarationList.declarations) {
      if (!ts.isIdentifier(declaration.name) || declaration.name.text !== name || !declaration.initializer) continue;
      let value = declaration.initializer;
      if (member && ts.isCallExpression(value)) {
        const property = declarationProperty(ts, sourceFile, value.arguments[0], member);
        if (property && ts.isShorthandPropertyAssignment(property)) return implementationDeclaration(ts, sourceFile, member, seen);
        value = property?.initializer || property;
      }
      if (value && ts.isIdentifier(value) && value.text !== name) return implementationDeclaration(ts, sourceFile, value.text, seen);
      if (value && ts.isPropertyAccessExpression(value)) return implementationDeclaration(ts, sourceFile, value.getText(sourceFile), seen);
      if (value && (ts.isArrowFunction(value) || ts.isFunctionExpression(value) || ts.isMethodDeclaration(value))) return value;
    }
  }
  return null;
}

function declarationProperty(ts, sourceFile, expression, member, seen = new Set()) {
  if (!expression || seen.has(expression)) return null;
  seen.add(expression);
  if (ts.isIdentifier(expression)) {
    for (const statement of sourceFile.statements) {
      for (const declaration of statement.declarationList?.declarations || []) {
        if (declaration.name?.text === expression.text) return declarationProperty(ts, sourceFile, declaration.initializer, member, seen);
      }
    }
  }
  if (expression.expression && !ts.isCallExpression(expression)) return declarationProperty(ts, sourceFile, expression.expression, member, seen);
  if (ts.isCallExpression(expression)) return declarationProperty(ts, sourceFile, expression.arguments[0], member, seen);
  for (const property of [...(expression.properties || [])].reverse()) {
    if ((property.name?.text || property.name?.getText(sourceFile)) === member) return property;
    if (ts.isSpreadAssignment(property)) {
      const found = declarationProperty(ts, sourceFile, property.expression, member, seen);
      if (found) return found;
    }
  }
  return null;
}

function callableReturnType(ts, checker, declaration) {
  try {
    const location = declaration.name || declaration;
    const type = checker.getTypeAtLocation(location);
    const signatures = checker.getSignaturesOfType(type, ts.SignatureKind.Call);
    const signature = signatures[0];
    if (!signature) return { type: null, text: "" };
    const returnType = typeof checker.getReturnTypeOfSignature === "function"
      ? checker.getReturnTypeOfSignature(signature)
      : signature.getReturnType();
    return { type: returnType, text: checker.typeToString(returnType) };
  } catch {
    return {
      type: null,
      text: declaration.type?.getText?.() || "",
    };
  }
}

function promiseLikeTypeText(value) {
  const alternatives = String(value || "")
    .split("|")
    .map((item) => item.trim().replace(/^\((.*)\)$/s, "$1").trim());
  return alternatives.some(
    (item) => /^(?:Promise|PromiseLike)\s*</.test(item),
  );
}

function promiseLikeType(ts, checker, type, fallbackText = "") {
  if (type) {
    const members = Array.isArray(type.types) ? type.types : [];
    if (members.length
        && members.some((member) => promiseLikeType(ts, checker, member))) {
      return true;
    }
    try {
      if (typeof checker.getPromisedTypeOfPromise === "function"
          && checker.getPromisedTypeOfPromise(type)) {
        return true;
      }
    } catch {
      // Structural thenable detection and the textual fallback remain.
    }
    try {
      if (checker.getPropertyOfType(type, "then")) return true;
    } catch {
      // The textual fallback supports TypeScript API variants that do not
      // expose property lookup for this type.
    }
  }
  return promiseLikeTypeText(fallbackText);
}

function auditCompletionAndPromiseOwnership(ts, sourceFile, checker, policy, project) {
  const owner = ownerFor(ts, sourceFile.fileName, policy);
  if (!owner || owner.role === "support" || !["node", "plugin"].includes(owner.kind)) return [];
  const declaration = implementationDeclaration(ts, sourceFile, owner.export);
  if (!declaration) return [];
  const findings = [];
  const completion = owner.completion || "immediate";
  const subject = owner.kind === "plugin" ? `plugin '${owner.id}' factory` : `node '${owner.id}'`;
  const declaredAsync = hasModifier(ts, declaration, ts.SyntaxKind.AsyncKeyword);
  const callableReturn = callableReturnType(ts, checker, declaration);
  const returnType = callableReturn.text;
  const returnsPromise = promiseLikeType(
    ts,
    checker,
    callableReturn.type,
    returnType,
  );
  if (completion === "immediate" && (declaredAsync || returnsPromise)) {
    findings.push(importFinding(
      sourceFile,
      declaration,
      "VF_COMPLETION_IMMEDIATE_PROMISE",
      `${subject} declares immediate completion but '${owner.export}' is async or returns ${returnType || "a Promise"}`,
    ));
  }
  if (owner.kind !== "plugin"
      && completion === "suspend" && !declaredAsync && !returnsPromise) {
    findings.push(importFinding(
      sourceFile,
      declaration,
      "VF_COMPLETION_SUSPEND_NON_PROMISE",
      `${subject} declares suspend completion but '${owner.export}' does not return a Promise`,
    ));
  }
  if (owner.kind === "plugin") {
    if (declaredAsync || returnsPromise) {
      findings.push(importFinding(
        sourceFile,
        declaration,
        "VF_PLUGIN_FACTORY",
        `plugin '${owner.id}' createPlugin factory must be synchronous`,
      ));
    }
    function pluginVisit(node) {
      if (node !== declaration
          && (ts.isFunctionDeclaration(node)
            || ts.isFunctionExpression(node)
            || ts.isArrowFunction(node)
            || ts.isMethodDeclaration(node))) {
        const asyncHook = hasModifier(ts, node, ts.SyntaxKind.AsyncKeyword);
        const hookReturn = callableReturnType(ts, checker, node);
        const hookReturnsPromise = promiseLikeType(
          ts,
          checker,
          hookReturn.type,
          hookReturn.text,
        );
        if (completion === "immediate" && (asyncHook || hookReturnsPromise)) {
          findings.push(importFinding(
            sourceFile,
            node,
            "VF_COMPLETION_IMMEDIATE_PROMISE",
            `immediate plugin '${owner.id}' cannot declare Promise-returning hooks`,
          ));
        }
      }
      if (ts.isCallExpression(node)) {
        const expression = node.expression;
        const name = ts.isIdentifier(expression)
          ? expression.text
          : ts.isPropertyAccessExpression(expression)
            ? expression.name.text
            : "";
        if (new Set([
          "addEventListener", "eventOn", "on", "once", "setInterval", "setTimeout",
        ]).has(name)) {
          findings.push(importFinding(
            sourceFile,
            node,
            "VF_PLUGIN_LONG_LIVED_LISTENER",
            `runtime plugin '${owner.id}' cannot register long-lived listeners or timers; express the resource lifecycle in explicit workflow nodes`,
          ));
        }
        const promiseChain = ts.isPropertyAccessExpression(expression)
          && new Set(["then", "catch", "finally"]).has(expression.name.text);
        if (promiseChain && ts.isExpressionStatement(node.parent)) {
          findings.push(importFinding(
            sourceFile,
            node,
            "VF_PLUGIN_PROMISE_UNOWNED",
            `plugin '${owner.id}' cannot discard Promise work`,
          ));
        }
      }
      if (ts.isVoidExpression(node)) {
        let discardedPromise = false;
        try {
          const expressionType = checker.getTypeAtLocation(node.expression);
          discardedPromise = promiseLikeType(
            ts,
            checker,
            expressionType,
            checker.typeToString(expressionType),
          );
        } catch {
          // Retain syntax-based checks when the checker cannot prove the type.
        }
        if (discardedPromise) {
          findings.push(importFinding(
            sourceFile,
            node,
            "VF_PLUGIN_PROMISE_UNOWNED",
            `plugin '${owner.id}' cannot discard Promise work with void`,
          ));
        }
      }
      visitChildren(ts, node, pluginVisit);
    }
    pluginVisit(declaration);
    return findings;
  }

  function callName(node) {
    if (!ts.isCallExpression(node)) return "";
    const expression = node.expression;
    if (ts.isIdentifier(expression)) return expression.text;
    if (ts.isPropertyAccessExpression(expression)) return expression.name.text;
    return "";
  }

  function nativeTimerName(expression, seen = new Set()) {
    if (!expression || seen.has(expression)) return "";
    seen.add(expression);
    let symbol=checker.getSymbolAtLocation(ts.isPropertyAccessExpression(expression) ? expression.name : expression);
    if(symbol && (symbol.flags & ts.SymbolFlags.Alias))symbol=checker.getAliasedSymbol(symbol);
    for (const item of symbolDeclarationNodes(symbol,project)) {
      const file=item.getSourceFile().fileName.replaceAll("\\", "/");
      if (/\/lib\.[^/]+\.d\.ts$/.test(file) || file.includes("/node_modules/@types/node/")) {
        return item.name?.text || "";
      }
      if ((ts.isVariableDeclaration(item) || ts.isPropertyAssignment(item)) && item.initializer) {
        const original=nativeTimerName(unwrapExpression(ts,item.initializer),seen);
        if(original)return original;
      }
    }
    return "";
  }
  function timerClearedInFinally(call, clearName) {
    const assignment=call.parent;
    const variable=ts.isVariableDeclaration(assignment) ? assignment.name :
      ts.isBinaryExpression(assignment) && assignment.operatorToken.kind===ts.SyntaxKind.EqualsToken ? assignment.left : null;
    if(!variable)return false;
    function sameHandle(left,right) {
      left=unwrapExpression(ts,left);right=unwrapExpression(ts,right);
      if(!left || !right)return false;
      if(ts.isIdentifier(left) && ts.isIdentifier(right))return checker.getSymbolAtLocation(left)===checker.getSymbolAtLocation(right);
      if(ts.isPropertyAccessExpression(left) && ts.isPropertyAccessExpression(right))
        return left.name.text===right.name.text && sameHandle(left.expression,right.expression);
      return left.kind===ts.SyntaxKind.ThisKeyword && right.kind===ts.SyntaxKind.ThisKeyword;
    }
    let cleared = false;
    function scan(node, inFinally = false) {
      if (ts.isTryStatement(node)) {
        if (node.finallyBlock) scan(node.finallyBlock, true);
        scan(node.tryBlock, inFinally);
        if (node.catchClause) scan(node.catchClause, inFinally);
        return;
      }
      if (inFinally && ts.isCallExpression(node) && nativeTimerName(node.expression) === clearName
          && node.arguments.length > 0 && sameHandle(node.arguments[0],variable)) cleared = true;
      visitChildren(ts, node, child=>scan(child,inFinally));
    }
    scan(declaration);
    return cleared;
  }
  const contextParameter = declaration.parameters?.[2]?.name;
  const contextSymbol = contextParameter && checker.getSymbolAtLocation(contextParameter);
  function listenerReleased(call) {
    const receiver = ts.isPropertyAccessExpression(call.expression) ? call.expression.expression : null;
    // The invocation signal is aborted when this Node actually exits. A once
    // abort listener therefore belongs to the invocation, including success.
    if (receiver && ts.isPropertyAccessExpression(unwrapExpression(ts,receiver)) && unwrapExpression(ts,receiver).name.text === "signal"
        && checker.getSymbolAtLocation(unwrapExpression(ts,receiver).expression) === contextSymbol
        && call.arguments[0]?.text === "abort"
        && call.arguments[2]?.getText(sourceFile).match(/once\s*:\s*true/)) return true;
    let released = false;
    const same = (left, right) => left && right && left.getText(sourceFile) === right.getText(sourceFile);
    function scan(item, inFinally = false) {
      if (ts.isTryStatement(item)) {
        if (item.finallyBlock) scan(item.finallyBlock, true);
        scan(item.tryBlock, inFinally);
        if (item.catchClause) scan(item.catchClause, inFinally);
        return;
      }
      if (inFinally && ts.isCallExpression(item)
          && ["removeEventListener", "off", "removeListener"].includes(nativeTimerName(item.expression))
          && (receiver ? ts.isPropertyAccessExpression(item.expression) && same(item.expression.expression, receiver) : ts.isIdentifier(item.expression))
          && same(item.arguments[0], call.arguments[0])
          && same(item.arguments[1], call.arguments[1])) released = true;
      visitChildren(ts, item, child => scan(child, inFinally));
    }
    scan(declaration);
    return released;
  }
  function auditPromiseResources(creation) {
    if(nativeTimerName(creation.expression)!=='Promise')return;
    const executor=creation.arguments?.[0];
    if(!executor || !(ts.isArrowFunction(executor)||ts.isFunctionExpression(executor)))return;
    const owned=ts.isAwaitExpression(creation.parent)||ts.isReturnStatement(creation.parent);
    function scan(item) {
      if(item!==executor && (ts.isArrowFunction(item)||ts.isFunctionExpression(item)||ts.isFunctionDeclaration(item)))return;
      if(ts.isCallExpression(item)) {
        const resource=nativeTimerName(item.expression);
        if(resource==='setInterval' || resource==='setTimeout' && !owned) {
          if(!timerClearedInFinally(item,resource==='setTimeout'?'clearTimeout':'clearInterval'))
            findings.push(importFinding(sourceFile,item,'VF_NODE_RESOURCE_UNOWNED',`node '${owner.id}' must own and release its timer`));
        }
        if(['addEventListener','on','once','addListener'].includes(resource) && !listenerReleased(item))
          findings.push(importFinding(sourceFile,item,'VF_NODE_RESOURCE_UNOWNED',`node '${owner.id}' must release its event listener in finally`));
      }
      visitChildren(ts,item,scan);
    }
    scan(executor);
  }
  function visit(node) {
    if (ts.isPropertyAccessExpression(node) && node.name.text === "tasks"
        && contextSymbol
        && checker.getSymbolAtLocation(node.expression) === contextSymbol) {
      findings.push(importFinding(sourceFile, node, "VF_TASK_CONTROL_FORBIDDEN",
        `node '${owner.id}' must use explicit graph edges; task controllers were removed`));
    }
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
        const expressionType = checker.getTypeAtLocation(node.expression);
        discardedPromise = promiseLikeType(
          ts,
          checker,
          expressionType,
          checker.typeToString(expressionType),
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
      const timer = nativeTimerName(node.expression);
      if (["addEventListener", "on", "once", "addListener"].includes(timer) && !listenerReleased(node)) {
        findings.push(importFinding(sourceFile, node, "VF_NODE_RESOURCE_UNOWNED",
          `node '${owner.id}' must release its event listener in finally`));
      }
      if (["setTimeout", "setInterval"].includes(timer)
          && !timerClearedInFinally(node, timer === "setTimeout" ? "clearTimeout" : "clearInterval")) {
        findings.push(importFinding(sourceFile, node, "VF_NODE_RESOURCE_UNOWNED",
          `node '${owner.id}' must await its timer or release its handle in finally`));
      }
      let callReturnsPromise = false;
      try {
        const callType = checker.getTypeAtLocation(node);
        callReturnsPromise = promiseLikeType(
          ts,
          checker,
          callType,
          checker.typeToString(callType),
        );
      } catch {
        // The syntax checks below remain authoritative when a checker cannot
        // expose a type for this expression.
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
    if (ts.isNewExpression(node)) auditPromiseResources(node);
    if (completion !== "immediate" && ts.isNewExpression(node)
        && ts.isExpressionStatement(node.parent)) {
      const type = checker.getTypeAtLocation(node);
      if (promiseLikeType(ts, checker, type, checker.typeToString(type)))
        findings.push(importFinding(sourceFile,node,"VF_PROMISE_UNOWNED",
          `node '${owner.id}' cannot discard constructed Promise work`));
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

function implementationScope(ts, sourceFile, checker, project, policy, symbolOnly = false, selectedExport = "") {
  const owner = ownerFor(ts, sourceFile.fileName, policy);
  const exportName = selectedExport || owner?.export;
  if (!exportName || (!symbolOnly && !exportName.includes("."))) return sourceFile;
  const implementation = implementationDeclaration(ts, sourceFile, exportName);
  if (!implementation) return sourceFile;
  const moduleVariables = sourceFile.statements.filter(statement => ts.isVariableStatement(statement)
    && statement.declarationList.declarations.every(declaration => {
      const value = unwrapExpression(ts, declaration.initializer);
      return !value || (!isSdkDeclaration(ts, sourceFile, value)
        && !ts.isFunctionExpression(value) && !ts.isArrowFunction(value));
    }));
  const reachable = new Set([implementation]), pending = [implementation, ...moduleVariables], referencedImports = new Set(), importedNames = new Map();
  while (pending.length) {
    const current = pending.pop();
    function visit(node) {
      if (ts.isIdentifier(node) && identifierIsReference(ts, node)) {
        for (const declaration of symbolDeclarationNodes(checker.getSymbolAtLocation(node), project)) {
          if (declaration.getSourceFile() !== sourceFile) continue;
          let statement = declaration;
          while (statement.parent && statement.parent !== sourceFile) statement = statement.parent;
          if (ts.isImportDeclaration(statement) || ts.isImportEqualsDeclaration(statement)) {
            referencedImports.add(statement);
            const names = importedNames.get(statement) || new Set();
            if (ts.isImportSpecifier(declaration)) names.add((declaration.propertyName || declaration.name).text);
            else if (ts.isNamespaceImport(declaration)) {
              const access = node.parent;
              const name = ts.isPropertyAccessExpression(access) && access.expression === node ? access.name.text
                : ts.isElementAccessExpression(access) && access.expression === node && isStringLiteralLike(ts, access.argumentExpression)
                  ? access.argumentExpression.text : "*";
              names.add(name);
            } else if (ts.isImportClause(declaration)) names.add("default");
            else names.add("*");
            importedNames.set(statement, names);
          }
          let callable = declaration;
          if (ts.isVariableDeclaration(callable)) callable = unwrapExpression(ts, callable.initializer);
          if (!callable || ![ts.isFunctionDeclaration, ts.isFunctionExpression, ts.isArrowFunction, ts.isClassDeclaration].some(test => test(callable))) continue;
          if (!reachable.has(callable)) {reachable.add(callable); pending.push(callable);}
        }
      }
      visitChildren(ts, node, visit);
    }
    visit(current);
  }
  const globals = sourceFile.statements.filter(statement => {
    if (ts.isImportDeclaration(statement)) {
      const clause = statement.importClause;
      if (!clause) return true;
      return referencedImports.has(statement);
    }
    if (ts.isImportEqualsDeclaration(statement)) return referencedImports.has(statement);
    return moduleVariables.includes(statement);
  });
  // Preserve the original nodes and positions; only traversal is scoped to the
  // selected implementation and its local callable references.
  const statements = [...globals, ...reachable];
  return Object.create(sourceFile, {
    statements: {value: statements, enumerable: true},
    implementationStatements: {value: statements},
    implementationImportNames: {value: importedNames},
  });
}

function implementationEffectScopes(ts, sourceFiles, checker, project, policy, rootFiles) {
  const available = new Map(sourceFiles.map(file => [normalizedRealPath(ts, file.fileName), file]));
  const scopes = new Map(), seen = new Set(), pending = [];
  function enqueue(file, owner, exportName = "") {
    if (!file || file.isDeclarationFile || !owner) return;
    const key = JSON.stringify([normalizedRealPath(ts, file.fileName), owner.kind, owner.id, exportName || owner.export]);
    if (seen.has(key)) return;
    seen.add(key);
    pending.push({file, owner, exportName});
  }
  // Roots are this Rule subject's declared entry and explicit support files.
  // Its real helper calls retain these params; unrelated SDK factory imports do
  // not inherit them merely because they share the frozen declaration closure.
  for (const file of sourceFiles) {
    if (rootFiles.has(path.resolve(file.fileName))) enqueue(file, ownerFor(ts, file.fileName, policy));
  }
  while (pending.length) {
    const {file, owner, exportName} = pending.pop();
    const ownedPolicy = {...policy, owners: [owner, ...policy.owners.filter(item => item !== owner)]};
    const scope = implementationScope(ts, file, checker, project, ownedPolicy, true, exportName);
    const key = normalizedRealPath(ts, file.fileName);
    const entries = scopes.get(key) || [];
    entries.push({scope, policy: ownedPolicy});
    scopes.set(key, entries);
    for (const imported of importSpecifiers(ts, scope)) {
      if (imported.declaration?.importClause?.isTypeOnly) continue;
      const resolved = resolvedImportFile(ts, checker, project, imported, file.fileName);
      const destinationFile = available.get(normalizedRealPath(ts, resolved || ""));
      if (!destinationFile) continue;
      const bindings = imported.declaration?.importClause?.namedBindings;
      const selectedNames = scope.implementationImportNames?.get(imported.declaration);
      const imports = bindings && ts.isNamedImports(bindings)
        ? bindings.elements.filter(item => !item.isTypeOnly && (!selectedNames || selectedNames.has("*")
            || selectedNames.has((item.propertyName || item.name).text)))
          .map(item => ({...imported, importedName: (item.propertyName || item.name).text}))
        : [...(selectedNames || new Set(["*"]))].map(name => ({...imported, importedName: name}));
      for (const dependency of imports) {
        const destination = importDestinationOwner(ts, resolved, ownedPolicy, owner, dependency);
        const name = dependency.importedName;
        const selectedExport = name && destination?.export?.split(".")[0] !== name ? name : "";
        enqueue(destinationFile, destination, selectedExport);
      }
    }
  }
  return scopes;
}

function publicSourceViews(ts, sourceFiles, checker, project, policy, rootFiles, subjectId) {
  const selected = new Set(), pending = [], imports = new Set(), inherited = new Map();
  const available = new Set(sourceFiles.filter(file => !file.isDeclarationFile
    && !file.fileName.includes(`${path.sep}node_modules${path.sep}`)));
  function top(declaration) {
    let node = declaration;
    while (node.parent && node.parent.kind !== ts.SyntaxKind.SourceFile) node = node.parent;
    if (ts.isVariableStatement(node)) {
      let current = declaration;
      while (current.parent && current.parent !== node.declarationList) current = current.parent;
      if (ts.isVariableDeclaration(current)) return current;
    }
    return node;
  }
  function enqueue(declaration, implementation = false) {
    if (!declaration || declaration.kind === ts.SyntaxKind.SourceFile || !available.has(declaration.getSourceFile())) return;
    const statement = top(declaration), file = statement.getSourceFile();
    const names = [statement.name?.text];
    const owned = policy.owners.some(owner => owner.kind === "node" && owner.id === subjectId
      && path.resolve(owner.path) === path.resolve(file.fileName) && names.includes(owner.export?.split(".")[0]));
    const foreign = !owned && (policy.owners.some(owner => owner.kind === "node" && owner.id !== subjectId
        && path.resolve(owner.path) === path.resolve(file.fileName) && names.includes(owner.export?.split(".")[0]))
      || ts.isVariableDeclaration(statement) && isSdkDeclaration(ts, file, statement.initializer));
    if (foreign) {
      if (!implementation || !ts.isVariableDeclaration(statement) || !ts.isCallExpression(statement.initializer)) return;
      const object = statement.initializer.arguments[0];
      const property = object?.properties?.find(property => property === declaration || property.initializer === declaration);
      if (!property) return;
      const members = inherited.get(statement) || new Set();
      if (members.has(property)) return;
      members.add(property); inherited.set(statement, members);
      selected.add(statement); pending.push(property);
      return;
    }
    if (selected.has(statement)) return;
    selected.add(statement); pending.push(statement);
  }
  for (const file of sourceFiles) {
    if (!rootFiles.has(path.resolve(file.fileName))) continue;
    const owners = policy.owners.filter(owner => owner.kind === "node" && owner.id === subjectId
      && path.resolve(owner.path) === path.resolve(file.fileName));
    for (const owner of owners) {
      const implementation = implementationDeclaration(ts, file, owner.export || "run")
        || file.statements.find(item => item.name?.text === owner.export);
      enqueue(implementation, true);
    }
  }
  while (pending.length) {
    const statement = pending.pop();
    function visit(node) {
      if (ts.isIdentifier(node)) {
        const symbol = checker.getSymbolAtLocation(node);
        for (const declaration of symbolDeclarationNodes(symbol, project)) {
          if (declaration.getSourceFile() === statement.getSourceFile()) {
            const candidate = top(declaration);
            if (ts.isImportDeclaration(candidate) || ts.isImportEqualsDeclaration(candidate)) imports.add(candidate);
            else enqueue(declaration);
          }
        }
        if (symbol && checker.getAliasedSymbol) {
          try { for (const declaration of symbolDeclarationNodes(checker.getAliasedSymbol(symbol), project)) enqueue(declaration); }
          catch {}
        }
        // Properties of namespace imports and inherited implementations have
        // their own resolved declarations, even when the local alias does not.
        if (ts.isPropertyAccessExpression(node.parent) && node.parent.name === node) {
          for (const declaration of symbolDeclarationNodes(symbol, project)) enqueue(declaration);
        }
      }
      visitChildren(ts, node, visit);
    }
    visit(statement);
  }
  for (const statement of imports) selected.add(statement);
  return sourceFiles.filter(file => [...selected].some(node => node.getSourceFile() === file)).map(file => {
    const nodes = [...selected].filter(node => node.getSourceFile() === file);
    const projected = [];
    const spans = [];
    for (const node of nodes) {
      if (ts.isVariableDeclaration(node) && ts.isVariableStatement(node.parent?.parent)) continue;
      projected.push(node); spans.push([node.getStart(file, true), node.getEnd()]);
    }
    for (const statement of file.statements.filter(node => ts.isVariableStatement(node))) {
      const originals = statement.declarationList.declarations.filter(node => selected.has(node));
      const declarations = originals.map(node => {
        const members = inherited.get(node);
        if (!members) return node;
        const initializer = node.initializer, object = initializer.arguments[0];
        return Object.create(node, {initializer:{value:Object.create(initializer, {
          arguments:{value:[Object.create(object, {properties:{value:[...members]}})]}})}});
      });
      if (!declarations.length) continue;
      projected.push(Object.create(statement,{declarationList:{value:Object.create(statement.declarationList,{declarations:{value:declarations}})}}));
      spans.push([statement.getStart(file,true),statement.declarationList.declarations[0].getStart(file)]);
      for (const declaration of originals) {
        const members = inherited.get(declaration);
        if (!members) { spans.push([declaration.getStart(file), declaration.getEnd()]); continue; }
        const object = declaration.initializer.arguments[0];
        spans.push([declaration.getStart(file), object.getStart(file) + 1], [object.getEnd() - 1, declaration.getEnd()]);
        for (const property of members) spans.push([property.getStart(file), property.getEnd()]);
      }
      for (let index = 1; index < declarations.length; index++) {
        const comma = file.text.indexOf(",", declarations[index - 1].getEnd());
        spans.push([comma, comma + 1]);
      }
      if (file.text[statement.getEnd()-1] === ";") spans.push([statement.getEnd()-1,statement.getEnd()]);
    }
    const visible = new Uint8Array(file.text.length);
    for (const [start, end] of spans) visible.fill(1, start, end);
    const text = file.text.slice(0, Math.max(...spans.map(span => span[1]))).split("").map((char, index) => visible[index] || char === "\n" || char === "\r" ? char : " ").join("");
    const value = {path: path.resolve(file.fileName), text: text + "\n", owner: subjectId};
    Object.defineProperty(value,"parsed",{value:Object.create(file,{text:{value:value.text},statements:{value:projected},parseDiagnostics:{value:[]}})});
    return value;
  });
}

function auditModuleRegExpState(ts, sourceFile, policy, ruleParams = {}) {
  const owner = ownerFor(ts, sourceFile.fileName, policy);
  if (ruleParams.effect_scope === "global_state" || !owner
      || !["node", "base_lib", "plugin"].includes(owner.kind)) return [];
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

function auditModuleStateWrites(ts, sourceFile, checker, project, policy, ruleParams = {}) {
  const owner = ownerFor(ts, sourceFile.fileName, policy);
  if (!owner
      || !["node", "base_lib", "plugin"].includes(owner.kind)) return [];
  const moduleBindings = new Set();
  const aliases = new Set();
  const builtinPrototypeAliases = new Set();
  const builtinObjectAliases = new Set();
  const namespaceAliases = new Map();
  const namespaceGlobals = new Set(["globalThis", "global", "window", "self"]);
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
    "globalThis", "global", "window", "self", "process",
  ]);
  const hostMembers = new Set(["process", "console", "fetch", "XMLHttpRequest", "WebSocket", "EventSource",
    "document", "localStorage", "sessionStorage", "indexedDB", "caches", "navigator", "location",
    "Worker", "SharedWorker", "performance", "crypto", "webcrypto"]);
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

  function namespaceReference(node) {
    const value = unwrapExpression(ts, node);
    if (!value) return null;
    if (ts.isPropertyAccessExpression(value) || ts.isElementAccessExpression(value)) {
      const parent = namespaceReference(value.expression);
      return parent ? [...parent, staticMemberName(value)] : null;
    }
    if (!ts.isIdentifier(value)) return null;
    return namespaceAliases.get(checker.getSymbolAtLocation(value))
      || (isUnshadowedNamedGlobal(value, namespaceGlobals) ? [] : null);
  }

  function permittedNamespaceState(node) {
    const members = namespaceReference(node);
    return ["global_state", "python_io"].includes(ruleParams.effect_scope)
      && members?.length && members[0] !== null
      && !builtinObjects.has(members[0]) && !hostMembers.has(members[0])
      && !members.some(name => name === "prototype" || name === "__proto__");
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
    if (!value) return false;
    if (namespaceReference(value)) return !permittedNamespaceState(value);
    if (!ts.isIdentifier(value)) return false;
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
    if (permittedNamespaceState(value)) return false;
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
        const namespace = namespaceReference(node.initializer);
        if (namespace && destination && !namespaceAliases.has(destination)) {
          namespaceAliases.set(destination, namespace);
          changed = true;
        }
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
    if (ruleParams.effect_scope === "global_state") return;
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
      if (writesBuiltinPrototype(node.left)) {
        reportBuiltinPrototype(node.left);
      } else if (writesBuiltinObject(node.left)) {
        reportBuiltinObject(node.left);
      } else if (writesAlias(node.left)) report(node.left);
    } else if (isKind(
      ts,
      node,
      "isDeleteExpression",
      "isDeleteExpression",
      "DeleteExpression",
    )) {
      if (writesBuiltinPrototype(node.expression)) {
        reportBuiltinPrototype(node.expression);
      } else if (writesBuiltinObject(node.expression)) {
        reportBuiltinObject(node.expression);
      } else if (writesAlias(node.expression)) report(node.expression);
    } else if ((ts.isPrefixUnaryExpression(node)
        || ts.isPostfixUnaryExpression(node))
        && new Set([
          ts.SyntaxKind.PlusPlusToken,
          ts.SyntaxKind.MinusMinusToken,
          ts.SyntaxKind.DeleteKeyword,
        ]).has(node.operator)) {
      if (writesBuiltinPrototype(node.operand)) {
        reportBuiltinPrototype(node.operand);
      } else if (writesBuiltinObject(node.operand)) {
        reportBuiltinObject(node.operand);
      } else if (writesAlias(node.operand)) report(node.operand);
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
        if (writesBuiltinPrototype(firstArgument)) {
          reportBuiltinPrototype(firstArgument);
        } else if (writesBuiltinObject(firstArgument)
            || isBuiltinObjectSource(firstArgument)) {
          reportBuiltinObject(firstArgument);
        } else if (writesAlias(firstArgument)) report(firstArgument);
      }
    }
    visitChildren(ts, node, visit);
  }
  visit(sourceFile);
  return findings;
}

function canonicalImportSpecifier(value) {
  return value.startsWith("node:") ? value.slice(5) : value;
}

function auditRuleImportPolicy(ts, sourceFile, ruleParams) {
  const selected = ruleParams.policy?.imports || {};
  const moduleMatches = (name, choices) => (choices || []).some(
    value => name === canonicalImportSpecifier(value) || name.startsWith(`${canonicalImportSpecifier(value)}/`),
  );
  const findings = [];
  for (const imported of importSpecifiers(ts, sourceFile)) {
    const name = canonicalImportSpecifier(imported.value);
    const root = packageName(name);
    const denied = moduleMatches(name, selected.banned_modules)
      || !moduleMatches(name, selected.allowed_modules)
        && (selected.banned_roots || []).map(canonicalImportSpecifier).includes(root)
        && !(selected.allowed_roots || []).map(canonicalImportSpecifier).includes(root);
    if (denied) findings.push(importFinding(sourceFile, imported.node, "VF_IMPORT_POLICY",
      `selected Rule policy forbids import '${imported.value}'`));
  }
  return findings;
}

function auditHostIo(ts, sourceFile, checker, project, policy, ruleParams = {}) {
  const owner = ownerFor(ts, sourceFile.fileName, policy);
  if (!owner || !["node", "base_lib", "plugin"].includes(owner.kind)) return [];
  const scope = ruleParams.effect_scope || "none";
  const code = owner.kind === "plugin" ? "VF_PLUGIN_HOST_IO" : "VF_BASE_LIB_HOST_IO";
  const namespaceGlobals = new Set(["window", "self", "global", "globalThis"]);
  const terminalMembers = new Set(["stdin", "stdout", "stderr", "argv"]);
  const terminalConsole = new Set(["log", "info", "warn", "error", "debug", "dir", "dirxml", "table", "trace", "assert", "clear", "group", "groupCollapsed", "groupEnd"]);
  const hardProcessMembers = new Set(["abort", "exit", "kill", "chdir", "setuid", "setgid", "seteuid", "setegid", "setgroups", "umask"]);
  const targetGlobals = new Set([
    "fetch", "XMLHttpRequest", "WebSocket", "EventSource", "document",
    "window", "self", "global", "globalThis", "localStorage",
    "sessionStorage", "indexedDB", "caches", "navigator", "location",
    "process", "console",
    "Worker", "SharedWorker", "crypto", "webcrypto",
  ]);
  const localComputationGlobals = new Set(["Date", "performance", "Math"]);
  const hostIoModules = new Set([
    "child_process", "cluster", "dgram", "dns", "fs", "http", "https",
    "net", "tls", "worker_threads",
  ]);
  const findings = [];
  const importedPrimitives = new Map();

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
      code,
      `${owner.kind} '${owner.id}' cannot access host global '${name}' under effect_scope '${scope}'; use an explicitly permitted effect or Capability`,
    ));
  }

  for (const imported of importSpecifiers(ts, sourceFile)) {
    const moduleName = canonicalImportSpecifier(imported.value);
    const rootName = moduleName.split("/", 1)[0];
    const bindings = imported.declaration?.importClause?.namedBindings;
    if (rootName === "process" || rootName === "console") {
      const remember = (node, members = []) => {
        const symbol = node && checker.getSymbolAtLocation(node);
        if (symbol) importedPrimitives.set(symbol, {primitive: rootName, members});
      };
      remember(imported.declaration?.importClause?.name);
      if (bindings && ts.isNamespaceImport(bindings)) remember(bindings.name);
      if (bindings && ts.isNamedImports(bindings)) {
        for (const item of bindings.elements) remember(item.name, [(item.propertyName || item.name).text]);
      }
    }
    const terminalProcessImport = rootName === "process" && scope === "terminal"
      && bindings && ts.isNamedImports(bindings)
      && bindings.elements.every(item => terminalMembers.has((item.propertyName || item.name).text));
    if ((hostIoModules.has(rootName) || rootName === "process" || rootName === "console")
        && scope !== "python_io" && !terminalProcessImport && !(rootName === "console" && scope === "terminal")) {
      findings.push(importFinding(
        sourceFile,
        imported.node,
        code,
        `${owner.kind} '${owner.id}' cannot import host IO module '${imported.value}' under effect_scope '${scope}'`,
      ));
    }
  }

  function primitiveReference(expression) {
    const value = unwrapExpression(ts, expression);
    if (!value) return null;
    if (ts.isPropertyAccessExpression(value) || ts.isElementAccessExpression(value)) {
      const parent = primitiveReference(value.expression);
      return parent ? {...parent, members: [...parent.members, memberName(value)]} : null;
    }
    if (!ts.isIdentifier(value)) return null;
    const alias = importedPrimitives.get(checker.getSymbolAtLocation(value));
    if (alias) return alias;
    return isUnshadowedGlobal(value, targetGlobals) ? {primitive:value.text, members:[]} : null;
  }

  // Follow static primitive aliases by symbol, so permissions and hard process
  // restrictions survive ordinary local bindings without relying on their names.
  let aliasesChanged = true;
  while (aliasesChanged) {
    aliasesChanged = false;
    function collect(node) {
      if (ts.isVariableDeclaration(node) && ts.isIdentifier(node.name) && node.initializer) {
        const symbol = checker.getSymbolAtLocation(node.name);
        const primitive = primitiveReference(node.initializer);
        if (symbol && primitive && !importedPrimitives.has(symbol)) {
          importedPrimitives.set(symbol, primitive);
          aliasesChanged = true;
        }
      }
      visitChildren(ts, node, collect);
    }
    collect(sourceFile);
  }

  function visit(node) {
    if (ts.isIdentifier(node) && identifierIsReference(ts, node)) {
      const imported = importedPrimitives.get(checker.getSymbolAtLocation(node));
      let primitive = imported?.primitive || node.text;
      const members = [...(imported?.members || [])];
      let current = node;
      for (let member = directMemberAccess(current); member; member = directMemberAccess(current)) {
        members.push(memberName(member));
        current = member;
      }
      const recognized = imported || isUnshadowedGlobal(node, targetGlobals);
      if (recognized) {
        const namespace = namespaceGlobals.has(primitive);
        if (namespace) primitive = members.shift();
        const name = members[0];
        if (localComputationGlobals.has(primitive)
            || (["crypto", "webcrypto"].includes(primitive) && ["getRandomValues", "randomUUID"].includes(name))) {
          // Reading time and using native math/random primitives does not grant Host I/O.
        } else if (!primitive || !targetGlobals.has(primitive)) {
          // A static custom slot is native host/resource state. The namespace
          // value itself is a harmless read for general I/O; dynamic selection
          // stays bounded, and builtin/prototype writes are checked separately.
          const customState = namespace && primitive && !members.includes("prototype") && !members.includes("__proto__");
          if (!(namespace && scope === "python_io" && primitive == null && members.length === 0)
              && !(customState && ["python_io", "global_state"].includes(scope))) reportHostGlobal(node, node.text);
        } else if (primitive === "process" && hardProcessMembers.has(name)) {
          reportHostGlobal(node, `process.${name}`);
        } else if (scope !== "python_io"
            && !(scope === "terminal" && primitive === "console" && terminalConsole.has(name))
            && !(scope === "terminal" && primitive === "process" && terminalMembers.has(name))) {
          reportHostGlobal(node, [primitive, ...members].filter(Boolean).join("."));
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

function qualityLineCount(text) {
  if (!text) return 0;
  const lines = text.split(/\r\n|\r|\n/).length;
  return /(?:\r\n|\r|\n)$/.test(text) ? lines - 1 : lines;
}

function qualityPosition(sourceFile, node) {
  const position = sourceFile.getLineAndCharacterOfPosition(node.getStart(sourceFile));
  return { line: position.line + 1, column: position.character + 1 };
}

function qualityIsFunction(ts, node) {
  return Boolean(node.body) && (
    ts.isFunctionDeclaration(node) || ts.isFunctionExpression(node)
    || ts.isArrowFunction(node) || ts.isMethodDeclaration(node)
    || ts.isConstructorDeclaration(node) || ts.isGetAccessorDeclaration(node)
    || ts.isSetAccessorDeclaration(node)
  );
}

function qualityBranch(ts, node) {
  const kind = node.kind;
  if (kind === ts.SyntaxKind.IfStatement
      || kind === ts.SyntaxKind.ForStatement
      || kind === ts.SyntaxKind.ForInStatement
      || kind === ts.SyntaxKind.ForOfStatement
      || kind === ts.SyntaxKind.WhileStatement
      || kind === ts.SyntaxKind.DoStatement
      || kind === ts.SyntaxKind.SwitchStatement
      || kind === ts.SyntaxKind.TryStatement
      || kind === ts.SyntaxKind.ConditionalExpression) return true;
  return kind === ts.SyntaxKind.BinaryExpression && [
    ts.SyntaxKind.AmpersandAmpersandToken,
    ts.SyntaxKind.BarBarToken,
    ts.SyntaxKind.QuestionQuestionToken,
  ].includes(node.operatorToken?.kind);
}

function qualityBranchMetrics(ts, root) {
  let branches = 0;
  let maxDepth = 0;
  function visit(node, depth) {
    const next = depth + (qualityBranch(ts, node) ? 1 : 0);
    if (next > depth) branches += 1;
    maxDepth = Math.max(maxDepth, next);
    visitChildren(ts, node, (child) => visit(child, next));
  }
  visit(root, 0);
  return { branches, maxDepth };
}

function qualityFunctionName(ts, node, sourceFile) {
  if (node.name?.text) return String(node.name.text);
  const parent = node.parent;
  if (parent?.name?.text) return String(parent.name.text);
  const location = qualityPosition(sourceFile, node);
  return `anonymous@${location.line}:${location.column}`;
}

function qualityFingerprint(ts, node) {
  const kinds = [];
  function visit(child) {
    kinds.push(String(child.kind));
    visitChildren(ts, child, visit);
  }
  visit(node.body || node);
  return kinds.join(",");
}

function qualityFunctions(ts, sourceFile) {
  const functions = [];
  let classCount = 0;
  function visit(node, scope) {
    const classNode = ts.isClassDeclaration(node) || ts.isClassExpression(node);
    if (classNode) classCount += 1;
    let nextScope = scope;
    if (qualityIsFunction(ts, node)) {
      const name = qualityFunctionName(ts, node, sourceFile);
      const start = qualityPosition(sourceFile, node).line;
      const end = sourceFile.getLineAndCharacterOfPosition(node.getEnd()).line + 1;
      const complexity = qualityBranchMetrics(ts, node.body);
      functions.push({
        qualname: [...scope, name].join("."),
        line_start: start,
        line_end: end,
        lines: Math.max(1, end - start + 1),
        branches: complexity.branches,
        max_nesting_depth: complexity.maxDepth,
        param_count: node.parameters?.length || 0,
        ast_fingerprint: qualityFingerprint(ts, node),
      });
      nextScope = [...scope, name];
    } else if (classNode) {
      nextScope = [...scope, qualityFunctionName(ts, node, sourceFile)];
    } else if (ts.isVariableDeclaration(node) && node.name?.text && isSdkDeclaration(ts, sourceFile, node.initializer)) {
      nextScope = [...scope, node.name.text];
    }
    visitChildren(ts, node, (child) => visit(child, nextScope));
  }
  visit(sourceFile, []);
  return { functions, classCount };
}

function qualityPublicApiCount(ts, sourceFile) {
  let count = 0;
  for (const statement of sourceFile.statements || []) {
    if (statement.modifiers?.some((item) => item.kind === ts.SyntaxKind.ExportKeyword)) {
      count += 1;
    } else if (ts.isExportDeclaration(statement)) {
      count += statement.exportClause?.elements?.length || 1;
    } else if (ts.isExportAssignment(statement)) {
      count += 1;
    }
  }
  return count;
}

function qualitySyntaxDiagnostics(ts, program, sourceFile) {
  const diagnostics = ts.__native
    ? program.getSyntacticDiagnostics(sourceFile.fileName)
    : program.getSyntacticDiagnostics(sourceFile);
  return diagnostics.map((item) => {
    const data = diagnosticText(ts, item);
    const offset = item.start ?? item.pos ?? item.range?.start ?? 0;
    const position = sourceFile.getLineAndCharacterOfPosition(
      typeof offset === "number" ? offset : 0,
    );
    return {
      code: "QUALITY.SYNTAX.JAVASCRIPT",
      severity: "error",
      object_type: "file",
      path: path.resolve(sourceFile.fileName),
      line: data.line || position.line + 1,
      column: data.column || position.character + 1,
      message: data.message,
    };
  });
}

function qualityCallGraph(ts, sourceFile, exportName) {
  const functions = new Map();
  const aliases = new Map();
  function register(name, node) {
    if (!name || !node?.body) return;
    functions.set(name, node);
    const leaf = name.split(".").at(-1);
    aliases.set(leaf, aliases.has(leaf) ? null : name);
  }
  function collect(node, owner = "") {
    if (qualityIsFunction(ts, node)) {
      let name = node.name?.text || "";
      const parent = node.parent;
      if (!name && parent?.name?.text) name = parent.name.text;
      if (name) register(owner ? `${owner}.${name}` : name, node);
      if (node.body) visitChildren(ts, node.body, (child) => collect(child, owner));
      return;
    }
    if (ts.isClassDeclaration(node) || ts.isClassExpression(node)) {
      const className = node.name?.text || owner;
      visitChildren(ts, node, (child) => collect(child, className));
      return;
    }
    if (ts.isVariableDeclaration(node) && node.name?.text && node.initializer) {
      const value = isSdkDeclaration(ts, sourceFile, node.initializer) ? node.initializer.arguments[0] : node.initializer;
      if (ts.isObjectLiteralExpression(value)) {
        visitChildren(ts, value, (child) => collect(child, node.name.text));
        return;
      }
    }
    visitChildren(ts, node, (child) => collect(child, owner));
  }
  collect(sourceFile);
  const graph = {};
  for (const [name, node] of functions) {
    const calls = new Set();
    const shadowed = new Set();
    function addBinding(binding) {
      if (ts.isIdentifier(binding)) {
        shadowed.add(binding.text);
      } else if (binding?.elements) {
        for (const element of binding.elements) {
          if (element?.name) addBinding(element.name);
        }
      }
    }
    for (const parameter of node.parameters || []) addBinding(parameter.name);
    function collectShadowed(child) {
      if (child !== node.body && qualityIsFunction(ts, child)) return;
      if (ts.isVariableDeclaration(child) && child.name) {
        if (!child.initializer || !qualityIsFunction(ts, child.initializer)) {
          addBinding(child.name);
        }
      }
      visitChildren(ts, child, collectShadowed);
    }
    collectShadowed(node.body);
    function visit(child) {
      if (child !== node.body && qualityIsFunction(ts, child)) return;
      if (ts.isCallExpression(child)) {
        const expression = child.expression;
        let target = "";
        if (ts.isIdentifier(expression)) {
          target = shadowed.has(expression.text)
            ? "" : (aliases.get(expression.text) || "");
        } else if (ts.isPropertyAccessExpression(expression)) {
          const receiver = expression.expression;
          if (ts.isIdentifier(receiver)) {
            const candidate = `${receiver.text}.${expression.name.text}`;
            target = functions.has(candidate) ? candidate : "";
          } else if (receiver.kind === ts.SyntaxKind.ThisKeyword) {
            const candidate = `${name.split(".")[0]}.${expression.name.text}`;
            target = functions.has(candidate) ? candidate : "";
          }
        }
        if (target) calls.add(target);
      }
      visitChildren(ts, child, visit);
    }
    visit(node.body);
    graph[name] = [...calls].sort();
  }
  const entry = functions.has(exportName) ? exportName : (aliases.get(exportName) || "");
  return { entry, calls: graph };
}

function collectQualityFacts(ts, program, checker, project, sourceFiles, request) {
  const root = path.resolve(request.qualityRoot || request.packageRoot);
  const selected = new Set(
    (request.qualityFiles || []).map((file) => path.resolve(file)),
  );
  const modules = new Map(
    [...selected].map((file) => [file, path.relative(root, file).split(path.sep).join("/")]),
  );
  const files = [];
  const findings = [];
  const implementations = [];
  for (const sourceFile of sourceFiles) {
    const filePath = path.resolve(sourceFile.fileName);
    if (!selected.has(filePath)) continue;
    const module = modules.get(filePath);
    const text = sourceFile.getFullText();
    const syntax = qualitySyntaxDiagnostics(ts, program, sourceFile);
    findings.push(...syntax.map((item) => ({ ...item, object_id: module })));
    const parsed = syntax.length ? { functions: [], classCount: 0 } : (analysisSession?analysisSession.metric(analysisSession.functions,sourceFile,"",()=>qualityFunctions(ts,sourceFile)):qualityFunctions(ts,sourceFile));
    const complexity = syntax.length ? { branches: 0, maxDepth: 0 } : qualityBranchMetrics(ts, sourceFile);
    const importSites = [];
    if (!syntax.length) {
      for (const imported of importSpecifiers(ts, sourceFile)) {
        const resolved = resolvedImportFile(ts, checker, project, imported, filePath);
        // A bare unresolved package name can look exactly like a root-relative
        // module ID.  Keep its spelling in raw_import, but mark the normalized
        // target as external so Core cannot infer an internal edge from text.
        const target = modules.get(path.resolve(resolved || ""))
          || `external:${imported.value}`;
        const location = qualityPosition(sourceFile, imported.node);
        importSites.push({
          source_module: module,
          imported: target,
          raw_import: imported.value,
          resolved_path: resolved ? path.resolve(resolved) : "",
          path: module,
          line: location.line,
          column: location.column,
        });
      }
    }
    files.push({
      path: module,
      module,
      lines: request.publicNodeView ? text.split(/\r?\n/).filter(line => line.trim()).length : qualityLineCount(text),
      bytes: Buffer.byteLength(request.publicNodeView ? text.split(/\r?\n/).filter(line => line.trim()).join("\n") + "\n" : text, "utf8"),
      function_count: parsed.functions.length,
      class_count: parsed.classCount,
      public_api_count: syntax.length ? 0 : qualityPublicApiCount(ts, sourceFile),
      branch_count: complexity.branches,
      max_nesting_depth: complexity.maxDepth,
      imports: [...new Set(importSites.map((item) => item.imported))].sort(),
      functions: parsed.functions,
      import_sites: importSites,
    });
    for (const item of request.qualityImplementations || []) {
      if (path.resolve(item.path) !== filePath || syntax.length) continue;
      const ownershipImports = ownershipImportStatements(ts,sourceFile,checker,project,{
        implementation:implementationDeclaration(ts,sourceFile,String(item.export ?? "run")),
        declarations:symbolDeclarationNodes,unwrap:unwrapExpression,sdkDeclaration:isSdkDeclaration,
      });
      const lines = statements => [...new Set([...statements].map(node=>qualityPosition(sourceFile,node).line))].sort((a,b)=>a-b);
      implementations.push({
        path: module,
        id: String(item.id || ""),
        kind: String(item.kind || "node"),
        export: String(item.export ?? "run"),
        entry_import_lines:lines(ownershipImports.entry),
        module_initialization_import_lines:lines(ownershipImports.initialization),
        import_lines:lines(new Set([...ownershipImports.entry,...ownershipImports.initialization])),
        ...(analysisSession?analysisSession.metric(analysisSession.callGraphs,sourceFile,String(item.export ?? "run"),()=>qualityCallGraph(ts,sourceFile,String(item.export ?? "run"))):qualityCallGraph(ts,sourceFile,String(item.export ?? "run"))),
      });
    }
  }
  return { files: files.sort((a, b) => a.path.localeCompare(b.path)), findings, implementations };
}

async function auditContracts(ts, request, extraFiles = [], checkDiagnostics = true, qualityOnly = false) {
  const files = [...new Set([...(request.typecheckFiles || []), ...(request.qualityFiles || []), ...extraFiles])]
    .map((item) => path.resolve(item));
  const contractFiles = new Set(
    (request.contractCheckFiles || []).map((item) => path.resolve(item)),
  );
  const findings = [];
  const jsonCompilerOptions = {
    paths: {"@vibeflow/plugin": [sdkTypes]},
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
    // A target-neutral quality pass needs type facts from both common host
    // families so ownership checks can prove that browser-only calls such as
    // fetch() return Promise values.  These libraries are facts for the
    // VibeFlow ownership analysis only: ordinary TypeScript diagnostics are
    // still restricted to generated ABI contract files below.
    lib: request.target === "node"
      ? ["ES2022"]
      : ["ES2022", "DOM", "DOM.Iterable"],
  };
  const state=await analysisProgram(ts,request,files,jsonCompilerOptions,analysisSession);
  const {program,checker,project,sourceFiles}=state;
  const diagnostics=checkDiagnostics?sourceFiles.filter(item=>contractFiles.has(path.resolve(item.fileName)))
    .flatMap(item=>ts.__native?[...program.getSyntacticDiagnostics(item.fileName),...program.getBindDiagnostics(item.fileName),...program.getSemanticDiagnostics(item.fileName)]
      :ts.getPreEmitDiagnostics(program,item)).map(item=>diagnosticText(ts,item)):[];
  try {
    if (qualityOnly) {
      return collectQualityFacts(ts, program, checker, project, sourceFiles, request);
    }
    const policy = normalizeImportPolicy(
      request.importPolicy,
      request.packageRoot,
    );
    const selectedOwners = policy.owners.filter(owner => owner.id === request.ruleSubjectId && owner.kind === request.ruleSubjectKind);
    policy.owners = [...selectedOwners, ...policy.owners.filter(owner => !selectedOwners.includes(owner))];
    deriveTransitiveOwners(
      ts,
      sourceFiles,
      checker,
      project,
      policy,
    );
    const rootFiles = new Set(files.map((item) => path.resolve(item)));
    const topics = new Set(request.ruleTopics || []);
    const ruleParams = request.ruleParams || {};
    const effectScopes = [...topics].some(topic => ["module_state", "host_io", "effect_imports"].includes(topic))
      ? implementationEffectScopes(ts, sourceFiles, checker, project, policy, rootFiles) : new Map();
    for (const sourceFile of sourceFiles) {
      if (sourceFile.isDeclarationFile && sourceFile.fileName.includes(`${path.sep}node_modules${path.sep}`)) continue;
      const owned = ownerFor(ts, sourceFile.fileName, policy);
      if (!owned && !rootFiles.has(path.resolve(sourceFile.fileName))) continue;
      if (!sourceFile.isDeclarationFile) findings.push(...qualitySyntaxDiagnostics(ts, program, sourceFile)
        .map(item => ({...item, file:item.path})));
      const implementationFile = implementationScope(ts, sourceFile, checker, project, policy);
      if (request.profile === "single-esm") findings.push(...auditSingleEsmConstraints(ts, sourceFile));
      if (topics.has("imports")) {
        findings.push(...auditParsedSource(ts, sourceFile, ""));

        findings.push(...auditRuleImportPolicy(ts, sourceFile, ruleParams));
      }
      if (topics.has("architecture")) findings.push(...auditImportOwnership(ts, implementationFile, checker, project, policy));
      if (sourceFile.isDeclarationFile) continue;
      if (topics.has("purity")) findings.push(...auditTopLevelPurity(ts, sourceFile, policy, ruleParams));
      if (topics.has("completion")) findings.push(...auditCompletionAndPromiseOwnership(ts, sourceFile, checker, policy, project));
      for (const effect of effectScopes.get(normalizedRealPath(ts, sourceFile.fileName)) || []) {
        const scoped = [];
        if (topics.has("module_state")) {
          scoped.push(...auditModuleRegExpState(ts, sourceFile, effect.policy, ruleParams));
          scoped.push(...auditModuleStateWrites(ts, effect.scope, checker, project, effect.policy, ruleParams));
        }
        if (topics.has("host_io")) scoped.push(...auditHostIo(ts, effect.scope, checker, project, effect.policy, ruleParams));
        if (topics.has("effect_imports")) {
          scoped.push(...auditParsedSource(ts, effect.scope, ""));
          scoped.push(...auditRuleImportPolicy(ts, effect.scope, ruleParams));
        }
        findings.push(...scoped.map(finding => ({...finding, owner: ownerFor(ts, sourceFile.fileName, effect.policy)})));
      }
      const sharedOwners = policy.owners.filter(
        (item) => path.resolve(item.path) === path.resolve(sourceFile.fileName),
      );
      for (const alternate of topics.has("completion") ? sharedOwners.slice(1) : []) {
        const alternatePolicy = {
          ...policy,
          owners: [alternate, ...policy.owners.filter((item) => item !== alternate)],
        };
        findings.push(...auditCompletionAndPromiseOwnership(
          ts, sourceFile, checker, alternatePolicy, project,
        ).map((finding) => ({
          ...finding,
          owner: { id: alternate.id, kind: alternate.kind, path: alternate.path },
        })));
      }
    }
    if (request.command === "rule-check") {
      const localSources = request.publicNodeView ? publicSourceViews(ts, sourceFiles, checker, project, policy, rootFiles, request.ruleSubjectId) : [];
      const localQuality = request.publicNodeView ? collectQualityFacts(ts, program, checker, project, localSources.map(source=>source.parsed), {...request,qualityRoot:request.qualityRoot || request.packageRoot,qualityFiles:localSources.map(source=>source.path)}) : null;
      return {
        local_quality: localQuality,
        findings: findings.map(finding => ({ ...finding, owner: finding.owner || ownerFor(ts, finding.file, policy) })),
        local_sources: localSources,
        sources: sourceFiles.filter(file => !file.fileName.includes(`${path.sep}node_modules${path.sep}`)).map(file => ({ path: path.resolve(file.fileName), text: file.text,
          initialization: file.statements.filter(statement => !ts.isFunctionDeclaration(statement) && !(ts.isVariableStatement(statement) && statement.declarationList.declarations.every(declaration => {const value=unwrapExpression(ts,declaration.initializer); return value && (ts.isArrowFunction(value) || ts.isFunctionExpression(value) || isSdkDeclaration(ts,file,value));}))).map(statement => [file.getLineAndCharacterOfPosition(statement.getStart(file)).line, statement.getText(file)]),
          imports: importSpecifiers(ts,file).map(imported => ({specifier:imported.value,
            path:resolvedImportFile(ts,checker,project,imported,file.fileName) || "",
            line:file.getLineAndCharacterOfPosition(imported.node.getStart(file)).line + 1,
            type_only:Boolean(imported.declaration.importClause?.isTypeOnly || imported.declaration.isTypeOnly)})) })),
      };
    }
    if (findings.length) {
      const diagnosticsWithOwners = findings.map((finding) => {
        if (finding.owner) return finding;
        const owner = finding.file
          ? ownerFor(ts, finding.file, policy)
          : null;
        return owner
          ? {
              ...finding,
              owner: {
                id: owner.id,
                kind: owner.kind,
                path: path.resolve(owner.path),
              },
            }
          : finding;
      });
      fail("VF_IMPORT_POLICY", "JavaScript/TypeScript import policy failed", {
        diagnostics: diagnosticsWithOwners,
      });
    }
    const contractDiagnostics = diagnostics.filter(
      (item) => item.file && contractFiles.has(path.resolve(item.file)),
    );
    if (contractDiagnostics.length) {
      fail("VF_TYPESCRIPT", "VibeFlow TypeScript ABI validation failed", {
        diagnostics: contractDiagnostics,
      });
    }
  } finally { await state.dispose(); }
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

function esbuildDiagnostics(cause) {
  const messages = Array.isArray(cause?.errors) ? cause.errors : [];
  return messages.map((item) => {
    const location = item?.location || {};
    return {
      code: "ESBUILD",
      message: String(item?.text || cause?.message || "esbuild failed"),
      ...(location.file ? { file: path.resolve(location.file) } : {}),
      ...(Number.isInteger(location.line) ? { line: location.line } : {}),
      ...(Number.isInteger(location.column)
        ? { column: location.column + 1 }
        : {}),
    };
  });
}

async function build(request, tools) {
  await auditContracts(tools.typescript, request);
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
    plugins: [workflowVirtualPlugin(request.workflowEntry), sdkPlugin(tools.typescript, {runtimeBindings: request.runtimeBindings})],
  };
  let result;
  try {
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
  } catch (cause) {
    if (typeof cause?.code === "string" && cause.code.startsWith("VF_")) {
      throw cause;
    }
    fail("VF_ESBUILD", "esbuild could not produce the selected target", {
      diagnostics: esbuildDiagnostics(cause),
    });
  }
  const closureFiles = Object.keys(result.metafile?.inputs || {})
    .map((item) => path.isAbsolute(item) ? item : path.resolve(request.packageRoot, item))
    .filter((item) => !item.startsWith("<")
      && !item.includes(`${path.sep}${VIRTUAL_WORKFLOW_NAMESPACE}:`));
  await auditContracts(tools.typescript, request, closureFiles, false);
  return {
    outputs: Object.keys(result.metafile?.outputs || {}).sort(),
    inputs: Object.keys(result.metafile?.inputs || {}).sort(),
  };
}

const packageCache=new Map();
async function dispatch(request){
  const packageRoot = path.resolve(request.packageRoot);
  const toolsKey=JSON.stringify([packageRoot,request.command === "build"]);
  if(!packageCache.has(toolsKey))packageCache.set(toolsKey,await packageTools(packageRoot,{requireEsbuild:request.command === "build"}));
  const tools=packageCache.get(toolsKey);
  const probe = {
    node: process.versions.node,
    typescript: String(tools.typescript.version || ""),
    ...(tools.esbuild
      ? { esbuild: String(tools.esbuild.version || "") }
      : {}),
  };
  if (request.command === "probe") return { ok: true, probe };
  if (request.command === "build") {
    return { ok: true, probe, build: await build(request, tools) };
  }
  if (request.command === "audit") {
    await auditContracts(tools.typescript, request, [], false);
    return { ok: true, probe, audit: { checked: true } };
  }
  if (request.command === "rule-check") {
    const rules = await auditContracts(tools.typescript, request, [], false);
    return { ok: true, probe, rules };
  }
  if (request.command === "quality-facts") {
    const facts = await auditContracts(tools.typescript, request, [], false, true);
    return { ok: true, probe, quality: facts };
  }
  fail("VF_PROTOCOL", `unknown driver command '${String(request.command)}'`);
}

function errorPayload(error){return {ok:false,error:{code:error?.code||"VF_TOOLCHAIN_INTERNAL",message:error instanceof Error?error.message:String(error),details:error?.details||{}}};}
if(process.argv.length===3&&process.argv[2]==="--session"){
  analysisSession=new AnalysisSession();
  const input=readline.createInterface({input:process.stdin,crlfDelay:Infinity});
  try{for await(const line of input){if(!line.trim())continue;let result;try{result=await dispatch(JSON.parse(line));}catch(error){result=errorPayload(error);}process.stdout.write(JSON.stringify(result)+"\n");}}
  finally{await analysisSession.dispose();}
}else{
  try{
    if(process.argv.length!==3)fail("VF_PROTOCOL","usage: node toolchain_driver.mjs REQUEST.json");
    const request=JSON.parse(await readFile(path.resolve(process.argv[2]),"utf8"));
    process.stdout.write(JSON.stringify(await dispatch(request)));
  }catch(error){process.stdout.write(JSON.stringify(errorPayload(error)));process.exitCode=1;}
}
