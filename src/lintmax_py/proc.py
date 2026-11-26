# Copyright (c) lintmax-py contributors. Licensed under the MIT License.
from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Result:
    code: int
    out: str


@dataclass(frozen=True, slots=True, kw_only=True)
class RunIO:
    input_bytes: bytes | None = None
    raw_output: bool = False


DEFAULT_IO = RunIO()


def run(
    argv: list[str],
    cwd: str | None = None,
    timeout: int = 1800,
    env: dict[str, str] | None = None,
    *,
    io: RunIO = DEFAULT_IO,
) -> Result:
    if shutil.which(argv[0]) is None:
        return Result(code=127, out=f"{argv[0]}: not installed")
    try:
        done = subprocess.run(
            argv,
            cwd=cwd,
            env=env,
            capture_output=True,
            input=io.input_bytes,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return Result(code=124, out=f"{argv[0]}: timed out after {timeout}s")
    except OSError as err:
        return Result(code=126, out=f"{argv[0]}: {err}")
    if io.raw_output and done.returncode == 0:
        return Result(code=0, out=done.stdout.decode("utf-8", errors="surrogateescape"))
    output = (done.stdout + done.stderr).decode("utf-8", errors="replace")
    return Result(code=done.returncode, out=output.replace("\r\n", "\n").replace("\r", "\n").strip())
