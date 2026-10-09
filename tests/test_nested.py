# Copyright (c) lintmax-py contributors. Licensed under the MIT License.
from __future__ import annotations

from typing import TYPE_CHECKING

from lintmax_py import gate
from lintmax_py.proc import Result

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    import pytest


def _record(calls: list[list[str]]) -> Callable[..., Result]:
    def fake(cmd: list[str], **_kwargs: object) -> Result:
        calls.append(cmd)
        return Result(code=0, out="")

    return fake


def _tree(root: Path) -> Path:
    (root / "pyproject.toml").write_text('[project]\nname = "outer"\n', encoding="utf-8")
    inner = root / "pinned"
    (inner / ".venv").mkdir(parents=True)
    (inner / "pyproject.toml").write_text('[project]\nname = "inner"\n', encoding="utf-8")
    (inner / "run.py").write_text("x = 1\n", encoding="utf-8")
    (root / ".venv" / "lib" / "pkg").mkdir(parents=True)
    (root / ".venv" / "lib" / "pkg" / "pyproject.toml").write_text("", encoding="utf-8")
    return inner


def test_a_nested_project_is_type_checked_against_its_own_environment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inner = _tree(tmp_path)
    calls: list[list[str]] = []
    monkeypatch.setattr(gate, "run", _record(calls))

    gate._python_stages(tmp_path, tmp_path, fix=False)

    ty_runs = [c for c in calls if c[0] == "ty"]
    assert len(ty_runs) == 2
    root_run, inner_run = ty_runs
    assert root_run[root_run.index("--exclude") + 1] == "pinned/"
    assert inner_run[inner_run.index("--python") + 1] == str(inner / ".venv")
    assert inner_run[-1] == str(inner)
    assert inner_run[inner_run.index("--project") + 1] == str(inner), (
        "a nested project is checked with its own ty settings"
    )


def test_a_manifest_inside_a_skipped_directory_is_not_a_project(tmp_path: Path) -> None:
    inner = _tree(tmp_path)
    assert gate.nested_projects(tmp_path) == [inner]


def test_a_repository_without_nested_projects_runs_one_type_check(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "outer"\n', encoding="utf-8")
    calls: list[list[str]] = []
    monkeypatch.setattr(gate, "run", _record(calls))

    gate._python_stages(tmp_path, tmp_path, fix=False)

    ty_runs = [c for c in calls if c[0] == "ty"]
    assert len(ty_runs) == 1
    assert "--exclude" not in ty_runs[0]


def test_deptry_judges_a_nested_project_from_its_own_manifest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inner = _tree(tmp_path)
    calls: list[tuple[list[str], object]] = []

    def fake(cmd: list[str], **kwargs: object) -> Result:
        calls.append((cmd, kwargs.get("cwd")))
        return Result(code=0, out="")

    monkeypatch.setattr(gate, "run", fake)
    gate._repo_stages(tmp_path, tmp_path, fix=False)

    deptry = [(c, cwd) for c, cwd in calls if c[0] == "deptry"]
    assert (str(inner)) in [cwd for _, cwd in deptry]
    root_cmd = next(c for c, cwd in deptry if cwd == str(tmp_path))
    assert root_cmd[root_cmd.index("--extend-exclude") + 1] == "pinned/"
