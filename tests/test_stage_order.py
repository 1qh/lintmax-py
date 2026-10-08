# Copyright (c) lintmax-py contributors. Licensed under the MIT License.
from __future__ import annotations

from typing import TYPE_CHECKING

from lintmax_py import gate
from lintmax_py.proc import Result

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    import pytest


def _record(calls: list[str]) -> Callable[..., Result]:
    def fake(cmd: list[str], **_kwargs: object) -> Result:
        calls.append(cmd[0])
        return Result(code=0, out="")

    return fake


def test_the_formatter_runs_before_the_checker_it_can_invalidate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A formatter that runs second rewrites the very file the checker just blessed.

    The check then passes against a version that no longer exists on disk, so the finding it owed
    surfaces on the next run against a tree the gate itself rewrote.
    """
    (tmp_path / "s.sh").write_text("#!/usr/bin/env bash\necho hi\n", encoding="utf-8")
    calls: list[str] = []
    monkeypatch.setattr(gate, "run", _record(calls))

    gate._repo_stages(tmp_path, tmp_path, fix=True)

    assert "shfmt" in calls
    assert "shellcheck" in calls
    assert calls.index("shfmt") < calls.index("shellcheck")


def test_fix_formats_again_after_the_autofix_that_can_unformat(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An autofix such as a trailing comma leaves a file the formatter would rewrite.

    Without a format pass after it, `fix` reports clean and the next `check` refuses the same tree.
    """
    calls: list[list[str]] = []

    def fake(cmd: list[str], **_kwargs: object) -> Result:
        calls.append(cmd)
        return Result(code=0, out="")

    monkeypatch.setattr(gate, "run", fake)
    gate._python_stages(tmp_path, tmp_path, fix=True)
    ruff = [c[1] for c in calls if c[0] == "ruff"]
    assert ruff.index("check") < len(ruff) - 1 - ruff[::-1].index("format")
