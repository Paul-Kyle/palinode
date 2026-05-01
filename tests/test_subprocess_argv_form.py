"""Static-analysis test ensuring all subprocess invocations in palinode/ use
the argv (list) form and never enable ``shell=True``.

Tied to the marketplace security review (Tier B finding #1): "unsafe shell
command construction in git operations". The intent is to lock the codebase
into argv-form forever — if a future change introduces ``shell=True`` or a
single-string command, this test fails and forces explicit review.

Implementation: walk the AST of every .py file under ``palinode/``, find each
call whose dotted name resolves to ``subprocess.run`` / ``subprocess.Popen``
/ ``subprocess.call`` / ``subprocess.check_call`` / ``subprocess.check_output``,
and assert (a) no ``shell=True`` keyword, (b) the first positional argument
is a list/tuple literal, not a string.

A small allowlist exists for tests/ helpers if ever needed; production code
under ``palinode/`` has no exemptions.
"""
from __future__ import annotations

import ast
import os
from pathlib import Path

import pytest


SUBPROCESS_FUNCS = {"run", "Popen", "call", "check_call", "check_output"}
PALINODE_ROOT = Path(__file__).resolve().parent.parent / "palinode"


def _iter_python_files(root: Path):
    for dirpath, _dirnames, filenames in os.walk(root):
        for fn in filenames:
            if fn.endswith(".py"):
                yield Path(dirpath) / fn


def _is_subprocess_call(node: ast.Call) -> bool:
    """Return True if this call is subprocess.<func>(...) for one of SUBPROCESS_FUNCS."""
    func = node.func
    if isinstance(func, ast.Attribute) and func.attr in SUBPROCESS_FUNCS:
        # subprocess.run(...) or sp.run(...) -- any module attribute
        if isinstance(func.value, ast.Name) and func.value.id in {"subprocess", "sp"}:
            return True
    return False


def _find_violations(path: Path) -> list[tuple[int, str]]:
    """Return a list of (lineno, reason) violations in this file."""
    try:
        source = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return []
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError:
        return []

    violations: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not _is_subprocess_call(node):
            continue

        # (a) Reject shell=True keyword.
        for kw in node.keywords:
            if kw.arg == "shell":
                # shell=True is a violation; shell=False or anything else is fine
                if isinstance(kw.value, ast.Constant) and kw.value.value is True:
                    violations.append((node.lineno, "shell=True"))

        # (b) First positional argument must be a list/tuple literal — not a
        # string literal, f-string, or % expression. A Name reference (e.g. a
        # local list variable) is also acceptable; we only flag obviously-string
        # constructions.
        if node.args:
            first = node.args[0]
            if isinstance(first, ast.Constant) and isinstance(first.value, str):
                violations.append((node.lineno, "string command (not argv list)"))
            elif isinstance(first, ast.JoinedStr):  # f-string
                violations.append((node.lineno, "f-string command (not argv list)"))
            elif isinstance(first, ast.BinOp) and isinstance(first.op, ast.Mod):
                violations.append((node.lineno, "%-format command (not argv list)"))
    return violations


def test_no_shell_true_or_string_commands_in_palinode():
    """Every subprocess call under palinode/ must use argv form, no shell=True."""
    all_violations: list[str] = []
    for py in _iter_python_files(PALINODE_ROOT):
        for lineno, reason in _find_violations(py):
            all_violations.append(f"{py.relative_to(PALINODE_ROOT.parent)}:{lineno}: {reason}")
    assert not all_violations, (
        "subprocess argv-form contract violated:\n  " + "\n  ".join(all_violations)
    )


def test_git_tools_run_git_uses_argv_form():
    """The central _run_git helper must keep its argv-form invocation."""
    from palinode.core import git_tools  # noqa: F401  (import to ensure module is valid)

    src = (PALINODE_ROOT / "core" / "git_tools.py").read_text(encoding="utf-8")
    # If anyone ever switches to shell=True or a string command, the static test
    # above already catches it. This test additionally guards against future
    # _run_git rewrites: the helper itself must continue to pass a list literal.
    tree = ast.parse(src)
    found = False
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.FunctionDef)
            and node.name == "_run_git"
        ):
            for child in ast.walk(node):
                if isinstance(child, ast.Call) and _is_subprocess_call(child):
                    assert child.args, "_run_git subprocess call missing positional args"
                    first = child.args[0]
                    assert isinstance(first, (ast.List, ast.Tuple)), (
                        "_run_git must pass an argv list to subprocess.run"
                    )
                    found = True
    assert found, "_run_git did not contain a subprocess call (refactor breakage?)"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
