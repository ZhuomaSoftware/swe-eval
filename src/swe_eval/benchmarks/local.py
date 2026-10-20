from __future__ import annotations

import hashlib
import io
import json
import tarfile
from pathlib import Path
from typing import Protocol

from ..schema import Task

SNAPSHOT_COMMIT_MESSAGE = "Trusted benchmark baseline\n"
SNAPSHOT_IDENTITY = "SWE Eval <fixture@swe-eval.invalid> 1704067200 +0000"


class BenchmarkAdapter(Protocol):
    def list_tasks(self) -> list[Task]: ...
    def get_task(self, task_id: str) -> Task: ...
    def source_archive(self, task: Task) -> bytes: ...


def _object_hash(kind: str, data: bytes) -> bytes:
    return hashlib.sha1(f"{kind} {len(data)}\0".encode() + data).digest()


def snapshot_commit(root: Path) -> str:
    """Compute the exact Git commit of a canonical, regular-file snapshot."""
    def tree(directory):
        entries = []
        for item in directory.iterdir():
            if item.is_symlink() or item.name == ".git":
                raise ValueError("snapshot must contain only regular files/directories, without .git")
            if item.is_dir():
                oid = tree(item)
                if oid is None:
                    continue  # Git does not track empty directories.
                mode, sort_key = "40000", item.name + "/"
            elif item.is_file():
                mode, oid, sort_key = "100644", _object_hash("blob", item.read_bytes()), item.name
            else:
                raise ValueError("unsupported source entry")
            entries.append((sort_key.encode(), mode.encode() + b" " + item.name.encode() + b"\0" + oid))
        return _object_hash("tree", b"".join(value for _, value in sorted(entries))) if entries else None

    tree_hash = tree(root) or _object_hash("tree", b"")
    commit = (f"tree {tree_hash.hex()}\nauthor {SNAPSHOT_IDENTITY}\n"
              f"committer {SNAPSHOT_IDENTITY}\n\n{SNAPSHOT_COMMIT_MESSAGE}").encode()
    return _object_hash("commit", commit).hex()


class LocalBenchmark:
    """Only administrator-installed manifests and local snapshots/bundles are trusted."""

    def __init__(self, root: Path | None = None):
        self.root = (root or Path(__file__).parent / "data").resolve()
        self.tasks = {}
        for manifest in sorted(self.root.glob("*/task.json")):
            task = Task.model_validate(json.loads(manifest.read_text()))
            if task.id in self.tasks:
                raise ValueError("duplicate benchmark task ID")
            self.tasks[task.id] = (task, manifest.parent)

    def list_tasks(self):
        return [task for task, _ in self.tasks.values()]

    def get_task(self, task_id):
        return self.tasks[task_id][0]

    def source_path(self, task):
        directory = self.tasks[task.id][1]
        source = (directory / task.repository.path).resolve()
        if not source.is_relative_to(directory):
            raise ValueError("repository source must be inside the task directory")
        return source

    def source_archive(self, task):
        source = self.source_path(task)
        if task.repository.kind == "snapshot" and snapshot_commit(source) != task.base_commit:
            raise ValueError("source snapshot does not match base_commit")
        buffer = io.BytesIO()
        total = 0
        with tarfile.open(fileobj=buffer, mode="w") as archive:
            files = sorted(source.rglob("*")) if source.is_dir() else [source]
            for path in files:
                if path.is_symlink():
                    raise ValueError("symlinks are forbidden in source archives")
                if path.is_dir():
                    continue
                if not path.is_file():
                    raise ValueError("non-regular source file")
                name = path.relative_to(source).as_posix() if source.is_dir() else "source.bundle"
                if ".git" in name.split("/"):
                    raise ValueError("use a git bundle rather than copying .git")
                data = path.read_bytes()
                total += len(data)
                if total > 32 * 1024 * 1024:
                    raise ValueError("source exceeds 32 MiB MVP limit")
                info = tarfile.TarInfo(name)
                info.size, info.mode, info.mtime = len(data), 0o644, 1704067200
                archive.addfile(info, io.BytesIO(data))
        return buffer.getvalue()
