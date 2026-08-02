import { createRequire, isBuiltin } from "node:module";
import { existsSync, realpathSync } from "node:fs";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import process from "node:process";
import { pathToFileURL } from "node:url";

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

function normalizeImportPolicy(raw, packageRoot) {
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
    packageRoot: normalizedRealPath({ sys: null }, packageRoot),
    derivedOwners: new Map(),
    nodeBaseLibs: policy.nodeBaseLibs && typeof policy.nodeBaseLibs === "object"
      ? policy.nodeBaseLibs : {},
    baseLibDependencies: policy.baseLibDependencies && typeof policy.baseLibDependencies === "object"
      ? policy.baseLibDependencies : {},
    hostExtensionDependencies:
      policy.hostExtensionDependencies
      && typeof policy.hostExtensionDependencies === "object"
        ? policy.hostExtensionDependencies : {},
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

function directOwnerFor(ts, fileName, policy) {
  const candidate = normalizedRealPath(ts, fileName);
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
      || !["node", "base_lib", "host_extension", "plugin"].includes(sourceOwner.kind)) return [];
  const findings = [];
  for (const imported of importSpecifiers(ts, sourceFile)) {
    const specifier = imported.value;
    // Explicit Node builtin imports are platform facts.  esbuild decides
    // whether the selected build target can resolve them; they do not affect
    // VibeFlow ownership between nodes/base_lib/plugins/extensions.
    if (isBuiltin(specifier)) continue;
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
    if (!isWithinPath(policy.packageRoot, resolvedFile)) {
      findings.push(importFinding(
        sourceFile,
        imported.node,
        "VF_IMPORT_PACKAGE_ROOT",
        `${sourceOwner.kind} '${sourceOwner.id}' imports source outside package_root: '${resolvedFile}'`,
      ));
      continue;
    }
    const destination = directOwnerFor(ts, resolvedFile, policy);
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
    } else if (sourceOwner.kind === "plugin") {
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
      || !["node", "base_lib", "host_extension", "plugin", "source"].includes(owner.kind)) return [];
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

function auditCompletionAndPromiseOwnership(ts, sourceFile, checker, policy) {
  const owner = ownerFor(ts, sourceFile.fileName, policy);
  if (!owner || !["node", "host_extension", "plugin"].includes(owner.kind)) return [];
  const declaration = implementationDeclaration(ts, sourceFile, owner.export);
  if (!declaration) return [];
  const findings = [];
  const completion = owner.completion || "immediate";
  const subject = owner.kind === "host_extension"
    ? `host_extension '${owner.id}' factory`
    : owner.kind === "plugin"
      ? `plugin '${owner.id}' factory`
      : `node '${owner.id}'`;
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
  // A host extension's factory must be immediate, but its returned start/stop
  // methods may suspend. The descriptor check above is therefore the complete
  // factory audit; Promise ownership rules below remain specific to nodes.
  if (owner.kind === "host_extension") return findings;
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
            `runtime plugin '${owner.id}' cannot register long-lived listeners or timers; use a host_extension`,
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
      || !["node", "base_lib", "host_extension", "plugin", "source"].includes(owner.kind)) return [];
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
      || !["node", "base_lib", "host_extension", "plugin", "source"].includes(owner.kind)) return [];
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

