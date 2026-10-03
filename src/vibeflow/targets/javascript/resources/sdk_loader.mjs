/** Record declaration locations before bundling; never serialize functions. */
import {readFile} from "node:fs/promises";
import {fileURLToPath} from "node:url";
const runtime = fileURLToPath(new URL("./sdk.mjs", import.meta.url));
export const sdkTypes = fileURLToPath(new URL("./sdk.d.ts", import.meta.url));

function runtimeDeclarations(ts, tree, program, project, requested) {
  const checker = project?.checker || program?.getTypeChecker?.();
  if (!checker) throw new Error(`source binding unavailable for ${tree.fileName}`);
  const selected = new Set(), pending = [], imports = new Map(), replacements = new Map();
  const names = new Set(requested.map(item => item.export.split(".")[0]));
  const declarations = symbol => (symbol?.declarations || []).map(item => typeof item?.resolve === "function" ? item.resolve(project) : item).filter(Boolean);
  function property(expression, name, seen = new Set()) {
    if (!expression || seen.has(expression)) return null;
    seen.add(expression);
    if (ts.isIdentifier(expression)) {
      const declaration = declarations(checker.getSymbolAtLocation(expression))[0];
      return property(declaration?.initializer, name, seen);
    }
    if (expression.expression && !ts.isCallExpression(expression)) return property(expression.expression, name, seen);
    for (const item of [...(expression.properties || [])].reverse()) {
      if (item.name?.text === name) return item;
      if (ts.isSpreadAssignment(item)) {
        const found = property(item.expression, name, seen);
        if (found) return found;
      }
    }
    return null;
  }
  const top = node => {while (node?.parent && node.parent !== tree) node = node.parent; return node;};
  function include(node) {
    if (!node || selected.has(node)) return;
    selected.add(node); pending.push(node);
  }
  for (const statement of tree.statements) {
    for (const declaration of statement.declarationList?.declarations || []) {
      if (names.has(declaration.name?.text)) {
        const value = declaration.initializer;
        const symbol = checker.getSymbolAtLocation(value?.expression);
        const imported = declarations(symbol).find(item => ts.isImportSpecifier(item));
        const callee = imported ? (imported.propertyName || imported.name)?.text : value?.expression?.name?.text;
        if (callee === "definePlugin") {
          const callbacks = requested.filter(item => item.export.split(".")[0] === declaration.name.text)
            .map(item => property(value.arguments?.[0], item.export.split(".")[1])).filter(Boolean);
          if (!callbacks.length) throw new Error(`runtime callback unavailable: ${declaration.name.text}`);
          replacements.set(declaration, `${declaration.name.text}={${callbacks.map(item => item.getText(tree)).join(",")}}`);
          selected.add(declaration); callbacks.forEach(include);
        } else include(declaration);
      }
    }
    if (names.has(statement.name?.text)) include(statement);
  }
  while (pending.length) {
    const current = pending.pop();
    function visit(node) {
      if (ts.isIdentifier(node)) {
        const symbol = ts.isShorthandPropertyAssignment(node.parent) && node.parent.name === node
          ? checker.getShorthandAssignmentValueSymbol(node.parent)
          : checker.getSymbolAtLocation(node);
        for (const declaration of declarations(symbol)) {
          if (declaration.getSourceFile() !== tree) continue;
          const statement = top(declaration);
          if (ts.isImportDeclaration(statement)) {
            const set = imports.get(statement) || new Set();
            set.add(declaration); imports.set(statement, set);
          } else if (ts.isVariableDeclaration(declaration) && declaration.parent?.parent === statement) include(declaration);
          else if (statement && statement !== current && statement.parent === tree && !ts.isVariableStatement(statement)) include(statement);
        }
      }
      if (ts.forEachChild) ts.forEachChild(node, child => {visit(child);});
      else node.forEachChild(child => {visit(child);});
    }
    visit(current);
  }
  return tree.statements.map(statement => {
    if (ts.isImportDeclaration(statement)) {
      const bindings = imports.get(statement);
      if (!bindings) return "\n".repeat(statement.getText(tree).split("\n").length);
      const clause = statement.importClause, named = clause?.namedBindings;
      const pieces = [];
      if (clause?.name && bindings.has(clause)) pieces.push(clause.name.text);
      if (named?.elements) {
        const used = named.elements.filter(item => bindings.has(item));
        if (used.length) pieces.push(`{${used.map(item => item.getText(tree)).join(",")}}`);
      } else if (named && bindings.has(named)) pieces.push(named.getText(tree));
      return pieces.length ? `import ${pieces.join(",")} from ${statement.moduleSpecifier.getText(tree)};` : "";
    }
    if (ts.isVariableStatement(statement)) {
      const declarations = statement.declarationList.declarations.filter(item => selected.has(item));
      if (!declarations.length) return "";
      const modifiers = (statement.modifiers || []).map(item => item.getText(tree)).join(" ");
      const keyword = statement.declarationList.flags & ts.NodeFlags.Const ? "const" : "let";
      return `${modifiers} ${keyword} ${declarations.map(item => replacements.get(item) || item.getText(tree)).join(",")};`;
    }
    return selected.has(statement) ? statement.getText(tree) : "";
  }).join("\n");
}

