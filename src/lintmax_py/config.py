# Copyright (c) lintmax-py contributors. Licensed under the MIT License.
from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path

import tomllib

from . import rules
from .dprint import bump
from .paths import GLOB_EXCLUDES, generated

LINE_LENGTH = 123

DELETING_FIXES = ("T201", "T203")
"""Rules whose autofix DELETES the flagged statement, which in a command-line program is its output.

The finding stays an error; only the automatic deletion is withheld, so the author replaces the call
with the program's real output channel instead of a fixer silently removing what the program says.
"""

DPRINT_SEED = [
    "https://plugins.dprint.dev/json-0.23.0.wasm",
    "https://plugins.dprint.dev/markdown-0.22.1.wasm",
    "https://plugins.dprint.dev/toml-0.7.0.wasm",
    "https://plugins.dprint.dev/dockerfile-0.4.1.wasm",
    "https://plugins.dprint.dev/g-plane/pretty_yaml-v0.6.0.wasm",
    "https://plugins.dprint.dev/g-plane/malva-v0.16.0.wasm",
    "https://plugins.dprint.dev/g-plane/markup_fmt-v0.27.3.wasm",
    "https://plugins.dprint.dev/g-plane/pretty_graphql-v0.2.3.wasm",
    "https://plugins.dprint.dev/bartlomieju/lax-sql-0.3.0.wasm",
]

EXCLUDES = GLOB_EXCLUDES

TEST_GLOBS = ("**/tests/**/*.py", "**/test_*.py", "**/*_test.py", "**/conftest.py")
TEST_IGNORES = ("S101", "PLR2004", "INP001", "PLC2701", "SLF001")
"""Rules whose own purpose statement excludes test code, scoped to test files ONLY.

`assert` is pytest's assertion API rather than a production shortcut, a test's expected value IS a
literal so naming it only restates the assertion, a test directory carries no `__init__.py` by
design, and a test that never reaches its subject's internals cannot pin them. Nothing that ships
loses a rule: every one of these stays enforced on every other file in the tree.
"""


def _test_scoping() -> str:
    body = json.dumps(list(TEST_IGNORES))
    return "".join(f"{json.dumps(glob)} = {body}\n" for glob in TEST_GLOBS)


def confusables(root: Path) -> list[str]:
    """Read the characters a project declares as belonging to its own writing system.

    The ambiguous-character rule hunts homoglyphs, and on a codebase whose domain language is not
    Latin its correct punctuation reads as an attack: full-width parentheses inside Japanese prose
    are right, and rewriting them alters the text the product ships. That is vocabulary rather than
    strictness, exactly like the spelling dictionary, so the project declares it and the rule stays
    on for every character it did not name.

    Returns:
        The declared characters, or nothing when the project names none.

    """
    for name in ("ruff.toml", ".ruff.toml", "pyproject.toml"):
        path = root / name
        try:
            parsed = tomllib.loads(path.read_text(encoding="utf-8"))
        except (OSError, tomllib.TOMLDecodeError):
            continue
        node = parsed.get("tool", {}).get("ruff") if path.name == "pyproject.toml" else parsed
        section = node.get("lint") if isinstance(node, dict) else None
        declared = section.get("allowed-confusables") if isinstance(section, dict) else None
        if isinstance(declared, list) and declared:
            return [str(char) for char in declared]
    return []


COPYRIGHT_RULE = "CPY001"
DEFAULT_NOTICE = "(?i)Copyright\\s+(\\(c\\)|©)"


def copyright_notice(root: Path) -> str:
    """Read the copyright notice a project requires in its files.

    The notice rule enforces nothing until a project states whose notice it wants: the holder is a
    legal fact about that codebase, not something a gate can supply. Enabled unconditionally it
    reports every file of every project that has made no such decision, which is noise rather than
    strictness. Declared, it is enforced on every file; undeclared, the rule stands down and nothing
    else relaxes.

    Returns:
        The notice pattern the project declares, or nothing when it declares none.

    """
    for name in ("ruff.toml", ".ruff.toml", "pyproject.toml"):
        path = root / name
        try:
            parsed = tomllib.loads(path.read_text(encoding="utf-8"))
        except (OSError, tomllib.TOMLDecodeError):
            continue
        node = parsed.get("tool", {}).get("ruff") if path.name == "pyproject.toml" else parsed
        section = node.get("lint") if isinstance(node, dict) else None
        table = section.get("flake8-copyright") if isinstance(section, dict) else None
        declared = table.get("notice-rgx") if isinstance(table, dict) else None
        if isinstance(declared, str) and declared:
            return declared
    return ""


def toml_array(key: str, items: list[str]) -> str:
    """Emit a TOML array assignment in exactly the shape the formatter leaves it.

    The gate's own formatter also reads the config the gate writes, so an array the formatter would
    re-wrap is a finding about the gate rather than the project. An assignment that fits the line
    width stays on one line; a longer one goes one item per line with a trailing comma.

    Returns:
        The assignment line or block, ending in a newline.

    """
    inline = f"{key} = {json.dumps(items, ensure_ascii=False)}"
    if len(inline) <= LINE_LENGTH:
        return inline + "\n"
    body = "".join(f"  {json.dumps(item, ensure_ascii=False)},\n" for item in items)
    return f"{key} = [\n{body}]\n"


