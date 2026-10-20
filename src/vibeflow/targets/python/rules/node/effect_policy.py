from __future__ import annotations

import ast

from vibeflow.targets.python.nodetypes.protocols import EFFECT_SCOPE_GLOBAL_STATE, EFFECT_SCOPE_PYTHON_IO, EFFECT_SCOPE_TERMINAL
from vibeflow.targets.python.quality.source_analysis.ast_facts import (
    path_effect_call_name,
    qualified_call_name,
)
from vibeflow.targets.python.quality.source_analysis.ast_facts import call_name as _call_name, is_immutable_constant, module_matches
from vibeflow.targets.python.rules.node.policy import BANNED_ATTR_CALLS, BANNED_IMPORT_ROOTS, PurityPolicy


BUILTIN_OPEN_CALLS = frozenset({"open", "builtins.open"})
HARD_PROCESS_TERMINATION_CALLS = frozenset(
    {
        "os._exit",
        "os.abort",
        "os.kill",
        "os.killpg",
        "signal.raise_signal",
    }
)
SYSTEM_EXIT_CALLS = frozenset(
    {
        "SystemExit",
        "builtins.SystemExit",
        "builtins.exit",
        "builtins.quit",
        "exit",
        "quit",
        "sys.exit",
    }
)
SYSTEM_EXIT_SCOPES = frozenset({EFFECT_SCOPE_TERMINAL, EFFECT_SCOPE_PYTHON_IO})
TERMINAL_CALLS = frozenset({"input", "builtins.input", "print", "builtins.print"})
TERMINAL_STREAMS = ("sys.stdin", "sys.stdout", "sys.stderr")
PYTHON_IO_IMPORT_ROOTS = frozenset(
    (BANNED_IMPORT_ROOTS - {"importlib"})
    | {
        "argparse",
        "dbm",
        "ftplib",
        "logging",
        "pty",
        "posix",
        "smtplib",
        "tempfile",
        "webbrowser",
        "xmlrpc",
    }
)
PYTHON_IO_IMPORT_MODULES = frozenset({"http.client", "http.server"})
PYTHON_IO_CALL_PREFIXES = ("http.client.", "http.server.", "io.open", "pty.")
COMMON_LIBRARY_IO_CALLS = frozenset(
    {
        "PIL.Image.open",
        "joblib.dump",
        "joblib.load",
        "numpy.fromfile",
        "numpy.load",
        "numpy.loadtxt",
        "numpy.memmap",
        "numpy.save",
        "numpy.savetxt",
        "numpy.savez",
        "numpy.savez_compressed",
        "pickle.dump",
        "pickle.load",
        "scipy.io.loadmat",
        "scipy.io.savemat",
        "soundfile.read",
        "soundfile.write",
        "torch.hub.download_url_to_file",
        "torch.hub.load",
        "torch.jit.load",
        "torch.jit.save",
        "torch.load",
        "torch.save",
    }
)
THREAD_PROCESS_CALLS = frozenset(
    {
        "_thread.start_new_thread",
        "asyncio.to_thread",
        "concurrent.futures.ProcessPoolExecutor",
        "concurrent.futures.ThreadPoolExecutor",
        "multiprocessing.Pool",
        "multiprocessing.Process",
        "os.fork",
        "os.forkpty",
        "os.posix_spawn",
        "os.posix_spawnp",
        "threading.Thread",
    }
)
AMBIENT_MUTATING_METHODS = frozenset(
    {
        "add",
        "append",
        "clear",
        "discard",
        "extend",
        "insert",
        "pop",
        "popitem",
        "remove",
        "register",
        "setdefault",
        "sort",
        "update",
        "unregister",
    }
)
FORBIDDEN_AMBIENT_STATE_PREFIXES = (
    "builtins.",
    "os.environ",
    "sys.meta_path",
    "sys.modules",
    "sys.path",
    "sys.path_hooks",
)
HARD_PROCESS_STATE_PREFIXES = (
    "os.environ",
    "sys.meta_path",
    "sys.modules",
    "sys.path",
    "sys.path_hooks",
)



PURE_PATH_CLASSES = frozenset({"PurePath", "PurePosixPath", "PureWindowsPath"})


def import_violation_code(module: str, *, effect_scope: str, policy: PurityPolicy,
                          imported_names: set[str] | None = None) -> str:
    """Effect categories cannot be lifted by configurable import policy."""
    effect = effect_import_violation_code(module, effect_scope=effect_scope, imported_names=imported_names)
    if effect:
        return effect
    if module == "urllib" and imported_names == {"parse"}:
        module = "urllib.parse"
    return policy_import_violation_code(module, policy=policy)


