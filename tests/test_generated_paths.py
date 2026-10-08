# Copyright (c) lintmax-py contributors. Licensed under the MIT License.
from __future__ import annotations

import re
from typing import TYPE_CHECKING

import tomllib

from lintmax_py import comments, config, gate
from lintmax_py.paths import generated, generated_regex, sources
from lintmax_py.proc import Result, run

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

MANIFEST = '[project]\nname = "x"\n[tool.lintmax-py]\ngenerated = ["out*", "data/"]\n'


def _tree(root: Path) -> None:
    (root / "pyproject.toml").write_text(MANIFEST, encoding="utf-8")
    for rel in ("out_a/m1/note.py", "data/clip/x.py", "src/kept.py"):
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("x = 1  # stray\n", encoding="utf-8")
    (root / "out_a" / "run.sh").write_text("echo hi\n", encoding="utf-8")
    (root / "tool.sh").write_text("echo hi\n", encoding="utf-8")


def test_a_project_declares_its_generated_paths(tmp_path: Path) -> None:
    _tree(tmp_path)
    assert generated(tmp_path) == ["out*", "data"]


def test_a_silent_project_declares_none(tmp_path: Path) -> None:
    assert generated(tmp_path) == []


def test_generated_files_are_never_rewritten_and_authored_ones_still_are(tmp_path: Path) -> None:
    _tree(tmp_path)
    assert comments.offenders(tmp_path) == [str(tmp_path / "src" / "kept.py")]


def test_every_walking_stage_skips_generated_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _tree(tmp_path)
    calls: list[list[str]] = []

    def fake(cmd: list[str], **_kwargs: object) -> Result:
        calls.append(cmd)
        return Result(code=0, out="")

    monkeypatch.setattr(gate, "run", fake)
    gate._python_stages(tmp_path, tmp_path, fix=False)
    gate._repo_stages(tmp_path, tmp_path, fix=False)
    by_tool = {cmd[0]: cmd for cmd in calls}
    assert "out*" in by_tool["ty"]
    assert str(tmp_path / "data") in by_tool["vulture"][by_tool["vulture"].index("--exclude") + 1]
    assert "/out*" in by_tool["typos"]
    assert by_tool["typos"][-1] == "."
    assert by_tool["dprint"][-1] == str(tmp_path), "dprint resolves its includes against the config's own temp directory"
    assert str(tmp_path / "out_a" / "run.sh") not in by_tool["shellcheck"]
    assert str(tmp_path / "tool.sh") in by_tool["shellcheck"]
    pattern = by_tool["deptry"][by_tool["deptry"].index("--extend-exclude") + 1]
    assert re.fullmatch(pattern, "out_a/m1/note.py")
    assert not re.fullmatch(pattern, "src/kept.py")


def test_formatter_and_linter_configs_exclude_generated_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _tree(tmp_path)
    monkeypatch.setattr(config, "bump", list)
    ruff = tomllib.loads(config.ruff_toml([], tmp_path))
    assert str(tmp_path / "out*") in ruff["exclude"]
    assert str(tmp_path / "data" / "**") in config.dprint_json(tmp_path)


def test_the_regex_matches_a_directory_and_its_contents() -> None:
    pattern = generated_regex(["synth/out*"])
    assert re.fullmatch(pattern, "synth/out_cafe/m001/audio.json")
    assert not re.fullmatch(pattern, "synth/minutes.py")


def test_files_version_control_ignores_are_never_judged(tmp_path: Path) -> None:
    assert run(["git", "-C", str(tmp_path), "init", "-q"]).code == 0
    (tmp_path / ".gitignore").write_text("mirror/\n", encoding="utf-8")
    (tmp_path / "mirror").mkdir()
    (tmp_path / "mirror" / "synced.sh").write_text("echo hi\n", encoding="utf-8")
    (tmp_path / "mine.sh").write_text("echo hi\n", encoding="utf-8")
    assert sources(tmp_path, "*.sh") == [tmp_path / "mine.sh"]


def test_outside_version_control_every_file_counts(tmp_path: Path) -> None:
    (tmp_path / "a.sh").write_text("echo hi\n", encoding="utf-8")
    assert sources(tmp_path, "*.sh") == [tmp_path / "a.sh"]
