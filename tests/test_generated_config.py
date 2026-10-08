# Copyright (c) lintmax-py contributors. Licensed under the MIT License.
from __future__ import annotations

from typing import TYPE_CHECKING

import tomllib

from lintmax_py import config, rules

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

NAMELESS: dict[str, object] = {"name": "pytest-fixture-autouse", "code": None, "preview": True}
CODED: dict[str, object] = {"name": "x", "code": "RUF999", "preview": True}


def test_a_rule_without_a_code_is_selected_by_name() -> None:
    selected = rules.selection([NAMELESS, CODED])
    assert "pytest-fixture-autouse" in selected
    assert "RUF999" in selected
    assert "None" not in selected


def test_a_long_array_goes_one_item_per_line_and_still_parses(tmp_path: Path) -> None:
    body = config.ruff_toml([NAMELESS, CODED], tmp_path)
    for line in body.splitlines():
        assert len(line) <= config.LINE_LENGTH, line
    parsed = tomllib.loads(body)
    assert "pytest-fixture-autouse" in parsed["lint"]["select"]
    assert parsed["exclude"] == config.EXCLUDES


def test_a_short_array_stays_on_one_line() -> None:
    assert config.toml_array("k", ["a", "b"]) == 'k = ["a", "b"]\n'


def test_the_generated_json_ends_in_a_newline(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "bump", list)
    assert config.dprint_json(tmp_path).endswith("}\n")


def test_a_fix_that_deletes_program_output_is_never_applied(tmp_path: Path) -> None:
    parsed = tomllib.loads(config.ruff_toml([], tmp_path))
    assert {"T201", "T203", "F401", "PIE794"} <= set(parsed["lint"]["unfixable"])
    assert "T201" not in parsed["lint"]["ignore"]
