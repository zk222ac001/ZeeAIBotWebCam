#!/usr/bin/env python3
"""Build a release candidate from an allowlisted source snapshot.

Requires an installed development/WebRTC environment. No hardware access,
service changes, dependency downloads, acceptance flags or production promotion.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile
import tomllib
from importlib.metadata import PackageNotFoundError, distribution
from pathlib import Path

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

ROOT = Path(__file__).resolve().parents[1]
TOP_FILES = {"pyproject.toml", "README.md", "LICENSE", "SECURITY.md", "CONTRIBUTING.md",
             "config.yaml", "config.pi.yaml"}
EXTENSIONS = {"src": {".py", ".html", ".css", ".js", ".svg"}, "scripts": {".py", ".sh"},
              "docs": {".md"}, "tests": {".py"}, "deploy": {".in", ".example"},
              ".github": {".yml", ".yaml"}}


def run(command: list[str], cwd: Path, *, env: dict[str, str] | None = None) -> str:
    return subprocess.run(command, cwd=cwd, env=env, check=True,
                          capture_output=True, text=True, timeout=180).stdout.strip()


def source_files(root: Path) -> list[Path]:
    names = run(["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"], root)
    result = []
    for name in names.split("\0"):
        path = Path(name)
        if (not name or path.is_absolute() or ".." in path.parts
                or any(part in {"__pycache__", ".venv"} for part in path.parts)):
            continue
        included = name in TOP_FILES or path.suffix in EXTENSIONS.get(path.parts[0], set())
        if included:
            if (root / path).is_symlink():
                raise ValueError("Release source must not contain symlinks")
            if (root / path).is_file():
                result.append(path)
    return sorted(set(result))


def runtime_constraints(project: dict) -> str:
    requirements = list(project["dependencies"]) + list(project["optional-dependencies"]["webrtc"])
    visited = set()
    versions: dict[str, str] = {}
    while requirements:
        req = Requirement(requirements.pop())
        # Dependency requirements added below already have their extra marker evaluated.
        dist = distribution(req.name)
        name = canonicalize_name(req.name)
        if req.specifier and not req.specifier.contains(dist.version, prereleases=True):
            raise ValueError(f"Installed {name} does not satisfy the project requirements")
        versions[name] = dist.version
        key = (name, tuple(sorted(req.extras)))
        if key in visited:
            continue
        visited.add(key)
        for value in dist.requires or []:
            child = Requirement(value)
            if child.marker and not any(child.marker.evaluate({"extra": extra})
                                        for extra in ("", *req.extras)):
                continue
            child.marker = None
            requirements.append(str(child))
    return ("# Runtime and WebRTC constraints from the build environment.\n"
            "# Platform-specific snapshot; excludes OS drivers and the external vendor SDK.\n"
            + "".join(f"{name}=={version}\n" for name, version in sorted(versions.items())))


def hashes(folder: Path) -> dict[str, str]:
    return {p.relative_to(folder).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(folder.rglob("*")) if p.is_file()}


def reject_config_secrets(snapshot: Path) -> None:
    import yaml

    for name in ("config.yaml", "config.pi.yaml"):
        try:
            config = yaml.safe_load((snapshot / name).read_text())
        except yaml.YAMLError:
            raise ValueError("Release YAML must be valid; review it locally") from None
        conference = config.get("conference", {})
        if any(conference.get(key) for key in ("access_token", "ice_credential", "ice_username")):
            raise ValueError("Remove private credentials from YAML before building a release")
        if config.get("control_access", {}).get("access_token"):
            raise ValueError("Remove private credentials from YAML before building a release")


def vendor_fingerprint(root: Path) -> dict:
    vendor = root / "vendor/TurboPi"
    if not (vendor / ".git").exists():
        return {"recorded": False}
    files = {}
    for name in ("ros_robot_controller_sdk.py", "Sonar.py", "FourInfrared.py"):
        path = vendor / "HiwonderSDK" / name
        files[f"HiwonderSDK/{name}"] = hashlib.sha256(path.read_bytes()).hexdigest()
    return {"recorded": True, "revision": run(["git", "rev-parse", "HEAD"], vendor),
            "local_modifications": bool(run(["git", "status", "--porcelain"], vendor)),
            "driver_sha256": files}


def build(root: Path, output: Path) -> Path:
    project = tomllib.loads((root / "pyproject.toml").read_text())["project"]
    with tempfile.TemporaryDirectory(prefix="zee-release-") as temporary:
        work = Path(temporary)
        snapshot = work / "snapshot"
        snapshot.mkdir()
        for relative in source_files(root):
            destination = snapshot / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(root / relative, destination)
        reject_config_secrets(snapshot)
        source_hashes = hashes(snapshot)
        source_digest = hashlib.sha256(json.dumps(source_hashes, sort_keys=True).encode()).hexdigest()
        constraints = runtime_constraints(project)
        vendor = vendor_fingerprint(root)
        identity = {"source": source_digest, "constraints": constraints, "vendor": vendor,
                    "python": list(sys.version_info[:2]), "system": sys.platform,
                    "architecture": platform.machine()}
        release_digest = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
        release_id = f"zeeai-studio-{project['version']}-{release_digest[:12]}"
        candidate = work / release_id
        shutil.copytree(snapshot, candidate)
        artifact_dir = candidate / "artifacts"
        artifact_dir.mkdir()
        env = dict(os.environ, SOURCE_DATE_EPOCH="315532800", PIP_NO_INDEX="1")
        run([sys.executable, "-m", "pip", "wheel", "--no-deps", "--no-build-isolation",
             "--wheel-dir", str(artifact_dir), str(snapshot)], root, env=env)
        (candidate / "runtime.constraints.txt").write_text(constraints)
        manifest = {
            "schema_version": 1, "release_id": release_id, "status": "candidate",
            "version": project["version"], "source_sha256": source_digest,
            "git_revision": run(["git", "rev-parse", "HEAD"], root),
            "uncommitted_changes": bool(run(["git", "status", "--porcelain"], root)),
            "python": platform.python_version(), "platform": platform.platform(),
            "production_accepted": False, "external_vendor": vendor,
            "external_requirements": ["Raspberry Pi OS camera/USB/serial drivers",
                                      "TurboPi SDK and device-specific physical calibration"],
            "files": hashes(candidate),
        }
        (candidate / "release-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
        checksums = hashes(candidate)
        (candidate / "SHA256SUMS").write_text("".join(
            f"{digest}  {name}\n" for name, digest in checksums.items()))
        output.mkdir(parents=True, exist_ok=True)
        destination = output / f"{release_id}.tar.gz"
        # Normalize archive timestamps and ownership for repeatable bundle contents.
        with (destination.open("wb") as raw,
              gzip.GzipFile(fileobj=raw, mode="wb", mtime=0, filename="") as zipped,
              tarfile.open(fileobj=zipped, mode="w") as archive):
            for path in sorted(candidate.rglob("*")):
                info = archive.gettarinfo(str(path), arcname=f"{release_id}/{path.relative_to(candidate)}")
                info.uid = info.gid = info.mtime = 0
                info.uname = info.gname = ""
                if path.is_file():
                    with path.open("rb") as content:
                        archive.addfile(info, content)
                else:
                    archive.addfile(info)
        return destination


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "dist")
    args = parser.parse_args()
    try:
        result = build(ROOT, args.output.resolve())
    except (OSError, ValueError, PackageNotFoundError, subprocess.SubprocessError):
        print("Release build failed. Check dependencies, source files and YAML credentials locally.", file=sys.stderr)
        return 1
    print(f"Release candidate: {result}")
    print("No hardware acceptance, service deployment or production promotion was performed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
