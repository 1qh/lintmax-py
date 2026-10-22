# Copyright (c) lintmax-py contributors. Licensed under the MIT License.
from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from lintmax_py import staleness

if TYPE_CHECKING:
    from pathlib import Path


def _project(root: Path, config: str = "") -> None:
    body = '[project]\ndependencies = ["pillow<13"]\n' + config
    (root / "pyproject.toml").write_text(body, encoding="utf-8")
    (root / "uv.lock").write_text('[[package]]\nname = "pillow"\nversion = "12.0"\n', encoding="utf-8")


def _offline(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LINTMAX_SKIP_STALENESS", raising=False)
    monkeypatch.setattr(staleness, "latest", lambda _name: "13.0")


def test_a_held_behind_package_is_silent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _offline(monkeypatch)
    _project(tmp_path, '[tool.lintmax-py.holds]\npillow = "Gradio requires pillow<13; revisit when it supports 13"\n')
    assert staleness.behind(tmp_path) == []


def test_an_unheld_behind_package_is_reported(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _offline(monkeypatch)
    _project(tmp_path)
    assert staleness.behind(tmp_path) == ["pillow 12.0 -> 13.0"]


def test_a_held_up_to_date_package_is_reported(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _offline(monkeypatch)
    _project(tmp_path, '[tool.lintmax-py.holds]\npillow = "Gradio requires pillow<13; revisit when it supports 13"\n')
    monkeypatch.setattr(staleness, "latest", lambda _name: "12.0")
    assert staleness.behind(tmp_path) == ["hold no longer needed: pillow 12.0"]


def test_a_hold_on_an_undeclared_package_is_reported(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _offline(monkeypatch)
    _project(tmp_path, '[tool.lintmax-py.holds]\ngradio = "Resolver conflict; revisit after the next release"\n')
    assert staleness.behind(tmp_path) == [
        "hold names an undeclared package: gradio",
        "pillow 12.0 -> 13.0",
    ]


@pytest.mark.parametrize("reason", ['""', '"   "', "13", "false", "[]", "{}"])
def test_an_invalid_hold_reason_is_refused(tmp_path: Path, reason: str, monkeypatch: pytest.MonkeyPatch) -> None:
    _offline(monkeypatch)
    _project(tmp_path, f"[tool.lintmax-py.holds]\npillow = {reason}\n")
    with pytest.raises(ValueError, match=r"tool\.lintmax-py\.holds\.pillow must be a non-empty string"):
        staleness.behind(tmp_path)


def test_holds_must_be_a_table(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _offline(monkeypatch)
    _project(tmp_path, '[tool.lintmax-py]\nholds = ["pillow"]\n')
    with pytest.raises(TypeError, match=r"tool\.lintmax-py\.holds must be a table"):
        staleness.behind(tmp_path)


@pytest.mark.parametrize("config", ["", '[tool.lintmax-py.holds]\npillow = "Conflict; revisit next release"\n'])
def test_a_failed_latest_lookup_is_skipped(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    config: str,
) -> None:
    _offline(monkeypatch)
    _project(tmp_path, config)
    monkeypatch.setattr(staleness, "latest", lambda _name: None)
    assert staleness.behind(tmp_path) == []
