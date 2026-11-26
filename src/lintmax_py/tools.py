# Copyright (c) lintmax-py contributors. Licensed under the MIT License.
from __future__ import annotations

import hashlib
import os
import shutil
import time
from pathlib import Path

from .proc import RunIO, run

TOOLS = {
    "ruff": "ruff",
    "ty": "ty",
    "vulture": "vulture",
    "deptry": "deptry",
    "pip-audit": "pip-audit",
    "typos": "typos",
    "shellcheck-py": "shellcheck",
    "shfmt-py": "shfmt",
    "dprint-py": "dprint",
}
REFRESH_TTL_SECONDS = 24 * 60 * 60


def is_ci() -> bool:
    return any(os.environ.get(name) for name in ("CI", "GITHUB_ACTIONS"))


def stamp() -> Path:
    key = hashlib.sha256(b"lintmax-py-refresh").hexdigest()[:16]
    return Path.home() / ".cache" / "lintmax-py" / f"{key}.refresh"


def fresh() -> bool:
    if is_ci():
        return False
    path = stamp()
    if not path.is_file():
        return False
    try:
        stamped = float(path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return False
    return (time.time() - stamped) < REFRESH_TTL_SECONDS


def mark() -> None:
    path = stamp()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(str(time.time()), encoding="utf-8")


def uv_bin_dir() -> Path | None:
    result = run(["uv", "tool", "dir", "--bin"], timeout=10, io=RunIO(raw_output=True))
    if result.code or not (directory := result.out.rstrip("\r\n")):
        return None
    return Path(directory).absolute()


def resolve(exe: str, uv_bin: Path | None) -> str | None:
    located = shutil.which(exe)
    if located is None and uv_bin is not None:
        located = shutil.which(str(uv_bin / exe))
    return str(Path(located).resolve()) if located is not None else None


def ensure() -> tuple[dict[str, str], list[str]]:
    uv_bin = uv_bin_dir()
    resolved: dict[str, str] = {}
    missing: list[str] = []
    refresh = not fresh()
    for package, exe in TOOLS.items():
        path = resolve(exe, uv_bin)
        if refresh or path is None:
            res = run(["uv", "tool", "install", "--force", "--quiet", f"{package}@latest"], timeout=900)
            path = resolve(exe, uv_bin)
            if path is None:
                reason = res.out or f"exit {res.code}"
                directory = uv_bin if uv_bin is not None else "unavailable"
                missing.append(
                    f"{exe}: install of {package} did not produce it ({reason}). "
                    f"Searched PATH and the uv tool bin directory ({directory})",
                )
                continue
        resolved[exe] = path
    if refresh:
        mark()
    return resolved, missing


def executables() -> list[str]:
    return sorted(TOOLS.values())
