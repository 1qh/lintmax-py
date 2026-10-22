# Copyright (c) lintmax-py contributors. Licensed under the MIT License.
from __future__ import annotations

import json
import re
import tomllib
from typing import TYPE_CHECKING

from lintmax_py import comments, config, gate
from lintmax_py.paths import SKIP_DIRS, generated, generated_regex, sources
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


def test_dprint_never_rewrites_generated_files_and_still_formats_authored_ones(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Generated excludes protect files BELOW a declared glob when the config lives elsewhere.

    The generated file sits below `data/*/*`, rather than matching the glob itself. Running the
    real formatter through the stage checks that exclusions match with the positional project root;
    checking only the config or mocking dprint leaves path resolution bugs invisible. An authored
    file must still be formatted when the config lives outside the project being checked.

    """
    root = tmp_path / "project"
    root.mkdir()
    (root / "pyproject.toml").write_text('[tool.lintmax-py]\ngenerated = ["data/*/*"]\n', encoding="utf-8")
    untouched = [root / "data" / "a" / "b" / "x.json"]
    untouched += [root / name / "nested" / "x.json" for name in sorted(SKIP_DIRS)]
    original = b'{"value":1}'
    for path in untouched:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(original)
    authored = root / "conf.json"
    authored.write_bytes(original)
    cfg = tmp_path / "config"
    cfg.mkdir()
    monkeypatch.setattr(config, "bump", list)
    (cfg / "dprint.json").write_text(config.dprint_json(root), encoding="utf-8")

    def real_dprint(cmd: list[str], cwd: str | None = None, **_kwargs: object) -> Result:
        return run(cmd, cwd=cwd) if cmd[0] == "dprint" else Result(code=0, out="")

    monkeypatch.setattr(gate, "run", real_dprint)
    assert gate._repo_stages(root, cfg, fix=True) == []
    for path in untouched:
        assert path.read_bytes() == original, path
    assert authored.read_bytes() == b'{ "value": 1 }\n'


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
    assert by_tool["dprint"] == ["dprint", "check", "--config", str(tmp_path / "dprint.json"), str(tmp_path)]
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
    dprint = json.loads(config.dprint_json(tmp_path))
    assert dprint["includes"] == ["**/*"]
    for pattern in ("**/out*", "**/out*/**", "**/data", "**/data/**"):
        assert pattern in dprint["excludes"]


def test_dprint_does_not_double_prefix_generated_patterns(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "bump", list)
    monkeypatch.setattr(config, "generated", lambda _root: ["**/data"])
    dprint = json.loads(config.dprint_json(tmp_path))
    assert dprint["excludes"] == [*config.EXCLUDES, "**/data", "**/data/**"]


def test_the_regex_carries_no_construct_deptry_rejects() -> None:
    pattern = generated_regex(["**/*.jsonl", "synth/out*", "asr-local/data"])
    assert "(?>" not in pattern
    assert re.fullmatch(pattern, "synth/out/m001/hyp/vi70k_ts.jsonl")
    assert re.fullmatch(pattern, "asr-local/data/brics222/audio.wav")
    assert not re.fullmatch(pattern, "spike/asr/score.py")


def test_deptry_accepts_the_regex(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "x"\nversion = "0"\ndependencies = []\n', encoding="utf-8")
    (tmp_path / "x.py").write_text("import json\n", encoding="utf-8")
    result = run(["deptry", ".", "--extend-exclude", generated_regex(["**/*.jsonl", "out*"])], cwd=str(tmp_path))
    assert result.code != 127, result.out
    assert "panicked" not in result.out


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