def policy_import_violation_code(module: str, *, policy: PurityPolicy) -> str:
    """Configurable import decisions, independent of effect classification."""
    return "banned_import" if _policy_bans_import(module, policy) else ""


def effect_import_violation_code(module: str, *, effect_scope: str,
                                 imported_names: set[str] | None = None) -> str:
    root = module.split(".", 1)[0]
    if module == "urllib" and imported_names == {"parse"}:
        return ""
    if module == "pathlib" and imported_names and imported_names <= PURE_PATH_CLASSES:
        return ""
    if module == "urllib.parse" or module.startswith("urllib.parse."):
        return ""
    if root in PYTHON_IO_IMPORT_ROOTS or any(
        module == effect_module or module.startswith(f"{effect_module}.")
        for effect_module in PYTHON_IO_IMPORT_MODULES
    ):
        if effect_scope == EFFECT_SCOPE_PYTHON_IO:
            return ""
        if effect_scope == EFFECT_SCOPE_TERMINAL and root == "argparse":
            return ""
        return "effect_import"
    return ""


def call_violation(
    node: ast.Call,
    *,
    aliases: dict[str, str],
    effect_scope: str,
    imported_roots: set[str] | frozenset[str] = frozenset(),
    module_state_names: set[str] | frozenset[str] = frozenset(),
    local_names: set[str] | frozenset[str] = frozenset(),
    source_resolved: bool = False,
    local_reference: bool = False,
) -> tuple[str, str]:
    """Return ``(code, name)`` for a denied call, keeping non-effect rules stable."""

    candidate = qualified_call_name(node.func, aliases) or _call_name(node.func)
    raw_root = _call_name(node.func).split(".", 1)[0]
    local_receiver = local_reference or raw_root in local_names and raw_root not in aliases
    if local_receiver or source_resolved:
        return "", ""
    if any(candidate == prefix or candidate.startswith(prefix + ".") for prefix in HARD_PROCESS_STATE_PREFIXES):
        return "effect_call", candidate
    if candidate in HARD_PROCESS_TERMINATION_CALLS:
        return "effect_call", candidate
    if is_system_exit_call(candidate):
        return ("", "") if effect_scope in SYSTEM_EXIT_SCOPES else ("effect_call", candidate)
    ambient = ambient_state_call_name(node, aliases=aliases, module_state_names=module_state_names, local_names=local_names)
    if ambient and effect_scope != EFFECT_SCOPE_GLOBAL_STATE:
        return "effect_call", ambient
    if candidate in {"random.seed", "random.setstate", "torch.manual_seed", "sys.setrecursionlimit"}:
        return ("", "") if effect_scope == EFFECT_SCOPE_GLOBAL_STATE else ("effect_call", candidate)
    if candidate.startswith("argparse.ArgumentParser.") and candidate.rsplit(".", 1)[-1] in {
            "parse_args", "parse_known_args", "parse_intermixed_args", "parse_known_intermixed_args"}:
        argv = node.args[0] if node.args else next((item.value for item in node.keywords if item.arg == "args"), None)
        if argv is None or isinstance(argv, ast.Constant) and argv.value is None:
            return "effect_call", candidate + " reads sys.argv; use the declared cli.argv input"
        return "", ""
    if candidate == "argparse.FileType":
        return ("", "") if effect_scope == EFFECT_SCOPE_PYTHON_IO else ("effect_call", candidate)
    if effect_scope == EFFECT_SCOPE_PYTHON_IO:
        return "", ""
    if is_terminal_call(candidate):
        if effect_scope == EFFECT_SCOPE_TERMINAL and terminal_print_target_is_allowed(node, candidate, aliases):
            return "", ""
        return "effect_call", candidate
    path_effect = path_effect_call_name(node, aliases)
    if path_effect or _is_python_io_call(candidate):
        return "effect_call", path_effect or candidate
    return "", ""


def ambient_state_call_name(
    node: ast.Call,
    *,
    aliases: dict[str, str],
    imported_roots: set[str] | frozenset[str] = frozenset(),
    module_state_names: set[str] | frozenset[str] = frozenset(),
    local_names: set[str] | frozenset[str] = frozenset(),
) -> str:
    candidate = qualified_call_name(node.func, aliases) or _call_name(node.func)
    raw_root = _call_name(node.func).split(".", 1)[0]
    if raw_root in local_names and raw_root not in aliases:
        return ""
    root, _, leaf = candidate.partition(".")
    return candidate if root in module_state_names and leaf in AMBIENT_MUTATING_METHODS else ""


