"""
Runs one AI-written `def answer(rows)` over a table's rows, with no way out.

The function comes from an LLM whose prompt holds text scraped from the web, so it is treated as hostile:
- before it runs, its syntax tree must use only an allowlist of nodes, names and attributes (no imports, no
  dunders, no file, network or interpreter access);
- it runs in a separate `python -I -S` process with an empty environment (no keys), a time limit, CPU and memory
  limits (RLIMIT on POSIX, a Job Object on Windows), at most two at once, and only `math` and `statistics` in reach.
Run as a script (`python ask_sandbox.py`) it is that process: JSON {source, rows} on stdin, JSON result on stdout.
"""

from __future__ import annotations

import ast
import json
import math
import os
import statistics
import subprocess
import sys
import threading
from typing import Any, Callable

MAX_SOURCE = 4000
TIMEOUT_S = 8
MAX_RESULT_ROWS = 500
MAX_RESULT_BYTES = 1_000_000
MEMORY_LIMIT = 512 * 2**20
# ponytail: one process-wide cap on concurrent children; a per-host pool if this ever runs on several workers.
_SLOTS = threading.BoundedSemaphore(2)

_SAFE_BUILTINS = {
    "abs": abs, "all": all, "any": any, "bool": bool, "dict": dict, "enumerate": enumerate, "filter": filter,
    "float": float, "int": int, "isinstance": isinstance, "len": len, "list": list, "map": map, "max": max,
    "min": min, "range": range, "reversed": reversed, "round": round, "set": set, "sorted": sorted, "str": str,
    "sum": sum, "tuple": tuple, "zip": zip, "ValueError": ValueError, "TypeError": TypeError,
    "ZeroDivisionError": ZeroDivisionError, "Exception": Exception, "None": None, "True": True, "False": False,
}
_MODULES = {"math": math, "statistics": statistics}
# Only the modules' own public API: `statistics` also holds what it imported (random, sys, namedtuple, ...).
_MODULE_ATTRS = {"math": {n for n in dir(math) if not n.startswith("_")}, "statistics": set(statistics.__all__)}
# Methods on the values a function can hold (rows are dicts of str / float / None).
_SAFE_METHODS = {
    "get", "items", "keys", "values", "append", "extend", "insert", "pop", "sort", "copy", "count", "index",
    "lower", "upper", "strip", "lstrip", "rstrip", "split", "replace", "startswith", "endswith", "isdigit",
    "join", "title", "update", "setdefault", "add", "discard", "union", "intersection", "difference",
}
_NODES = (
    ast.Module, ast.FunctionDef, ast.arguments, ast.arg, ast.Return, ast.Assign, ast.AugAssign, ast.For,
    ast.While, ast.If, ast.IfExp, ast.Break, ast.Continue, ast.Pass, ast.Expr, ast.Compare, ast.BoolOp,
    ast.BinOp, ast.UnaryOp, ast.Call, ast.keyword, ast.Name, ast.Load, ast.Store, ast.Constant, ast.List,
    ast.Tuple, ast.Dict, ast.Set, ast.ListComp, ast.DictComp, ast.SetComp, ast.GeneratorExp, ast.comprehension,
    ast.Subscript, ast.Slice, ast.Attribute, ast.Lambda, ast.Try, ast.ExceptHandler, ast.JoinedStr,
    ast.FormattedValue, ast.NamedExpr, ast.operator, ast.unaryop, ast.cmpop, ast.boolop, ast.expr_context,
)


class UnsafeCode(ValueError):
    pass


def _drop_safe_imports(source: str) -> str:
    """Models write `import statistics` / `from math import sqrt` even when told the modules are already there.
    Those exact imports become plain names bound to the provided modules; any other import is left in place, and
    validate() refuses it."""
    try:
        tree = ast.parse(source)
    except (SyntaxError, RecursionError, MemoryError, ValueError):
        return source  # validate() reports it

    class Rewrite(ast.NodeTransformer):
        def visit_Import(self, node: ast.Import) -> Any:
            # `import math as m` stays (and is refused): m.sqrt would be an attribute on a plain name.
            return ast.Pass() if all(a.name in _MODULES and not a.asname for a in node.names) else node

        def visit_ImportFrom(self, node: ast.ImportFrom) -> Any:
            if node.module not in _MODULES or node.level or not all(a.name in _MODULE_ATTRS[node.module] for a in node.names):
                return node
            return [
                ast.Assign(targets=[ast.Name(a.asname or a.name, ast.Store())], value=ast.Attribute(ast.Name(node.module, ast.Load()), a.name, ast.Load()))
                for a in node.names
            ]

    return ast.unparse(ast.fix_missing_locations(Rewrite().visit(tree)))


