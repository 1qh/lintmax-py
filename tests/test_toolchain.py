# Copyright (c) lintmax-py contributors. Licensed under the MIT License.
"""The gate owns its own toolchain, so installing one of its tools must not be refusable."""

from __future__ import annotations

import inspect
from typing import TYPE_CHECKING

from lintmax_py import rules, tools

if TYPE_CHECKING:
    import pytest


def test_installing_a_tool_overwrites_whatever_holds_its_name() -> None:
    """A stale entry left by an earlier install must not be able to disable a stage.

    A tool store that has been wiped leaves the launcher behind as a DANGLING symlink, so the
    installer refuses with "executable already exists" while the executable resolves to nothing.
    The stage then reports itself not installed on every run and stops judging anything, which
    reads as a gate with fewer rules rather than a gate that is broken.
    """
    source = inspect.getsource(tools.ensure)
    install = next(line for line in source.splitlines() if '"install"' in line)
    assert '"--force"' in install, "an install that can be refused is a stage that can silently vanish"


def test_the_xml_rules_stand_down_only_for_a_protected_expat(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(rules, "expat_version", lambda _python: (2, 7, 4))
    assert rules.xml_safe("python")
    monkeypatch.setattr(rules, "expat_version", lambda _python: (2, 6, 0))
    assert not rules.xml_safe("python")
    monkeypatch.setattr(rules, "expat_version", lambda _python: None)
    assert not rules.xml_safe("python")
