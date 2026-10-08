// Ownership includes erased type references; runtime/effect visitors do not.
function is(ts, node, name) {
  const predicate = ts[`is${name}`] || ts[`is${name}Declaration`];
  return typeof predicate === "function" ? predicate(node) : node?.kind === ts.SyntaxKind[name];
}

function reference(ts, node) {
  const parent = node.parent;
  if (!parent) return true;
  if ((ts.isPropertyAccessExpression(parent) && parent.name === node)
      || (is(ts, parent, "QualifiedName") && parent.right === node)
      || ((ts.isPropertyAssignment(parent) || ts.isPropertyDeclaration(parent)
        || is(ts, parent, "PropertySignature") || ts.isMethodDeclaration(parent)
        || is(ts, parent, "MethodSignature") || ts.isVariableDeclaration(parent)
        || is(ts, parent, "Parameter") || ts.isFunctionDeclaration(parent)
        || ts.isFunctionExpression(parent) || ts.isClassDeclaration(parent)
        || ts.isTypeAliasDeclaration(parent) || ts.isInterfaceDeclaration(parent)
        || is(ts, parent, "TypeParameter") ) && parent.name === node)
      || ts.isImportSpecifier(parent) || ts.isExportSpecifier(parent)
      || (ts.isBindingElement(parent) && (parent.name === node || parent.propertyName === node))) return false;
  return true;
}

function functionBoundary(ts, node) {
  return ts.isFunctionDeclaration(node) || ts.isFunctionExpression(node)
    || ts.isArrowFunction(node) || ts.isMethodDeclaration(node)
    || ts.isGetAccessorDeclaration(node) || ts.isSetAccessorDeclaration(node)
    || is(ts, node, "Constructor");
}

function classInitialization(ts, node) {
  const roots = [...(node.heritageClauses || [])];
  for (const modifier of node.modifiers || []) if (is(ts, modifier, "Decorator")) roots.push(modifier);
  for (const member of node.members || []) {
    for (const modifier of member.modifiers || []) if (is(ts, modifier, "Decorator")) roots.push(modifier);
    if (member.name && ts.isComputedPropertyName(member.name)) roots.push(member.name.expression);
    if (member.modifiers?.some(item => item.kind === ts.SyntaxKind.StaticKeyword) && member.initializer) roots.push(member.initializer);
    if (is(ts, member, "ClassStaticBlockDeclaration")) roots.push(member.body);
  }
  return roots;
}

export function ownershipImportStatements(ts, sourceFile, checker, project, {
  implementation, declarations, unwrap, sdkDeclaration,
}) {
  const entry = new Set(), initialization = new Set();
  const imports = sourceFile.statements.filter(node => ts.isImportDeclaration(node) || ts.isImportEqualsDeclaration(node));
  if (!implementation) return {entry: new Set(imports.map(node => node.moduleSpecifier || node)), initialization};

  function collect(roots, result, initializing = false) {
    const seen = new Set(), pending = roots.map(node => ({node, invoked: false}));
    function enqueue(node, invoked = false) {
      if (node && !seen.has(node)) pending.push({node, invoked});
    }
    function visit(node, root = false) {
      if (!node) return;
      if (initializing && functionBoundary(ts, node) && !root) return;
      if (initializing && ts.isClassDeclaration(node) && !root) {
        for (const child of classInitialization(ts, node)) visit(child);
        return;
      }
      if (ts.isIdentifier(node) && reference(ts, node)) {
        for (const declaration of declarations(checker.getSymbolAtLocation(node), project)) {
          if (declaration.getSourceFile() !== sourceFile) continue;
          let statement = declaration;
          while (statement.parent && statement.parent !== sourceFile) statement = statement.parent;
          if (ts.isImportDeclaration(statement) || ts.isImportEqualsDeclaration(statement)) { result.add(statement.moduleSpecifier || statement); continue; }
          const called = (ts.isCallExpression(node.parent) || ts.isNewExpression(node.parent)) && node.parent.expression === node;
          if (functionBoundary(ts, declaration)) {
            if (!initializing || called) enqueue(declaration, called);
          } else if (ts.isVariableDeclaration(declaration)) {
            const value = unwrap(ts, declaration.initializer);
            if (sdkDeclaration(ts, sourceFile, value)) continue;
            if (declaration.type) enqueue(declaration.type);
            if (value && (!initializing || !functionBoundary(ts, value) || called)) enqueue(value, called);
          } else if (ts.isTypeAliasDeclaration(declaration) || ts.isInterfaceDeclaration(declaration)) {
            enqueue(declaration);
          } else if (ts.isClassDeclaration(declaration)) {
            if (!initializing || called) enqueue(declaration, called);
            else for (const child of classInitialization(ts, declaration)) enqueue(child);
          }
        }
      }
      if (initializing && ts.isCallExpression(node)) {
        const value = unwrap(ts, node.expression);
        if (value && functionBoundary(ts, value)) enqueue(value, true);
        for (const declaration of declarations(checker.getSymbolAtLocation(node.expression), project)) {
          if (declaration.getSourceFile() === sourceFile && functionBoundary(ts, declaration)) enqueue(declaration, true);
        }
      }
      if (ts.isCallExpression(node)) {
        const dynamic = node.expression.kind === ts.SyntaxKind.ImportKeyword;
        const require = ts.isIdentifier(node.expression) && node.expression.text === "require";
        const argument = node.arguments[0];
        if ((dynamic || require) && argument && (is(ts, argument, "StringLiteral") || is(ts, argument, "NoSubstitutionTemplateLiteral"))) result.add(argument);
      }
      if (typeof ts.forEachChild === "function") ts.forEachChild(node, child => visit(child));
      else node.forEachChild(child => visit(child));
    }
    while (pending.length) {
      const {node, invoked} = pending.pop();
      if (seen.has(node)) continue;
      seen.add(node);
      if (initializing && functionBoundary(ts, node) && !invoked) continue;
      if (initializing && ts.isClassDeclaration(node) && invoked) {
        for (const child of classInitialization(ts, node)) enqueue(child);
        for (const member of node.members || []) {
          if (is(ts, member, "Constructor")) enqueue(member, true);
          else if (member.initializer) enqueue(member.initializer);
        }
        continue;
      }
      visit(node, true);
    }
  }

  collect([implementation], entry);
  const roots = [];
  for (const statement of sourceFile.statements) {
    if (ts.isImportDeclaration(statement)) {
      if (!statement.importClause) initialization.add(statement.moduleSpecifier);
    } else if (ts.isExportDeclaration(statement) && statement.moduleSpecifier) {
      initialization.add(statement.moduleSpecifier);
    } else if (ts.isVariableStatement(statement)) {
      for (const declaration of statement.declarationList.declarations) {
        const value = unwrap(ts, declaration.initializer);
        if (sdkDeclaration(ts, sourceFile, value) || (value && functionBoundary(ts, value))) continue;
        if (declaration.type) roots.push(declaration.type);
        if (value) roots.push(value);
      }
    } else if (ts.isClassDeclaration(statement)) {
      roots.push(...classInitialization(ts, statement));
    } else if (!ts.isFunctionDeclaration(statement) && !ts.isInterfaceDeclaration(statement)
        && !ts.isTypeAliasDeclaration(statement) && !ts.isImportEqualsDeclaration(statement)) {
      roots.push(statement);
    }
  }
  collect(roots, initialization, true);
  return {entry, initialization};
}