def validate(source: str) -> None:
    """Raise UnsafeCode unless `source` is exactly one `def answer(rows)` built from allowed parts."""
    if len(source) > MAX_SOURCE:
        raise UnsafeCode("function too long")
    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        raise UnsafeCode(f"syntax error: {e.msg}") from None
    except (RecursionError, MemoryError, ValueError):  # "- - - … 1" nested thousands deep
        raise UnsafeCode("expression nested too deep") from None
    if len(tree.body) != 1 or not isinstance(tree.body[0], ast.FunctionDef) or tree.body[0].name != "answer":
        raise UnsafeCode("must be a single `def answer(rows)`")
    fn = tree.body[0]
    if fn.decorator_list or len(fn.args.args) != 1 or fn.args.vararg or fn.args.kwarg or fn.args.kwonlyargs:
        raise UnsafeCode("answer takes exactly one argument")
    local: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.arg):
            local.add(node.arg)
        elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            local.add(node.id)
        elif isinstance(node, ast.ExceptHandler) and node.name:
            local.add(node.name)
    for node in ast.walk(tree):
        if not isinstance(node, _NODES):
            raise UnsafeCode(f"{type(node).__name__} is not allowed")
        if isinstance(node, ast.FunctionDef) and node is not fn:
            raise UnsafeCode("nested functions are not allowed")
        if isinstance(node, ast.Name):
            if node.id.startswith("_"):
                raise UnsafeCode(f"name {node.id} is not allowed")
            if isinstance(node.ctx, ast.Load) and node.id not in local and node.id not in _SAFE_BUILTINS and node.id not in _MODULES:
                raise UnsafeCode(f"name {node.id} is not allowed")
            if isinstance(node.ctx, ast.Store) and (node.id in _MODULES or node.id in _SAFE_BUILTINS):
                raise UnsafeCode(f"{node.id} can't be reassigned")
        if isinstance(node, ast.Attribute):
            if node.attr.startswith("_"):
                raise UnsafeCode(f"attribute {node.attr} is not allowed")
            if isinstance(node.value, ast.Name) and node.value.id in _MODULES:
                if node.attr not in _MODULE_ATTRS[node.value.id]:
                    raise UnsafeCode(f"{node.value.id}.{node.attr} is not allowed")
            elif node.attr not in _SAFE_METHODS:
                raise UnsafeCode(f"attribute {node.attr} is not allowed")
        if isinstance(node, ast.Constant) and isinstance(node.value, (bytes, complex)):
            raise UnsafeCode("bytes and complex literals are not allowed")
        # 10 ** 10 ** 10 and [0] * 10 ** 9 would eat the machine before the time limit lands.
        if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Pow, ast.LShift)):
            if not (isinstance(node.right, ast.Constant) and isinstance(node.right.value, (int, float)) and abs(node.right.value) <= 8):
                raise UnsafeCode("powers and shifts need a small constant exponent")


def _jsonable(v: Any) -> Any:
    if v is None or isinstance(v, (bool, str)):
        return v
    if isinstance(v, (int, float)):
        return v if math.isfinite(v) else None
    if isinstance(v, dict):
        return {str(k): _jsonable(x) for k, x in v.items()}
    if isinstance(v, (list, tuple, set)):
        return [_jsonable(x) for x in v]
    raise TypeError(f"answer returned a {type(v).__name__}")


def _child() -> None:
    payload = json.loads(sys.stdin.read())
    source = payload["source"]
    validate(source)  # again, in here: this process is the one that executes it
    scope: dict[str, Any] = {"__builtins__": _SAFE_BUILTINS, **_MODULES}
    exec(compile(source, "<answer>", "exec"), scope)  # noqa: S102 - validated above, isolated process
    out = _jsonable(scope["answer"](payload["rows"]))
    if isinstance(out, list) and len(out) > MAX_RESULT_ROWS:
        out = out[:MAX_RESULT_ROWS]
    text = json.dumps({"ok": True, "value": out})
    if len(text) > MAX_RESULT_BYTES:
        raise ValueError("the result is too large")
    sys.stdout.write(text)


