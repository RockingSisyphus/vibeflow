"""Resolve source-visible class members with Python's C3 precedence, without imports."""

import ast


def class_members(symbol, symbols, imports):
    from vibeflow.targets.python.quality.source_context import _resolve_call

    if not isinstance(symbol._node, ast.ClassDef):
        return {}
    by_id = {item.id: item for item in symbols}
    aliases = {}
    for item in imports:
        if item.resolved_path:
            aliases.setdefault(item.path, {})[item.alias] = (item.resolved_path, item.symbol)
    memo, active = {}, set()

    def linearize(current):
        if current.id in memo:
            return memo[current.id]
        if current.id in active:
            raise ValueError("cyclic class inheritance: " + current.name)
        active.add(current.id)
        bases = []
        for expression in current._node.bases:
            target = _resolve_call(expression, current, aliases.get(current.path, {}), by_id)
            base = by_id.get(target)
            if base is not None and isinstance(base._node, ast.ClassDef):
                bases.append(base)
        sequences = [list(linearize(base)) for base in bases] + [list(bases)]
        result = [current]
        while any(sequences):
            sequences = [items for items in sequences if items]
            head = next((items[0] for items in sequences if not any(
                items[0].id in {item.id for item in other[1:]} for other in sequences)), None)
            if head is None:
                raise ValueError("inconsistent class inheritance: " + current.name)
            result.append(head)
            for items in sequences:
                if items[0].id == head.id:
                    items.pop(0)
        active.remove(current.id)
        memo[current.id] = tuple(result)
        return memo[current.id]

    members, shadowed = {}, set()
    for owner in linearize(symbol):
        local = {}
        for statement in owner._node.body:
            if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef)):
                local[statement.name] = by_id[f"{owner.path}:{owner.name}.{statement.name}"]
            elif isinstance(statement, (ast.Assign, ast.AnnAssign)):
                targets = statement.targets if isinstance(statement, ast.Assign) else (statement.target,)
                for target in targets:
                    for item in ast.walk(target):
                        if isinstance(item, ast.Name) and isinstance(item.ctx, ast.Store) and statement.value is not None:
                            local[item.id] = None
        members.update({name:item for name,item in local.items() if name not in shadowed and item is not None})
        shadowed.update(local)
    return members
