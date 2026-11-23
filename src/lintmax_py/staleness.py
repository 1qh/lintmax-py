# Copyright (c) lintmax-py contributors. Licensed under the MIT License.
from __future__ import annotations

import json
import os
import re
import tomllib
import urllib.error
import urllib.request
from typing import TYPE_CHECKING

from packaging.requirements import InvalidRequirement, Requirement
from packaging.version import InvalidVersion, Version

if TYPE_CHECKING:
    from pathlib import Path

TIMEOUT = 15
NAME_RE = re.compile(r"^[A-Za-z0-9._-]+")


def skip() -> bool:
    return bool(os.environ.get("LINTMAX_SKIP_STALENESS"))


def specs(root: Path) -> list[str]:
    manifest = root / "pyproject.toml"
    if not manifest.is_file():
        return []
    data = tomllib.loads(manifest.read_text(encoding="utf-8"))
    project = data.get("project", {})
    lists = [
        project.get("dependencies", []),
        *data.get("dependency-groups", {}).values(),
        *project.get("optional-dependencies", {}).values(),
        data.get("build-system", {}).get("requires", []),
    ]
    return [item for entries in lists for item in entries if isinstance(item, str)]


def declared(root: Path) -> list[str]:
    names = []
    for spec in specs(root):
        match = NAME_RE.match(spec.strip())
        if match:
            names.append(match.group(0).lower().replace("_", "-"))
    return sorted(set(names))


def excluded(root: Path, newest: dict[str, str]) -> list[str]:
    found = []
    for spec in specs(root):
        try:
            requirement = Requirement(spec)
            version = Version(newest.get(requirement.name.lower().replace("_", "-"), ""))
        except (InvalidRequirement, InvalidVersion):
            continue
        if requirement.specifier and not requirement.specifier.contains(version, prereleases=version.is_prerelease):
            found.append(f"{spec} excludes {requirement.name} {version}")
    return found


def locked(root: Path) -> dict[str, str]:
    lock = root / "uv.lock"
    if not lock.is_file():
        return {}
    data = tomllib.loads(lock.read_text(encoding="utf-8"))
    return {
        str(pkg["name"]).lower(): str(pkg["version"])
        for pkg in data.get("package", [])
        if "name" in pkg and "version" in pkg
    }


def holds(root: Path) -> dict[str, str]:
    manifest = root / "pyproject.toml"
    if not manifest.is_file():
        return {}
    data = tomllib.loads(manifest.read_text(encoding="utf-8"))
    section = data.get("tool", {}).get("lintmax-py")
    declared = section.get("holds", {}) if isinstance(section, dict) else {}
    if not isinstance(declared, dict):
        msg = "tool.lintmax-py.holds must be a table of package names and non-empty reasons"
        raise TypeError(msg)
    for name, reason in declared.items():
        if not isinstance(reason, str) or not reason.strip():
            msg = f"tool.lintmax-py.holds.{name} must be a non-empty string explaining the hold and when to revisit it"
            raise ValueError(msg)
    return {name.lower(): reason for name, reason in declared.items()}


def latest(name: str) -> str | None:
    try:
        with urllib.request.urlopen(
            f"https://pypi.org/pypi/{name}/json",
            timeout=TIMEOUT,
        ) as response:
            body = json.load(response)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        return None
    version = body.get("info", {}).get("version")
    return str(version) if version else None


def behind(root: Path) -> list[str]:
    if skip():
        return []
    held = holds(root)
    names = declared(root)
    pinned = locked(root)
    stale = [f"hold names an undeclared package: {name}" for name in sorted(held.keys() - set(names))]
    newest: dict[str, str] = {}
    for name in names:
        found = latest(name)
        if found is not None:
            newest[name] = found
    for name in names:
        current = pinned.get(name)
        if current is None or name not in newest:
            continue
        if name in held:
            if newest[name] == current:
                stale.append(f"hold no longer needed: {name} {current}")
        elif newest[name] != current:
            stale.append(f"{name} {current} -> {newest[name]}")
    stale += [
        line
        for line in excluded(root, {name: version for name, version in newest.items() if name not in held})
        if line not in stale
    ]
    return stale
