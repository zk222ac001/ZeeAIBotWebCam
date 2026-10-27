#!/usr/bin/env python3
"""Prepare separate Studio access tokens without displaying credentials.

Dry-run by default. Applying requires root and never restarts the application,
changes hardware settings, or promotes physical acceptance flags.
"""
from __future__ import annotations

import argparse
import os
import re
import secrets
import stat
import sys
import tempfile
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

DEFAULT_ENV = Path("/etc/zee-robot/zee-robot.env")
MARKER = "# ZeeAI Studio access (managed by setup_studio_access.py)"
KEYS = (
    "CONFERENCE_AUTH_REQUIRED", "CONFERENCE_ACCESS_TOKEN",
    "CONTROL_AUTH_REQUIRED", "CONTROL_ACCESS_TOKEN",
)
ASSIGNMENT = re.compile(r"^\s*(" + "|".join(KEYS) + r")\s*=(.*)$")
TOKEN = re.compile(r"[A-Za-z0-9._~+/=-]{16,256}\Z")


def existing_token(value: str) -> str:
    candidate = value.strip()
    if len(candidate) >= 2 and candidate[0] in {"'", '"'} and candidate[-1] == candidate[0]:
        candidate = candidate[1:-1]
    if (not TOKEN.fullmatch(candidate)
            or candidate.lower().startswith(("replace-", "change-me", "your-"))):
        raise ValueError(
            "An existing access token cannot be safely preserved. "
            "Review the file locally or use --rotate to replace both tokens."
        )
    return candidate


def prepare_environment(
    original: str, *, rotate: bool = False, token_factory: Callable[[], str] | None = None,
) -> tuple[str, int]:
    """Keep unrelated environment lines and reuse valid credentials by default."""
    values: dict[str, str] = {}
    retained: list[str] = []
    for line in original.splitlines(keepends=True):
        assignment = ASSIGNMENT.match(line.rstrip("\r\n"))
        if assignment:
            value = assignment[2].strip()
            if value.endswith("\\") or (value[:1] in {"'", '"'} and value[-1:] != value[:1]):
                raise ValueError("Multiline or continued access settings require manual review.")
            values[assignment[1]] = assignment[2]
        elif line.rstrip("\r\n") != MARKER:
            retained.append(line)
    create_token = token_factory or (lambda: secrets.token_urlsafe(32))
    tokens: dict[str, str] = {}
    generated = 0
    for key in ("CONFERENCE_ACCESS_TOKEN", "CONTROL_ACCESS_TOKEN"):
        if key in values and values[key].strip() not in {"", "''", '""'} and not rotate:
            tokens[key] = existing_token(values[key])
        else:
            tokens[key] = create_token()
            if not TOKEN.fullmatch(tokens[key]):
                raise ValueError("The generated token does not meet the expected format")
            generated += 1
    if len(set(tokens.values())) != 2:
        raise ValueError("Conference and control tokens must differ. Use --rotate to replace them.")
    prefix = "".join(retained).rstrip("\r\n")
    managed = "\n".join([
        MARKER, "CONFERENCE_AUTH_REQUIRED=true",
        f"CONFERENCE_ACCESS_TOKEN={tokens['CONFERENCE_ACCESS_TOKEN']}",
        "CONTROL_AUTH_REQUIRED=true", f"CONTROL_ACCESS_TOKEN={tokens['CONTROL_ACCESS_TOKEN']}",
    ]) + "\n"
    return (prefix + "\n\n" if prefix else "") + managed, generated


def read_environment(path: Path) -> str:
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise ValueError("The environment path must be a regular file, not a symlink")
    if not path.exists():
        return ""
    if path.stat().st_size > 65536:
        raise ValueError("Environment file exceeds the expected size; review it manually")
    return path.read_text(encoding="utf-8")


def atomic_write(path: Path, content: str) -> None:
    """Replace a file only after a complete, flushed, mode-0600 write."""
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise ValueError("Refusing to replace a symlink or non-regular file")
    descriptor, temporary_name = tempfile.mkstemp(prefix=".zee-access-", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as output:
            os.fchmod(output.fileno(), 0o600)
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        temporary.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="write settings; requires root")
    parser.add_argument("--rotate", action="store_true", help="replace both existing access tokens")
    parser.add_argument("--env-file", type=Path, default=DEFAULT_ENV)
    args = parser.parse_args(argv)
    if args.apply and os.geteuid() != 0:
        print("Applying access settings requires sudo; no files were changed.", file=sys.stderr)
        return 2
    try:
        path = args.env_file.absolute()
        if path.parent.is_symlink():
            raise ValueError("The environment directory must not be a symlink")
        if args.apply and path.parent.exists():
            info = path.parent.stat()
            if info.st_uid != 0 or stat.S_IMODE(info.st_mode) & 0o022:
                raise ValueError("The environment directory must be root-owned and not group/world-writable")
        original = read_environment(path)
        updated, generated = prepare_environment(original, rotate=args.rotate)
        if not args.apply:
            print(f"Dry run: enable both access gates; create {generated} token(s), preserve {2-generated}.")
            print("Other environment settings are preserved. No files changed; no credentials displayed.")
            return 0
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        changed = original != updated
        if changed and path.exists():
            stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S.%fZ")
            backup = path.with_name(path.name + ".pre-studio-access-" + stamp)
            atomic_write(backup, original)
        atomic_write(path, updated)
        print("Access settings saved with mode 0600. No credentials displayed.")
        print(f"Created {generated} token(s); preserved {2-generated} existing token(s).")
        print("Copy the two tokens locally using sudoedit /etc/zee-robot/zee-robot.env.")
        print("Then restart zee-robot.service and enter them in Studio Access settings.")
        print("Service state, hardware settings and validation flags were not changed.")
        return 0
    except (OSError, ValueError) as exc:
        if isinstance(exc, PermissionError):
            print("Root access is needed to read the existing environment file; no changes made.", file=sys.stderr)
        elif isinstance(exc, ValueError):
            print(str(exc), file=sys.stderr)
        else:
            print(f"Could not update the environment file ({type(exc).__name__}).", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