export function sdkPlugin(ts, {runtimeBindings = []} = {}) {
  return {name: "vibeflow-plugin-sdk", setup(build) {
    build.onResolve({filter: /^@vibeflow\/plugin$/}, () => ({path: runtime}));
    build.onLoad({filter: /\.(?:[cm]?[jt]s|[jt]sx)$/}, async args => {
      if (args.path === runtime) return;
      const text = await readFile(args.path, "utf8");
      if (!text.includes("@vibeflow/plugin")) return;
      let api, snapshot, tree;
      try {
        let program, project;
        const selected = runtimeBindings.filter(item => item.module === args.path);
        if (ts.createSourceFile && !selected.length) tree = ts.createSourceFile(args.path, text, ts.ScriptTarget.Latest, true);
        else {
          if (ts.API) {
            api = new ts.API({cwd: build.initialOptions.absWorkingDir});
            snapshot = api.updateSnapshot({openFiles: [args.path]});
            project = snapshot.getDefaultProjectForFile(args.path);
            program = project?.program;
          } else program = ts.createProgram([args.path], {allowJs:true, module:ts.ModuleKind.ESNext});
          tree = program?.getSourceFile(args.path);
        }
        if (!tree) throw new Error(`cannot analyze SDK declarations in ${args.path}`);
        if (selected.length) {
          const contents = runtimeDeclarations(ts, tree, program, project, selected);
          return {contents, loader: /\.[cm]?ts$/.test(args.path) ? "ts" : "js"};
        }
        const names = new Set(), namespaces = new Set(), edits = [];
        for (const statement of tree.statements) {
          if (statement.moduleSpecifier?.text !== "@vibeflow/plugin") continue;
          const bindings = statement.importClause?.namedBindings;
          if (bindings?.elements) for (const element of bindings.elements) names.add(element.name.text);
          else if (bindings?.name) namespaces.add(bindings.name.text);
        }
        function visit(node) {
          if (ts.SyntaxKind[node.kind] === "VariableDeclaration" && node.initializer && node.name?.text) {
            const call = node.initializer, expression = call.expression;
            const isSdk = names.has(expression?.text) || (namespaces.has(expression?.expression?.text) && expression?.name);
            if (isSdk && call.arguments?.[0]) {
              const object = call.arguments[0], position = tree.getLineAndCharacterOfPosition(node.getStart(tree));
              const origin = {path: args.path, line: position.line + 1, column: position.character + 1,
                symbol: node.name.text, language: /\.[cm]?tsx?$/.test(args.path) ? "typescript" : "javascript"};
              edits.push({offset: object.end, text: `,__origin:${JSON.stringify(origin)}})`});
              edits.push({offset: object.getStart(tree), text: "({..."});
            }
          }
          if (ts.forEachChild) ts.forEachChild(node, child => {visit(child);});
          else node.forEachChild(child => {visit(child);});
        }
        visit(tree);
        let contents = text;
        for (const edit of edits.sort((a,b) => b.offset - a.offset)) contents = contents.slice(0, edit.offset) + edit.text + contents.slice(edit.offset);
        return {contents, loader: /\.tsx$/.test(args.path) ? "tsx" : /\.jsx$/.test(args.path) ? "jsx" : /\.[cm]?ts$/.test(args.path) ? "ts" : "js"};
      } finally {snapshot?.dispose(); api?.close();}
    });
  }};
}