function auditBaseLibHostIo(ts, sourceFile, checker, project, policy) {
  const owner = ownerFor(ts, sourceFile.fileName, policy);
  if (!owner || owner.kind !== "base_lib") return [];
  const targetGlobals = new Set([
    "fetch", "XMLHttpRequest", "WebSocket", "EventSource", "document",
    "window", "self", "global", "globalThis", "localStorage",
    "sessionStorage", "indexedDB", "caches", "navigator", "location",
    "process",
  ]);
  const nondeterministicGlobals = new Set([
    "Date",
    "performance",
    "crypto",
    "webcrypto",
    "process",
  ]);
  const mathGlobals = new Set(["Math"]);
  const hostIoModules = new Set([
    "child_process", "cluster", "dgram", "dns", "fs", "http", "https",
    "net", "tls", "worker_threads",
  ]);
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

  for (const imported of importSpecifiers(ts, sourceFile)) {
    const moduleName = imported.value.startsWith("node:")
      ? imported.value.slice("node:".length)
      : imported.value;
    const rootName = moduleName.split("/", 1)[0];
    if (hostIoModules.has(rootName)) {
      findings.push(importFinding(
        sourceFile,
        imported.node,
        "VF_BASE_LIB_HOST_IO",
        `base_lib '${owner.id}' cannot import host IO module '${imported.value}'; use a Capability from a node`,
      ));
    }
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

function auditPluginHostIo(ts, sourceFile, checker, project, policy) {
  const owner = ownerFor(ts, sourceFile.fileName, policy);
  if (!owner || owner.kind !== "plugin") return [];
  const blocked = new Set([
    "globalThis", "window", "self", "global", "document", "process",
    "localStorage", "sessionStorage", "navigator", "location", "fetch",
    "XMLHttpRequest", "WebSocket", "EventSource", "indexedDB", "caches",
    "Worker", "SharedWorker",
  ]);
  const findings = [];
  function locallyDeclared(node) {
    const symbol = checker.getSymbolAtLocation(node);
    return symbolDeclarationNodes(symbol, project).some((declaration) => {
      const file = declaration.getSourceFile();
      return !file.isDeclarationFile
        && normalizedRealPath(ts, file.fileName)
          === normalizedRealPath(ts, sourceFile.fileName);
    });
  }
  function visit(node) {
    if (ts.isIdentifier(node)
        && blocked.has(node.text)
        && identifierIsReference(ts, node)
        && !locallyDeclared(node)) {
      findings.push(importFinding(
        sourceFile,
        node,
        "VF_PLUGIN_HOST_IO",
        `plugin '${owner.id}' cannot access host primitive '${node.text}'; use a host_extension`,
      ));
    }
    visitChildren(ts, node, visit);
  }
  visit(sourceFile);
  return findings;
}

function auditUnclassifiedHiddenWork(ts, sourceFile, checker, policy) {
  const owner = ownerFor(ts, sourceFile.fileName, policy);
  if (!owner || owner.kind !== "source") return [];
  const findings = [];
  function callName(node) {
    if (!ts.isCallExpression(node)) return "";
    if (ts.isIdentifier(node.expression)) return node.expression.text;
    if (ts.isPropertyAccessExpression(node.expression)) {
      return node.expression.name.text;
    }
    return "";
  }
  function visit(node) {
    if (ts.isCallExpression(node)) {
      const name = callName(node);
      if (new Set([
        "addEventListener", "eventOn", "on", "once", "setInterval",
        "setTimeout",
      ]).has(name)) {
        findings.push(importFinding(
          sourceFile,
          node,
          "VF_SOURCE_LISTENER_UNOWNED",
          `source '${owner.id}' registers a long-lived listener or timer without a host_extension owner`,
        ));
      }
      let returnsPromise = false;
      try {
        const type = checker.getTypeAtLocation(node);
        returnsPromise = promiseLikeType(
          ts,
          checker,
          type,
          checker.typeToString(type),
        );
      } catch {
        // Syntax-based Promise chain checks remain available below.
      }
      const discardedChain = ts.isPropertyAccessExpression(node.expression)
        && new Set(["then", "catch", "finally"]).has(node.expression.name.text)
        && ts.isExpressionStatement(node.parent);
      if ((returnsPromise && ts.isExpressionStatement(node.parent))
          || discardedChain) {
        findings.push(importFinding(
          sourceFile,
          node,
          "VF_PROMISE_UNOWNED",
          `source '${owner.id}' discards Promise work without a workflow or TaskPlan owner`,
        ));
      }
    }
    if (ts.isVoidExpression(node)) {
      try {
        const type = checker.getTypeAtLocation(node.expression);
        if (promiseLikeType(ts, checker, type, checker.typeToString(type))) {
          findings.push(importFinding(
            sourceFile,
            node,
            "VF_PROMISE_UNOWNED",
            `source '${owner.id}' discards Promise work with void`,
          ));
        }
      } catch {
        // A plain void remains legal when Promise ownership is not provable.
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

async function auditContracts(ts, request, extraFiles = [], checkDiagnostics = true) {
  const files = [...new Set([...(request.typecheckFiles || []), ...extraFiles])]
    .map((item) => path.resolve(item));
  const contractFiles = new Set(
    (request.contractCheckFiles || []).map((item) => path.resolve(item)),
  );
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
    // A target-neutral quality pass needs type facts from both common host
    // families so ownership checks can prove that browser-only calls such as
    // fetch() return Promise values.  These libraries are facts for the
    // VibeFlow ownership analysis only: ordinary TypeScript diagnostics are
    // still restricted to generated ABI contract files below.
    lib: request.target === "node"
      ? ["ES2022"]
      : ["ES2022", "DOM", "DOM.Iterable"],
  };
  let program;
  let checker;
  let project = null;
  let sourceFiles;
  let diagnostics = [];
  let dispose = () => {};
  let temporaryConfigRoot = null;
  if (ts.__native) {
    const configDirectory = request.workflowEntry
      ? path.dirname(request.workflowEntry)
      : (temporaryConfigRoot = await mkdtemp(
          path.join(os.tmpdir(), "vibeflow-audit-ts-"),
        ));
    const configPath = path.join(
      configDirectory,
      checkDiagnostics
        ? "tsconfig.vibeflow.json"
        : "tsconfig.vibeflow-closure.json",
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
        diagnostics = sourceFiles
          .filter((item) => contractFiles.has(path.resolve(item.fileName)))
          .flatMap((item) => [
            ...program.getSyntacticDiagnostics(item.fileName),
            ...program.getBindDiagnostics(item.fileName),
            ...program.getSemanticDiagnostics(item.fileName),
          ])
          .map((item) => diagnosticText(ts, item));
      }
    } catch (cause) {
      try {
        snapshot?.dispose();
      } finally {
        api.close();
        if (temporaryConfigRoot) {
          await rm(temporaryConfigRoot, { recursive: true, force: true });
          temporaryConfigRoot = null;
        }
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
      lib: request.target === "node"
        ? ["lib.es2022.d.ts"]
        : ["lib.es2022.d.ts", "lib.dom.d.ts", "lib.dom.iterable.d.ts"],
    };
    program = ts.createProgram({ rootNames: files, options: compilerOptions });
    checker = program.getTypeChecker();
    sourceFiles = program.getSourceFiles();
    diagnostics = checkDiagnostics
      ? sourceFiles
        .filter((item) => contractFiles.has(path.resolve(item.fileName)))
        .flatMap((item) => ts.getPreEmitDiagnostics(program, item))
        .map((item) => diagnosticText(ts, item))
      : [];
  }
  const policy = normalizeImportPolicy(
    request.importPolicy,
    request.packageRoot,
  );
  deriveTransitiveOwners(
    ts,
    sourceFiles,
    checker,
    project,
    policy,
  );
  const rootFiles = new Set(files.map((item) => path.resolve(item)));
  try {
    for (const sourceFile of sourceFiles) {
      if (sourceFile.isDeclarationFile) continue;
      const owned = ownerFor(ts, sourceFile.fileName, policy);
      if (!owned && !rootFiles.has(path.resolve(sourceFile.fileName))) continue;
      findings.push(...auditParsedSource(ts, sourceFile, request.profile));
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
      findings.push(...auditBaseLibHostIo(
        ts,
        sourceFile,
        checker,
        project,
        policy,
      ));
      findings.push(...auditPluginHostIo(
        ts,
        sourceFile,
        checker,
        project,
        policy,
      ));
      findings.push(...auditUnclassifiedHiddenWork(
        ts,
        sourceFile,
        checker,
        policy,
      ));
    }
    if (findings.length) {
      const diagnosticsWithOwners = findings.map((finding) => {
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
  } finally {
    try {
      dispose();
    } finally {
      if (temporaryConfigRoot) {
        await rm(temporaryConfigRoot, { recursive: true, force: true });
      }
    }
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
    plugins: [workflowVirtualPlugin(request.workflowEntry)],
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

async function main() {
  if (process.argv.length !== 3) {
    fail("VF_PROTOCOL", "usage: node toolchain_driver.mjs REQUEST.json");
  }
  const requestPath = path.resolve(process.argv[2]);
  const request = JSON.parse(await readFile(requestPath, "utf8"));
  const packageRoot = path.resolve(request.packageRoot);
  const tools = await packageTools(packageRoot, {
    requireEsbuild: request.command !== "audit",
  });
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