def ruff_toml(inventory: list[dict[str, object]], root: Path) -> str:
    select = rules.selection(inventory)
    ignore = rules.ignored()
    allowed = confusables(root)
    allowed_line = toml_array("allowed-confusables", allowed) if allowed else ""
    notice = copyright_notice(root)
    if not notice:
        ignore = [*ignore, COPYRIGHT_RULE]
    return (
        "preview = true\n"
        f"line-length = {LINE_LENGTH}\n"
        f"{toml_array('exclude', [*EXCLUDES, *_absolute(root)])}"
        "[lint]\n"
        f"{toml_array('select', select)}"
        f"{toml_array('ignore', ignore)}"
        f"{allowed_line}"
        f"{toml_array('unfixable', list(DELETING_FIXES))}"
        f"[lint.per-file-ignores]\n{_test_scoping()}"
        "[lint.flake8-quotes]\n"
        'inline-quotes = "double"\n'
        "[lint.flake8-copyright]\n"
        f"notice-rgx = {json.dumps(notice or DEFAULT_NOTICE)}\n"
        "[format]\n"
        "docstring-code-format = true\n"
    )


def _absolute(root: Path) -> list[str]:
    """Anchor declared generated paths to the project, since the generated config lives elsewhere.

    Returns:
        Each declared pattern as an absolute glob, plus its contents.

    """
    return [glob for pat in generated(root) for glob in (str(root / pat), str(root / pat / "**"))]


def dprint_json(root: Path) -> str:
    return (
        json.dumps(
            {
                "lineWidth": LINE_LENGTH,
                "indentWidth": 2,
                "useTabs": False,
                "newLineKind": "lf",
                "includes": ["**/*"],
                "excludes": [*EXCLUDES, *_absolute(root)],
                "plugins": bump(DPRINT_SEED),
            },
            indent=2,
        )
        + "\n"
    )


VOCABULARY_FILES = ("typos.toml", "_typos.toml", ".typos.toml", "pyproject.toml")
VOCABULARY_TABLES = ("extend-words", "extend-identifiers")


def vocabulary(root: Path) -> dict[str, dict[str, str]]:
    """Read the project's own spelling dictionary from the config the speller itself discovers.

    A spell checker with no project dictionary reports every domain noun a codebase owns — a client
    name, a product name, a protocol token — as a misspelling, and the only escapes are renaming the
    domain or turning the stage off. Neither is acceptable, so the dictionary is merged in. The
    speller resolves one config file and offers no inheritance, and the gate passes its own generated
    config, so a project file would otherwise be ignored entirely.

    Only the two vocabulary tables are read. The switches stay owned by the gate, so a project can
    name the words it uses and cannot weaken the check that reads them.

    Returns:
        The vocabulary tables present in the first config file that carries the speller's section.

    """
    for name in VOCABULARY_FILES:
        section = _typos_section(root / name)
        if section is None:
            continue
        found: dict[str, dict[str, str]] = {}
        for table in VOCABULARY_TABLES:
            entries = section.get(table)
            if isinstance(entries, dict):
                found[table] = {str(word): str(correction) for word, correction in entries.items()}
        if found:
            return found
    return {}


def _typos_section(path: Path) -> dict[str, object] | None:
    try:
        parsed = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return None
    node = parsed.get("tool", {}).get("typos") if path.name == "pyproject.toml" else parsed
    if not isinstance(node, dict):
        return None
    default = node.get("default")
    if not isinstance(default, dict):
        return None
    return {str(key): value for key, value in default.items()}


def typos_toml(root: Path) -> str:
    body = "[default]\ncheck-filename = true\ncheck-file = true\n"
    for table, entries in vocabulary(root).items():
        body += f"[default.{table}]\n"
        body += "".join(f"{json.dumps(word)} = {json.dumps(correction)}\n" for word, correction in sorted(entries.items()))
    return body


def materialize(inventory: list[dict[str, object]], root: Path) -> tuple[Path, str]:
    cfg_root = Path(tempfile.mkdtemp(prefix="lintmax-py-"))
    written = {
        "ruff.toml": ruff_toml(inventory, root),
        "dprint.json": dprint_json(root),
        "typos.toml": typos_toml(root),
    }
    for name, body in written.items():
        (cfg_root / name).write_text(body, encoding="utf-8")
    digest = hashlib.sha256("".join(written.values()).encode()).hexdigest()
    return cfg_root, digest


VULTURE_KEYS = ("ignore_decorators", "ignore_names")


def vulture_allowances(root: Path) -> dict[str, list[str]]:
    """Read what a project declares its dead-code analysis cannot see.

    A function reached only through a registration decorator, and an attribute read only by a
    metaclass, are both live and both invisible to a static reachability scan — so the scan reports
    every route handler and every model field as dead. That is a fact about the frameworks a project
    uses, which the gate cannot know and the project can state, exactly like its spelling dictionary.

    Only the two allowance lists are read; nothing a project writes can switch the stage off.

    Returns:
        The declared allowances, keyed by the flag they populate.

    """
    try:
        parsed = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return {}
    section = parsed.get("tool", {}).get("vulture")
    if not isinstance(section, dict):
        return {}
    found: dict[str, list[str]] = {}
    for key in VULTURE_KEYS:
        declared = section.get(key)
        if isinstance(declared, list) and declared:
            found[key] = [str(item) for item in declared]
    return found
