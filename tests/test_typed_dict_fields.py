# Copyright (c) lintmax-py contributors. Licensed under the MIT License.
"""Dead-code allowances derive every TypedDict field, so string-keyed reads are not reported."""

from __future__ import annotations

from typing import TYPE_CHECKING

from lintmax_py import config
from lintmax_py.proc import run

if TYPE_CHECKING:
    from pathlib import Path

SOURCE = """from typing import TypedDict
import typing


class Row(TypedDict):
    title: str


class Other(typing.TypedDict):
    count: int


class Plain:
    width: int


def read(row: Row, other: Other) -> str:
    return row["title"] + str(other["count"])
"""


def test_fields_of_both_spellings_are_named_and_plain_classes_are_not(tmp_path: Path) -> None:
    path = tmp_path / "rows.py"
    path.write_text(SOURCE, encoding="utf-8")
    assert config.typed_dict_fields([path]) == ["count", "title"]


def test_vulture_stays_quiet_on_fields_once_allowed(tmp_path: Path) -> None:
    path = tmp_path / "rows.py"
    path.write_text(SOURCE, encoding="utf-8")
    bare = run(["vulture", str(path)])
    assert bare.code != 127, bare.out
    assert "unused variable 'title'" in bare.out
    allowed = run(["vulture", "--ignore-names", ",".join(config.typed_dict_fields([path])), str(path)])
    assert "'title'" not in allowed.out
    assert "'count'" not in allowed.out
