# Copyright (c) lintmax-py contributors. Licensed under the MIT License.
from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from lintmax_py import gate
from lintmax_py.dprint import changed_code_span
from lintmax_py.proc import DEFAULT_IO, Result

if TYPE_CHECKING:
    from pathlib import Path

    from lintmax_py.proc import RunIO

ORIGINAL_CASE = (
    b'root=/tmp\nout=$(printf "%s\\n" "$root/item" | while read -r f; do '
    b'case "$f" in ("$root"/*) ;; (*) continue ;; esac; done)\n'
)
BROKEN_CASE = (
    b'root=/tmp\nout=$(printf "%s\\n" "$root/item" | while read -r f; do\n'
    b'  case "$f" in\n    "$root"/*) ;;\n    *) continue ;;\n  esac\ndone)\n'
)
PARSER_ERROR = "syntax error near unexpected token ';;'"


@pytest.mark.parametrize("fix", [False, True])
def test_shfmt_preserves_a_case_that_its_output_breaks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    fix: bool,
) -> None:
    broken = tmp_path / "case.sh"
    broken.write_bytes(ORIGINAL_CASE)
    safe = tmp_path / "safe.sh"
    safe_before = b"#!/usr/bin/env -S bash\nif true;then\necho ok\nfi\n"
    safe_after = b"#!/usr/bin/env -S bash\nif true; then\n  echo ok\nfi\n"
    safe.write_bytes(safe_before)
    parsed: list[tuple[list[str], bytes | None]] = []

    def fake(argv: list[str], *_args: object, io: RunIO = DEFAULT_IO, **_kwargs: object) -> Result:
        if argv[0] == "shfmt":
            if "-w" in argv:
                broken.write_bytes(BROKEN_CASE)
                safe.write_bytes(safe_after)
                return Result(code=0, out="")
            output = BROKEN_CASE if argv[-1] == str(broken) else safe_after
            return Result(code=0, out=output.decode())
        parsed.append((argv, io.input_bytes))
        return Result(code=2, out=PARSER_ERROR) if io.input_bytes == BROKEN_CASE else Result(code=0, out="")

    monkeypatch.setattr(gate, "run", fake)
    findings = gate._shell_format([broken, safe], fix=fix)
    assert findings
    assert findings[0] == gate.Finding(stage="shfmt", detail=f"{broken}: {PARSER_ERROR}")
    assert findings[1:] == ([] if fix else [gate.Finding(stage="shfmt", detail=f"{safe}: needs formatting (run fix)")])
    assert parsed
    assert parsed == [(["sh", "-n"], BROKEN_CASE), (["bash", "-n"], safe_after)]
    assert broken.read_bytes() == ORIGINAL_CASE
    assert safe.read_bytes() == (safe_after if fix else safe_before)


@pytest.mark.parametrize("fix", [False, True])
def test_dprint_preserves_a_markdown_file_when_it_would_trim_inline_code(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    fix: bool,
) -> None:
    guarded = tmp_path / "rule.md"
    original = b"Match the prefix `## ` before the title.\n"
    guarded.write_bytes(original)
    safe = tmp_path / "safe.md"
    safe_before = b"*   Keep ``a`b`` as written.\n"
    safe_after = b"- Keep ``a`b`` as written.\n"
    safe.write_bytes(safe_before)

    def fake(argv: list[str], *_args: object, io: RunIO = DEFAULT_IO, **_kwargs: object) -> Result:
        assert len(argv) > 1
        if argv[1] == "file-paths":
            return Result(code=0, out=f"{guarded}\n{safe}")
        assert "--stdin" in argv
        if argv[-1] == str(guarded):
            assert io.input_bytes == original
            return Result(code=0, out="Match the prefix `##` before the title.\n")
        assert io.input_bytes == safe_before
        return Result(code=0, out=safe_after.decode())

    monkeypatch.setattr(gate, "run", fake)
    findings = gate._dprint_stage(tmp_path, tmp_path, fix=fix)
    assert findings
    assert findings[0] == gate.Finding(stage="dprint", detail=f"{guarded}: formatting would change inline code span '## '")
    assert findings[1:] == ([] if fix else [gate.Finding(stage="dprint", detail=f"{safe}: needs formatting (run fix)")])
    assert guarded.read_bytes() == original
    assert safe.read_bytes() == (safe_after if fix else safe_before)


def test_inline_code_guard_matches_delimiter_lengths_and_counts_duplicates() -> None:
    before = b"Keep ```a``b`c``` and `## ` and `## `.\n"
    reordered = b"Keep `## ` and ```a``b`c``` and `## `.\n"
    assert changed_code_span(before, reordered) is None
    assert changed_code_span(before, reordered.replace(b"a``b`c", b"a`b`c")) == (
        "formatting would change inline code span 'a``b`c'"
    )
    assert changed_code_span(before, reordered.replace(b"`## `", b"`##`", 1)) == (
        "formatting would change inline code span '## '"
    )


def test_inline_code_guard_ignores_backticks_inside_fenced_code() -> None:
    before = b"```sh\nprintf '`## `'\n```\n\nKeep `## ` in prose.\n"
    after = before.replace(b"printf '`## `'", b"printf '`##`'")
    assert changed_code_span(before, after) is None
