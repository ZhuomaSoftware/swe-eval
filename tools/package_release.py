"""Validate Python distributions and assemble an explicit, credential-free bundle.

Run `python -m build --no-isolation` first, then this script from any directory.
No benchmark repository code is imported or executed by packaging.
"""
from __future__ import annotations

import argparse
import email.parser
import gzip
import hashlib
import io
import json
import os
import re
import tarfile
import tomllib
import zipfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
DATA_FILES = (
    "task.json", "known_good.patch", "hidden/grade.py",
    "repository/intervals.py", "repository/test_public.py", "repository/README.md",
)
DEPLOY_FILES = (
    "README.md", "VALIDATION.md", "pyproject.toml", "MANIFEST.in",
    "compose.yaml", "compose.packaged.yaml", ".env.example", ".dockerignore", ".gitignore",
    "requirements-core.lock", "requirements-agent.lock", "requirements-test.lock", "requirements-build.lock",
    "config/models.json",
    "docker/service.Dockerfile", "docker/sandbox.Dockerfile", "docker/grader.Dockerfile",
    "tools/package_release.py",
)
FORBIDDEN = {".git", ".venv", ".env", "models.local.json", "__pycache__"}


def safe_paths(names):
    for name in names:
        path = PurePosixPath(name)
        if path.is_absolute() or ".." in path.parts or FORBIDDEN.intersection(path.parts):
            raise ValueError(f"unsafe distribution member: {name}")
        if path.suffix in {".pyc", ".pyo", ".sqlite3"}:
            raise ValueError(f"runtime artifact in distribution: {name}")


def check_distributions(directory: Path, project: dict):
    wheels = list(directory.glob("*.whl"))
    source_name = project["name"].replace("-", "_") + "-" + project["version"]
    sdist = directory / f"{source_name}.tar.gz"
    if len(wheels) != 1 or not sdist.is_file():
        raise ValueError("expected exactly one wheel and the matching source distribution")
    with zipfile.ZipFile(wheels[0]) as wheel:
        if wheel.testzip() is not None:
            raise ValueError("wheel CRC validation failed")
        names = set(wheel.namelist())
        safe_paths(names)
        required = {"swe_eval/benchmarks/data/intervals/" + path for path in DATA_FILES}
        if not required <= names:
            raise ValueError("wheel is missing benchmark fixture files")
        metadata_files = [name for name in names if name.endswith(".dist-info/METADATA")]
        if len(metadata_files) != 1:
            raise ValueError("invalid wheel metadata")
        metadata = email.parser.BytesParser().parsebytes(wheel.read(metadata_files[0]))
        if metadata["Name"] != project["name"] or metadata["Version"] != project["version"]:
            raise ValueError("wheel name/version differs from pyproject.toml")
    with tarfile.open(sdist, "r:gz") as source:
        members = source.getmembers()
        names = {item.name for item in members}
        safe_paths(names)
        if any(not (item.isfile() or item.isdir()) for item in members):
            raise ValueError("source distribution must contain only regular files/directories")
        required = {f"{source_name}/{path}" for path in DEPLOY_FILES}
        required |= {f"{source_name}/src/swe_eval/benchmarks/data/intervals/{path}" for path in DATA_FILES}
        if not required <= names:
            raise ValueError("source distribution is missing deployment or benchmark files")


def deployment_archive(directory: Path, project: dict):
    version = project["version"]
    if not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}", version):
        raise ValueError("version is not suitable for a Docker tag")
    prefix = f"swe-eval-{version}"
    destination = directory / f"{prefix}-deploy.tar.gz"
    timestamp = int(os.getenv("SOURCE_DATE_EPOCH", "0"))
    files = [ROOT / name for name in DEPLOY_FILES]
    for path in sorted((ROOT / "src/swe_eval").rglob("*")):
        if path.is_symlink():
            raise ValueError("symlinks are not permitted in deployment source")
        if path.is_file() and "__pycache__" not in path.parts and path.suffix not in {".pyc", ".pyo"}:
            files.append(path)
    metadata = {
        "version": version, "repository": project["urls"]["Repository"],
        "commit": os.getenv("GITHUB_SHA"), "source_date_epoch": timestamp,
        "image_tag": version, "docker_platform": "linux/amd64",
    }
    entries = [(path.relative_to(ROOT).as_posix(), path) for path in files]
    safe_paths(name for name, _ in entries)
    with destination.open("wb") as target, gzip.GzipFile(fileobj=target, mode="wb", filename="", mtime=0) as compressed:
        with tarfile.open(fileobj=compressed, mode="w") as archive:
            for name, path in entries:
                if path.is_symlink() or not path.is_file():
                    raise ValueError(f"deployment source must be a regular file: {name}")
                data = path.read_bytes()
                info = tarfile.TarInfo(f"{prefix}/{name}")
                info.size, info.mode, info.mtime = len(data), 0o644, timestamp
                archive.addfile(info, io.BytesIO(data))
            data = (json.dumps(metadata, indent=2) + "\n").encode()
            info = tarfile.TarInfo(f"{prefix}/build-info.json")
            info.size, info.mode, info.mtime = len(data), 0o644, timestamp
            archive.addfile(info, io.BytesIO(data))
    (directory / "build-info.json").write_text(json.dumps(metadata, indent=2) + "\n")
    return destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dist-dir", type=Path, default=ROOT / "dist")
    args = parser.parse_args()
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
    directory = args.dist_dir.resolve()
    check_distributions(directory, project)
    deployment_archive(directory, project)
    artifacts = sorted([*directory.glob("*.whl"), *directory.glob("*.tar.gz"), directory / "build-info.json"])
    with (directory / "SHA256SUMS").open("w") as checksums:
        for path in artifacts:
            with path.open("rb") as source:
                digest = hashlib.file_digest(source, "sha256").hexdigest()
            checksums.write(f"{digest}  {path.name}\n")
    print(f"Validated and packaged {project['name']} {project['version']} in {directory}")


if __name__ == "__main__":
    main()
