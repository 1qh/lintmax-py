# Copyright (c) lintmax-py contributors. Licensed under the MIT License.
"""deptry reads the target project's installed metadata, so a namespace distribution maps to its module."""

from __future__ import annotations

from typing import TYPE_CHECKING

from lintmax_py import gate
from lintmax_py.proc import run

if TYPE_CHECKING:
    from pathlib import Path


def _project(root: Path) -> None:
    (root / "pyproject.toml").write_text(
        '[project]\nname = "x"\nversion = "0"\ndependencies = ["spoken-ns-audio"]\n',
        encoding="utf-8",
    )
    (root / "x.py").write_text("import spokenns\n", encoding="utf-8")
    dist = root / ".venv" / "lib" / "python3.12" / "site-packages" / "spoken_ns_audio-1.0.dist-info"
    dist.mkdir(parents=True)
    (dist / "METADATA").write_text("Metadata-Version: 2.1\nName: spoken-ns-audio\nVersion: 1.0\n", encoding="utf-8")
    (dist / "top_level.txt").write_text("spokenns\n", encoding="utf-8")


def test_without_the_project_environment_deptry_misreads_the_namespace(tmp_path: Path) -> None:
    _project(tmp_path)
    blind = run(["deptry", "."], cwd=str(tmp_path))
    assert blind.code != 127, blind.out
    assert "DEP001" in blind.out


def test_with_the_project_environment_deptry_maps_the_namespace(tmp_path: Path) -> None:
    _project(tmp_path)
    env = gate._deptry_env(tmp_path)
    assert env is not None
    seen = run(["deptry", "."], cwd=str(tmp_path), env=env)
    assert "DEP001" not in seen.out, seen.out
    assert "DEP002" not in seen.out, seen.out


def test_no_environment_means_no_override(tmp_path: Path) -> None:
    assert gate._deptry_env(tmp_path) is None