def _limits() -> None:  # POSIX only: CPU seconds and address space for the child
    import resource

    resource.setrlimit(resource.RLIMIT_CPU, (TIMEOUT_S, TIMEOUT_S))
    resource.setrlimit(resource.RLIMIT_AS, (MEMORY_LIMIT, MEMORY_LIMIT))


def _windows_job(handle: int) -> Callable[[], None]:
    """Windows has no RLIMIT: a Job Object caps the child's memory and CPU time, forbids it starting processes,
    and kills it when the job closes. Returns the function that closes the job; raises OSError if the child
    couldn't be placed in it."""
    import ctypes
    from ctypes import wintypes

    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateJobObjectW.restype = wintypes.HANDLE
    k32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    k32.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    k32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    k32.CloseHandle.argtypes = [wintypes.HANDLE]

    class Basic(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64), ("LimitFlags", wintypes.DWORD),
            ("MinimumWorkingSetSize", ctypes.c_size_t), ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD), ("SchedulingClass", wintypes.DWORD),
        ]

    class Extended(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", Basic), ("IoInfo", ctypes.c_ulonglong * 6), ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t), ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    info = Extended()
    # PROCESS_TIME | ACTIVE_PROCESS | PROCESS_MEMORY | KILL_ON_JOB_CLOSE
    info.BasicLimitInformation.LimitFlags = 0x2 | 0x8 | 0x100 | 0x2000
    info.BasicLimitInformation.PerProcessUserTimeLimit = TIMEOUT_S * 10_000_000  # 100 ns units
    info.BasicLimitInformation.ActiveProcessLimit = 1
    info.ProcessMemoryLimit = MEMORY_LIMIT
    job = k32.CreateJobObjectW(None, None)
    if not job:
        raise OSError(ctypes.get_last_error(), "could not create a job for the calculation")
    if not k32.SetInformationJobObject(job, 9, ctypes.byref(info), ctypes.sizeof(info)) or not k32.AssignProcessToJobObject(job, handle):
        code = ctypes.get_last_error()
        k32.CloseHandle(job)
        raise OSError(code, "could not limit the calculation's process")
    return lambda: k32.CloseHandle(job)


def run(source: str, rows: list[dict[str, Any]]) -> Any:
    """Validate, then run `answer(rows)` in the locked-down child. Returns its JSON value or raises ValueError."""
    source = _drop_safe_imports(source)
    validate(source)
    if not _SLOTS.acquire(timeout=TIMEOUT_S):
        raise ValueError("too many calculations are running")
    try:
        return _run_child(source, rows)
    finally:
        _SLOTS.release()


def _run_child(source: str, rows: list[dict[str, Any]]) -> Any:
    env = {"SYSTEMROOT": os.environ["SYSTEMROOT"]} if os.name == "nt" and "SYSTEMROOT" in os.environ else {}
    # The base interpreter, not a venv's python.exe: on Windows that is a launcher that starts a second process,
    # which the job forbids. The child needs only the standard library.
    python = getattr(sys, "_base_executable", None) or sys.executable
    proc = subprocess.Popen(
        [python, "-I", "-S", os.path.abspath(__file__)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
        preexec_fn=_limits if os.name == "posix" else None,  # noqa: PLW1509 - no threads touch this fork's state
    )
    close_job = None
    try:
        if os.name == "nt":
            # The child waits on stdin, so nothing runs before it is in the job. Fail closed if it can't be.
            close_job = _windows_job(int(proc._handle))  # noqa: SLF001 - Popen keeps the process handle here
        out, err = proc.communicate(json.dumps({"source": source, "rows": rows}), timeout=TIMEOUT_S)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.communicate()
        raise ValueError("the calculation took too long") from None
    except OSError as e:
        proc.kill()
        proc.communicate()
        raise ValueError(f"the calculation could not be sandboxed: {e}") from None
    finally:
        if close_job:
            close_job()
    if proc.returncode != 0:
        raise ValueError(((err or "").strip().splitlines() or ["the calculation failed"])[-1][:300])
    return json.loads(out)["value"]


if __name__ == "__main__":
    _child()
