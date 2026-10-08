# Copyright (c) lintmax-py contributors. Licensed under the MIT License.
from __future__ import annotations

import fnmatch
import re
from typing import TYPE_CHECKING

import tomllib

if TYPE_CHECKING:
    from pathlib import Path

SKIP_DIRS = frozenset({
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
    "site-packages",
    "venv",
})

GLOB_EXCLUDES = [f"**/{name}" for name in sorted(SKIP_DIRS)] + ["**/uv.lock"]


def skipped(path: Path) -> bool:
    return any(part in SKIP_DIRS for part in path.parts)


def generated(root: Path) -> list[str]:
    """Read the paths a project declares as generated output, relative to its root.

    Experiment results, recorded transcripts and other files a program writes are not authored
    code, and judging them reports the program's OUTPUT as defects — a spell checker reads every
    non-English transcript line as a misspelling. Which paths are generated is a fact about the
    project the gate cannot infer, so the project states it in its own manifest. Every stage skips
    exactly those paths and nothing else; no rule is relaxed for any authored file.

    Returns:
        The declared glob patterns, or nothing when the project declares none.

    """
    try:
        manifest = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return []
    section = manifest.get("tool", {}).get("lintmax-py")
    declared = section.get("generated") if isinstance(section, dict) else None
    if not isinstance(declared, list):
        return []
    return [str(item).strip("/") for item in declared if str(item).strip("/")]


def is_generated(path: Path, root: Path, patterns: list[str]) -> bool:
    relative = path.relative_to(root).as_posix()
    return any(fnmatch.fnmatch(relative, pat) or fnmatch.fnmatch(relative, f"{pat}/*") for pat in patterns)


def generated_regex(patterns: list[str]) -> str:
    return "|".join(f"(?:{fnmatch.translate(pat)[:-2]}(?:/.*)?)" for pat in patterns) or re.escape("")


def sources(root: Path, pattern: str = "*.py") -> list[Path]:
    declared = generated(root)
    return [p for p in sorted(root.rglob(pattern)) if not skipped(p) and not is_generated(p, root, declared)]
