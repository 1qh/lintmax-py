# Copyright (c) lintmax-py contributors. Licensed under the MIT License.
from __future__ import annotations

import json

from .proc import run

DOCSTRING_REQUIRED = ("D100", "D101", "D102", "D103", "D104", "D105", "D106", "D107")
SUBPROCESS_POLICY = ("S404", "S603")
XML_PARSER = ("S314", "S405")
SAFE_EXPAT = (2, 7, 2)


def inventory(ruff: str) -> list[dict[str, object]]:
    res = run([ruff, "rule", "--all", "--output-format", "json"])
    if res.code != 0:
        msg = f"ruff rule --all failed: {res.out}"
        raise RuntimeError(msg)
    parsed = json.loads(res.out)
    if not isinstance(parsed, list) or not parsed:
        msg = "ruff reported an empty rule set"
        raise RuntimeError(msg)
    return [dict(entry) for entry in parsed if isinstance(entry, dict)]


def selector(rule: dict[str, object]) -> str:
    """Return the token that selects a rule: its code, or its name when ruff ships it without one.

    Newer ruff ships rules that carry no code at all and are selectable only by name. Reading the
    code alone turns each of them into the literal string `None`, which selects nothing, so the rule
    is silently never run while the generated config looks complete.

    Returns:
        The rule's code, or its name when it has no code.

    """
    code = rule.get("code")
    return str(code) if code else str(rule["name"])


def preview_codes(rules: list[dict[str, object]]) -> list[str]:
    return sorted(selector(r) for r in rules if r.get("preview"))


def selection(rules: list[dict[str, object]]) -> list[str]:
    return ["ALL", *preview_codes(rules)]


def ignored() -> list[str]:
    return [*DOCSTRING_REQUIRED, *SUBPROCESS_POLICY]


def expat_version(python: str) -> tuple[int, ...] | None:
    res = run([python, "-c", "import pyexpat; print(pyexpat.EXPAT_VERSION)"])
    if res.code != 0:
        return None
    digits = res.out.strip().removeprefix("expat_").split(".")
    try:
        return tuple(int(part) for part in digits)
    except ValueError:
        return None


def xml_safe(python: str) -> bool:
    found = expat_version(python)
    return found is not None and found >= SAFE_EXPAT


def summary(rules: list[dict[str, object]]) -> str:
    linters = {str(r.get("linter", "?")) for r in rules}
    preview = preview_codes(rules)
    return (
        f"ruff rules: {len(rules)} across {len(linters)} linters "
        f"({len(preview)} preview-gated, all selected)\n"
        f"ty rules: all at error severity\n"
        f"disabled: {', '.join(ignored())} (docstring-required family, subprocess policy); "
        f"{', '.join(XML_PARSER)} when the project's Expat is at least {'.'.join(map(str, SAFE_EXPAT))}"
    )
