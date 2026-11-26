# Copyright (c) lintmax-py contributors. Licensed under the MIT License.
from __future__ import annotations

import hashlib
import json
import re
import time
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path

HOST = "https://plugins.dprint.dev/"
TIMEOUT = 15
TTL_SECONDS = 6 * 60 * 60


VERSION_SUFFIX = re.compile(r"[-@]v?\d+\.\d+\.\d+$")
MARKDOWN_SUFFIXES = frozenset({".md", ".markdown", ".mdown", ".mkd", ".mkdn", ".mdwn"})
FENCE = re.compile(rb"^ {0,3}(`{3,}(?!`)|~{3,}(?!~))(.*)$")
BACKTICKS = re.compile(rb"`+")
BACKSLASHES = re.compile(rb"\\+\Z")


def _inline_blocks(source: bytes) -> list[bytes]:
    blocks: list[bytes] = []
    lines: list[bytes] = []
    fence = b""
    for line in source.splitlines(keepends=True):
        match = FENCE.fullmatch(line.rstrip(b"\r\n"))
        if fence:
            if match and match[1].startswith(fence) and not match[2].strip():
                fence = b""
            continue
        if match and (match[1].startswith(b"~") or b"`" not in match[2]):
            fence = match[1]
        elif line.strip():
            lines.append(line)
            continue
        if lines:
            blocks.append(b"".join(lines))
            lines.clear()
    if lines:
        blocks.append(b"".join(lines))
    return blocks


def _inline_spans(source: bytes) -> list[bytes]:
    spans: list[bytes] = []
    for block in _inline_blocks(source):
        end = 0
        for opening in BACKTICKS.finditer(block):
            if opening.start() < end:
                continue
            escape = BACKSLASHES.search(block, 0, opening.start())
            width = len(opening[0]) - (len(escape[0]) % 2 if escape else 0)
            if width == 0:
                continue
            for closing in BACKTICKS.finditer(block, opening.end()):
                if len(closing[0]) == width:
                    spans.append(block[opening.end() : closing.start()])
                    end = closing.end()
                    break
    return spans


def changed_code_span(original: bytes, formatted: bytes) -> str | None:
    before = _inline_spans(original)
    after = _inline_spans(formatted)
    removed = Counter(before) - Counter(after)
    added = Counter(after) - Counter(before)
    if removed:
        span = next(iter(removed)).decode("utf-8", errors="replace")
        return f"formatting would change inline code span {span!r}"
    if added:
        span = next(iter(added)).decode("utf-8", errors="replace")
        return f"formatting would introduce inline code span {span!r}"
    return None


def plugin_name(file: str) -> str:
    """Strip the VERSION off a plugin's filename, never split at the first separator.

    A plugin whose own name carries a hyphen resolves to the wrong plugin entirely under a
    split-at-the-first-hyphen rule, and the wrong name still LOOKS like a name — so the failure is a
    404 against a plausible URL rather than anything that reads as a parsing bug.

    Returns:
        The plugin's name without its version.

    """
    return VERSION_SUFFIX.sub("", file)


def plugin_path(pinned: str) -> str | None:
    if not pinned.startswith(HOST):
        return None
    tail = pinned[len(HOST) :]
    if "." not in tail:
        return None
    file = tail.rsplit(".", 1)[0]
    if "/" in file:
        owner, rest = file.split("/", 1)
        return f"{owner}/{plugin_name(rest)}"
    return f"dprint/{plugin_name(file)}"


def latest_url(path: str) -> str | None:
    try:
        with urllib.request.urlopen(f"{HOST}{path}/latest.json", timeout=TIMEOUT) as response:  # ruff: ignore[suspicious-url-open-usage]
            body = json.load(response)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        return None
    url = body.get("url") if isinstance(body, dict) else None
    return url if isinstance(url, str) and url.startswith(HOST) else None


def _cache_path(seed: list[str]) -> Path:
    key = hashlib.sha256("\n".join(seed).encode()).hexdigest()[:16]
    return Path.home() / ".cache" / "lintmax-py" / f"{key}.plugins"


def _cached(seed: list[str], *, force: bool) -> list[str] | None:
    if force:
        return None
    path = _cache_path(seed)
    if not path.is_file():
        return None
    try:
        body = json.loads(path.read_text(encoding="utf-8"))
        stamped = float(body["stamp"])
        resolved = body["plugins"]
    except (json.JSONDecodeError, KeyError, ValueError, OSError):
        return None
    if time.time() - stamped >= TTL_SECONDS:
        return None
    return [str(p) for p in resolved] if isinstance(resolved, list) else None


def _store(seed: list[str], resolved: list[str]) -> None:
    path = _cache_path(seed)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"stamp": time.time(), "plugins": resolved}),
        encoding="utf-8",
    )


def bump(plugins: list[str], *, force: bool = False) -> list[str]:
    hit = _cached(plugins, force=force)
    if hit is not None:
        return hit
    out: list[str] = []
    for pinned in plugins:
        path = plugin_path(pinned)
        latest = latest_url(path) if path is not None else None
        out.append(latest if latest is not None else pinned)
    _store(plugins, out)
    return out
