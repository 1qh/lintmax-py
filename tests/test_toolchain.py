# Copyright (c) lintmax-py contributors. Licensed under the MIT License.
"""The gate owns its own toolchain, so installing one of its tools must not be refusable."""

from __future__ import annotations

import inspect
from typing import TYPE_CHECKING

from lintmax_py import config, gate, rules, staleness, tools
from lintmax_py.proc import Result

if TYPE_CHECKING:
    from pathlib import Path

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


def test_gate_runs_a_tool_from_the_uv_bin_directory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "project"
    root.mkdir()
    (root / "example.py").write_text("value = 1\n", encoding="utf-8")
    uv_bin = tmp_path / "uv bin"
    uv_bin.mkdir()
    path_bin = tmp_path / "path bin"
    path_bin.mkdir()
    monkeypatch.setenv("PATH", str(path_bin))
    monkeypatch.setattr(tools, "fresh", lambda: True)

    scripts = {
        "ruff": """#!/bin/sh
if [ "$1" = rule ]; then
    printf '[{}]\\n'
fi
""",
        "ty": "#!/bin/sh\nexit 0\n",
        "vulture": "#!/bin/sh\nprintf 'uv-bin stub ran\\n'\nexit 1\n",
        "dprint": "#!/bin/sh\nexit 0\n",
        "typos": "#!/bin/sh\nexit 0\n",
    }
    for name, script in scripts.items():
        stub = uv_bin / name
        stub.write_text(script, encoding="utf-8")
        stub.chmod(0o700)
    monkeypatch.setattr(tools, "TOOLS", {name: name for name in scripts})
    calls: list[list[str]] = []

    def fake_uv(argv: list[str], *, timeout: int, **_kwargs: object) -> Result:
        assert argv == ["uv", "tool", "dir", "--bin"]
        assert timeout > 0
        calls.append(argv)
        return Result(code=0, out=f"{uv_bin}\n")

    monkeypatch.setattr(tools, "run", fake_uv)
    monkeypatch.setattr(config, "materialize", lambda _inventory, _root: (tmp_path, ""))
    monkeypatch.setattr(staleness, "behind", lambda _root: [])

    assert gate.run_gate(root, fix=False) == [gate.Finding(stage="vulture", detail="uv-bin stub ran")]
    assert calls == [["uv", "tool", "dir", "--bin"]]


def test_missing_tool_reports_path_and_uv_bin(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    uv_bin = tmp_path / "uv-bin"
    uv_bin.mkdir()
    path_bin = tmp_path / "path-bin"
    path_bin.mkdir()
    monkeypatch.setenv("PATH", str(path_bin))
    monkeypatch.setattr(tools, "fresh", lambda: True)
    monkeypatch.setattr(tools, "TOOLS", {"vulture": "vulture"})
    calls: list[list[str]] = []

    def fake_uv(argv: list[str], *, timeout: int, **_kwargs: object) -> Result:
        assert timeout > 0
        calls.append(argv)
        return Result(code=0, out=f"{uv_bin}\n" if argv[2] == "dir" else "")

    monkeypatch.setattr(tools, "run", fake_uv)

    resolved, missing = tools.ensure()
    assert resolved == {}
    assert missing == [
        f"vulture: install of vulture did not produce it (exit 0). Searched PATH and the uv tool bin directory ({uv_bin})",
    ]
    assert calls == [
        ["uv", "tool", "dir", "--bin"],
        ["uv", "tool", "install", "--force", "--quiet", "vulture@latest"],
    ]


def test_the_xml_rules_stand_down_only_for_a_protected_expat(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(rules, "expat_version", lambda _python: (2, 7, 4))
    assert rules.xml_safe("python")
    monkeypatch.setattr(rules, "expat_version", lambda _python: (2, 6, 0))
    assert not rules.xml_safe("python")
    monkeypatch.setattr(rules, "expat_version", lambda _python: None)
    assert not rules.xml_safe("python")
