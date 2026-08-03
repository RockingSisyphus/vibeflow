from __future__ import annotations

import ast

from vibeflow.targets.python.project.node import EFFECT_SCOPE_GLOBAL_STATE, EFFECT_SCOPE_PYTHON_IO, EFFECT_SCOPE_TERMINAL
from vibeflow.targets.python.quality.source_analysis.ast_rules import (
    is_banned_import,
    path_effect_call_name,
    qualified_call_name,
    qualified_reference_name,
)
from vibeflow.targets.python.quality.source_analysis.helpers import _call_name, _matches_prefix
from vibeflow.targets.python.quality.source_analysis.types import BANNED_ATTR_CALLS, BANNED_CALL_NAMES, BANNED_IMPORT_ROOTS, PurityPolicy


DYNAMIC_CODE_CALLS = frozenset(
    {
        "__import__",
        "builtins.__import__",
        "compile",
        "builtins.compile",
        "eval",
        "builtins.eval",
        "exec",
        "builtins.exec",
        "importlib.import_module",
        "importlib.reload",
        "runpy.run_module",
        "runpy.run_path",
    }
)
DYNAMIC_NAMESPACE_CALLS = frozenset({"builtins.globals", "builtins.locals", "globals", "locals"})
SENSITIVE_REFLECTION_ROOTS = frozenset(
    {
        "builtins",
        "cffi",
        "ctypes",
        "importlib",
        "os",
        "socket",
        "subprocess",
    }
)
HARD_FORBIDDEN_IMPORT_ROOTS = frozenset({"_ctypes", "cffi", "ctypes"})
HARD_FFI_CALLS = frozenset(
    {
        "cffi.FFI",
        "ctypes.CDLL",
        "ctypes.LibraryLoader",
        "ctypes.OleDLL",
        "ctypes.PyDLL",
        "ctypes.WinDLL",
        "numpy.ctypeslib.load_library",
        "torch.classes.load_library",
        "torch.ops.load_library",
        "torch.utils.cpp_extension.load",
        "torch.utils.cpp_extension.load_inline",
    }
)
HARD_FFI_LEAVES = frozenset({"CDLL", "LoadLibrary", "OleDLL", "PyDLL", "WinDLL", "dlopen"})
CALLBACK_INJECTION_CALLS = frozenset(
    {
        "atexit.register",
        "atexit.unregister",
        "signal.signal",
        "sys.addaudithook",
        "sys.set_asyncgen_hooks",
        "sys.setprofile",
        "sys.settrace",
        "threading.setprofile",
        "threading.settrace",
    }
)
ARGPARSE_FILETYPE_CALLS = frozenset({"argparse.FileType"})
ARGPARSE_GLOBAL_ARGV_METHODS = frozenset(
    {
        "parse_args",
        "parse_intermixed_args",
        "parse_known_args",
        "parse_known_intermixed_args",
    }
)
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
    (BANNED_IMPORT_ROOTS - {"boundary", "boundaries", "importlib"})
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
AMBIENT_STATE_LEAVES = frozenset(
    {
        "autocast",
        "detect_anomaly",
        "filterwarnings",
        "flags",
        "freeze",
        "inference_mode",
        "no_grad",
        "simplefilter",
        "unfreeze",
    }
)
AMBIENT_STATE_PREFIXES = (
    "clear_",
    "disable",
    "empty_",
    "enable",
    "manual_seed",
    "reset",
    "seed",
    "set",
    "use_",
)
AMBIENT_CONTAINER_NAMES = frozenset(
    {
        "cache",
        "caches",
        "config",
        "filters",
        "flags",
        "hooks",
        "options",
        "registries",
        "registry",
        "settings",
        "state",
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
IO_METHOD_NAMES = frozenset(
    {
        "close",
        "commit",
        "communicate",
        "connect",
        "cursor",
        "execute",
        "executemany",
        "flush",
        "read",
        "read_bytes",
        "read_text",
        "readline",
        "readlines",
        "recv",
        "recvfrom",
        "rollback",
        "send",
        "sendall",
        "truncate",
        "write",
        "write_bytes",
        "write_text",
        "writelines",
    }
)
PROCESS_CONTROL_CALLS = frozenset({"time.sleep"})


def import_violation_code(module: str, *, effect_scope: str, policy: PurityPolicy) -> str:
    """Return an absolute effect code or a legacy policy import code."""

    root = module.split(".", 1)[0]
    if root in HARD_FORBIDDEN_IMPORT_ROOTS:
        return "effect_import"
    if module == "urllib.parse" or module.startswith("urllib.parse."):
        return "banned_import" if _policy_bans_import(module, policy) else ""
    if root in PYTHON_IO_IMPORT_ROOTS or any(
        module == effect_module or module.startswith(f"{effect_module}.")
        for effect_module in PYTHON_IO_IMPORT_MODULES
    ):
        if effect_scope == EFFECT_SCOPE_PYTHON_IO:
            return ""
        if effect_scope == EFFECT_SCOPE_TERMINAL and root == "argparse":
            return ""
        return "effect_import"
    return "banned_import" if _policy_bans_import(module, policy) else ""


def call_violation(
    node: ast.Call,
    *,
    aliases: dict[str, str],
    effect_scope: str,
    imported_roots: set[str] | frozenset[str] = frozenset(),
    module_state_names: set[str] | frozenset[str] = frozenset(),
    local_names: set[str] | frozenset[str] = frozenset(),
) -> tuple[str, str]:
    """Return ``(code, name)`` for a denied call, keeping non-effect rules stable."""

    name = qualified_call_name(node.func, aliases)
    raw_name = _call_name(node.func)
    candidate = name or raw_name
    if candidate in DYNAMIC_CODE_CALLS or raw_name in DYNAMIC_CODE_CALLS or candidate in DYNAMIC_NAMESPACE_CALLS:
        return "banned_call", candidate
    dynamic_reflection = _dynamic_reflection_call_name(node, aliases, imported_roots)
    if dynamic_reflection:
        return "banned_call", dynamic_reflection
    leaf = candidate.rsplit(".", 1)[-1]
    if candidate in HARD_FFI_CALLS or raw_name in HARD_FFI_CALLS or leaf in HARD_FFI_LEAVES:
        return "effect_call", candidate
    if candidate in CALLBACK_INJECTION_CALLS or raw_name in CALLBACK_INJECTION_CALLS:
        return "effect_call", candidate
    if any(candidate == prefix or candidate.startswith(f"{prefix}.") for prefix in HARD_PROCESS_STATE_PREFIXES):
        return "effect_call", candidate
    if candidate in HARD_PROCESS_TERMINATION_CALLS or raw_name in HARD_PROCESS_TERMINATION_CALLS:
        return "effect_call", candidate
    if is_system_exit_call(candidate, raw_name):
        if effect_scope in SYSTEM_EXIT_SCOPES:
            return "", ""
        return "effect_call", candidate
    argparse_violation = _argparse_violation(node, candidate, raw_name)
    if argparse_violation:
        return "effect_call", argparse_violation
    ambient_state = ambient_state_call_name(
        node,
        aliases=aliases,
        imported_roots=imported_roots,
        module_state_names=module_state_names,
        local_names=local_names,
    )
    if ambient_state:
        if effect_scope == EFFECT_SCOPE_GLOBAL_STATE:
            return "", ""
        return "effect_call", ambient_state
    if effect_scope == EFFECT_SCOPE_PYTHON_IO:
        return "", ""
    if candidate == "urllib.parse" or candidate.startswith("urllib.parse."):
        return "", ""
    if is_terminal_call(candidate):
        if effect_scope == EFFECT_SCOPE_TERMINAL and terminal_print_target_is_allowed(node, candidate, aliases):
            return "", ""
        return "effect_call", candidate
    path_effect = path_effect_call_name(node, aliases)
    if path_effect:
        return "effect_call", path_effect
    root = candidate.split(".", 1)[0]
    if _is_python_io_call(candidate, raw_name, root, leaf):
        return "effect_call", candidate
    return "", ""


def ambient_state_call_name(
    node: ast.Call,
    *,
    aliases: dict[str, str],
    imported_roots: set[str] | frozenset[str] = frozenset(),
    module_state_names: set[str] | frozenset[str] = frozenset(),
    local_names: set[str] | frozenset[str] = frozenset(),
) -> str:
    raw_root = _call_name(node.func).split(".", 1)[0]
    if raw_root in local_names and raw_root not in aliases:
        return ""
    candidate = qualified_call_name(node.func, aliases) or _call_name(node.func)
    root = candidate.split(".", 1)[0]
    if root not in imported_roots and root not in module_state_names:
        return ""
    base = (
        qualified_reference_name(node.func.value, aliases)
        if isinstance(node.func, ast.Attribute)
        else candidate.rsplit(".", 1)[0]
    )
    if not base or ambient_assignment_is_forbidden(base):
        return ""
    leaf = candidate.rsplit(".", 1)[-1]
    if (
        leaf in AMBIENT_STATE_LEAVES
        or leaf.startswith(AMBIENT_STATE_PREFIXES)
    ):
        return candidate
    if leaf in AMBIENT_MUTATING_METHODS and (
        root in module_state_names or _looks_like_ambient_container(base)
    ):
        return candidate
    return ""


def _looks_like_ambient_container(name: str) -> bool:
    leaf = name.rsplit(".", 1)[-1].lower()
    return leaf in AMBIENT_CONTAINER_NAMES or leaf.endswith(
        ("_cache", "_config", "_flags", "_options", "_registry", "_state")
    )


def ambient_assignment_is_forbidden(name: str) -> bool:
    return any(name == prefix.rstrip(".") or name.startswith(prefix) for prefix in FORBIDDEN_AMBIENT_STATE_PREFIXES)


def dynamic_namespace_reference(
    node: ast.Subscript,
    *,
    aliases: dict[str, str],
    imported_roots: set[str] | frozenset[str] = frozenset(),
) -> str:
    if isinstance(node.slice, ast.Constant) and isinstance(node.slice.value, str):
        return ""
    base = qualified_reference_name(node.value, aliases)
    normalized = base[: -len(".__dict__")] if base.endswith(".__dict__") else base
    root = normalized.split(".", 1)[0]
    if root in SENSITIVE_REFLECTION_ROOTS or root in imported_roots:
        return base
    return ""


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
        banned_roots=policy.banned_import_roots or tuple(sorted(BANNED_IMPORT_ROOTS)),
        allowed_modules=policy.allowed_import_modules,
        banned_modules=policy.banned_import_modules,
    )


def _is_python_io_call(candidate: str, raw_name: str, root: str, leaf: str) -> bool:
    return (
        candidate in BUILTIN_OPEN_CALLS
        or raw_name in BUILTIN_OPEN_CALLS
        or candidate in BANNED_CALL_NAMES
        or raw_name in BANNED_CALL_NAMES
        or root in BANNED_CALL_NAMES
        or candidate in BANNED_ATTR_CALLS
        or _matches_prefix(candidate, BANNED_ATTR_CALLS)
        or candidate in PROCESS_CONTROL_CALLS
        or root in PYTHON_IO_IMPORT_ROOTS
        or candidate in COMMON_LIBRARY_IO_CALLS
        or candidate in THREAD_PROCESS_CALLS
        or candidate.startswith("transformers.") and candidate.endswith(".from_pretrained")
        or leaf in IO_METHOD_NAMES
        or any(candidate == prefix.rstrip(".") or candidate.startswith(prefix) for prefix in PYTHON_IO_CALL_PREFIXES)
    )


def _argparse_violation(node: ast.Call, candidate: str, raw_name: str) -> str:
    if candidate in ARGPARSE_FILETYPE_CALLS or raw_name in ARGPARSE_FILETYPE_CALLS:
        return candidate or raw_name
    leaf = (candidate or raw_name).rsplit(".", 1)[-1]
    if leaf not in ARGPARSE_GLOBAL_ARGV_METHODS:
        return ""
    argv = node.args[0] if node.args else next(
        (keyword.value for keyword in node.keywords if keyword.arg == "args"),
        None,
    )
    if argv is None or isinstance(argv, ast.Constant) and argv.value is None:
        return candidate or raw_name
    return ""


def _dynamic_reflection_call_name(
    node: ast.Call,
    aliases: dict[str, str],
    imported_roots: set[str] | frozenset[str],
) -> str:
    function = qualified_call_name(node.func, aliases)
    if function not in {"getattr", "builtins.getattr"} or len(node.args) < 2:
        return ""
    if isinstance(node.args[1], ast.Constant) and isinstance(node.args[1].value, str):
        return ""
    base = qualified_reference_name(node.args[0], aliases)
    root = base.split(".", 1)[0]
    return f"getattr({base}, <dynamic>)" if root in SENSITIVE_REFLECTION_ROOTS or root in imported_roots else ""


__all__ = [
    "ambient_assignment_is_forbidden",
    "ambient_state_call_name",
    "call_violation",
    "dynamic_namespace_reference",
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
