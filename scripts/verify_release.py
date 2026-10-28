#!/usr/bin/env python3
"""Verify an extracted, unmodified release before installation (no hardware access)."""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path


def verify(root: Path) -> list[str]:
    if (root / "SHA256SUMS").is_symlink():
        raise ValueError("Checksum inventory must not be a symlink")
    problems = []
    expected = set()
    for line in (root / "SHA256SUMS").read_text().splitlines():
        digest, name = line.split("  ", 1)
        relative = Path(name)
        if relative.is_absolute() or ".." in relative.parts or name in expected:
            raise ValueError("Invalid checksum path")
        expected.add(name)
        target = root / relative
        if any(p.is_symlink() for p in (target, *target.parents)):
            problems.append(f"Symlink is not allowed: {name}")
        elif not target.is_file() or hashlib.sha256(target.read_bytes()).hexdigest() != digest:
            problems.append(f"Missing or changed file: {name}")
    actual = {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file() or p.is_symlink()}
    if actual != expected | {"SHA256SUMS"}:
        problems.append("Release file inventory differs from the checksums")
    if not expected:
        problems.append("Release checksum inventory is empty")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", type=Path)
    args = parser.parse_args()
    try:
        problems = verify(args.folder.resolve())
    except (OSError, ValueError):
        print("FAIL: release checksum inventory cannot be read")
        return 1
    if problems:
        print("FAIL: release integrity check")
        for problem in problems:
            print(f"  - {problem}")
        return 1
    print("PASS: release file inventory and SHA-256 checksums match")
    print("Checksums detect changes; they do not authenticate the release publisher.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