def ambient_assignment_is_forbidden(name: str) -> bool:
    return any(name == prefix.rstrip(".") or name.startswith(prefix) for prefix in FORBIDDEN_AMBIENT_STATE_PREFIXES)


def is_terminal_call(name: str) -> bool:
    return name in TERMINAL_CALLS or name.startswith("argparse.") or any(
        name == stream or name.startswith(f"{stream}.") for stream in TERMINAL_STREAMS
    )


def is_system_exit_call(name: str, raw_name: str = "") -> bool:
    return name in SYSTEM_EXIT_CALLS or raw_name in SYSTEM_EXIT_CALLS


def system_exit_reference(node: ast.AST | None, aliases: dict[str, str]) -> str:
    if node is None:
        return ""
    target = node.func if isinstance(node, ast.Call) else node
    name = qualified_call_name(target, aliases)
    raw_name = _call_name(target)
    return (name or raw_name) if is_system_exit_call(name, raw_name) else ""


def system_exit_is_forbidden(effect_scope: str) -> bool:
    return effect_scope not in SYSTEM_EXIT_SCOPES


def terminal_print_target_is_allowed(node: ast.Call, name: str, aliases: dict[str, str]) -> bool:
    if name not in {"print", "builtins.print"}:
        return True
    file_values = [keyword.value for keyword in node.keywords if keyword.arg == "file"]
    if not file_values:
        return True
    target = qualified_call_name(file_values[0], aliases)
    return target in {"sys.stdout", "sys.stderr"}


def terminal_stream_reference(node: ast.Attribute, aliases: dict[str, str]) -> str:
    name = qualified_call_name(node, aliases)
    return name if name in TERMINAL_STREAMS else ""


def process_argv_reference(node: ast.Attribute, aliases: dict[str, str]) -> str:
    name = qualified_call_name(node, aliases)
    return name if name == "sys.argv" else ""


def process_argv_import_is_forbidden(module: str, names: set[str]) -> bool:
    return module == "sys" and "argv" in names


def terminal_stream_import_is_forbidden(module: str, names: set[str], *, effect_scope: str) -> bool:
    return (
        module == "sys"
        and bool(names & {"stdin", "stdout", "stderr"})
        and terminal_stream_is_forbidden(effect_scope)
    )


def from_import_effect_is_forbidden(module: str, names: set[str], *, effect_scope: str) -> bool:
    if effect_scope == EFFECT_SCOPE_PYTHON_IO:
        return False
    qualified = {f"{module}.{name}" for name in names}
    return bool(
        qualified & {"http.client", "http.server", "io.open"}
        or module in {"http.client", "http.server", "pty"}
    )


def terminal_stream_is_forbidden(effect_scope: str) -> bool:
    return effect_scope not in {EFFECT_SCOPE_TERMINAL, EFFECT_SCOPE_PYTHON_IO}


def _policy_bans_import(module: str, policy: PurityPolicy) -> bool:
    return is_banned_import(
        module,
        allowed_roots=policy.allowed_import_roots,
        banned_roots=policy.banned_import_roots,
        allowed_modules=policy.allowed_import_modules,
        banned_modules=policy.banned_import_modules,
    )


def _is_python_io_call(candidate: str) -> bool:
    """Only named external operations; unknown receivers are outside coverage."""
    return (candidate in BUILTIN_OPEN_CALLS or candidate in BANNED_ATTR_CALLS
        or candidate in COMMON_LIBRARY_IO_CALLS
        or candidate in THREAD_PROCESS_CALLS
        or any(candidate.startswith(prefix) for prefix in PYTHON_IO_CALL_PREFIXES))


__all__ = [
    "ambient_assignment_is_forbidden",
    "ambient_state_call_name",
    "call_violation",
    "from_import_effect_is_forbidden",
    "import_violation_code",
    "process_argv_import_is_forbidden",
    "process_argv_reference",
    "system_exit_is_forbidden",
    "system_exit_reference",
    "terminal_stream_import_is_forbidden",
    "terminal_stream_is_forbidden",
    "terminal_stream_reference",
]


def module_assignment_is_allowed(node: ast.Assign | ast.AnnAssign) -> bool:
    value = node.value
    if value is None:
        return True
    return is_immutable_constant(value)


def is_banned_import(module: str, *, allowed_roots: tuple[str, ...], banned_roots: tuple[str, ...], allowed_modules: tuple[str, ...], banned_modules: tuple[str, ...]) -> bool:
    root = module.split(".", 1)[0]
    if module_matches(module, banned_modules):
        return True
    if module_matches(module, allowed_modules):
        return False
    return root in set(banned_roots) and root not in set(allowed_roots)
