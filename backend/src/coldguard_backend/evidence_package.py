"""Exclusive, staged file packages verified against an independently supplied anchor."""

import hashlib
import json
import re
import tempfile
from pathlib import Path, PurePosixPath

from coldguard_backend.experiment_evidence import encode_evidence


def digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def package_path(root: Path, name: str) -> Path:
    parts = PurePosixPath(name).parts if isinstance(name, str) else ()
    if not parts or name != "/".join(parts) or any(part in {".", ".."} or "\\" in part or ":" in part for part in parts):
        raise ValueError("package artifact requires a normalized relative path")
    path = root.joinpath(*parts)
    if root.resolve() not in path.resolve().parents or any(
        item.is_symlink() or (hasattr(item, "is_junction") and item.is_junction())
        for item in (path, *path.parents) if item != root and root in item.parents
    ):
        raise ValueError("package artifact escapes or aliases its directory")
    return path


def publish_package(destination: Path, files: dict[str, bytes], *, format: str, metadata: dict) -> dict:
    if not files or len(files) > 5000 or {"format", "files"} & metadata.keys():
        raise ValueError("invalid evidence package contents or metadata")
    names = [name.casefold() for name in files]
    if len(set(names)) != len(names) or "manifest.json" in names:
        raise ValueError("package artifact names collide with each other or the manifest")
    if destination.exists() or destination.is_symlink():
        raise FileExistsError("evidence destination already exists; never overwrite")
    for name in files:
        package_path(destination, name)
    destination.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".evidence-staging-", dir=destination.parent))
    manifest = {"format": format, **metadata, "files": {name: digest(content) for name, content in sorted(files.items())}}
    manifest_bytes = encode_evidence(manifest)
    for name, content in {**files, "manifest.json": manifest_bytes}.items():
        path = package_path(stage, name)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as output:
            output.write(content)
    if destination.exists() or destination.is_symlink():
        raise FileExistsError("evidence destination appeared during publication")
    stage.rename(destination)
    return {"manifest_sha256": digest(manifest_bytes), "manifest": manifest}


def verify_package(directory: Path, *, expected_manifest_sha256: str, format: str) -> dict:
    if not isinstance(expected_manifest_sha256, str) or re.fullmatch(r"[0-9a-f]{64}", expected_manifest_sha256) is None:
        raise ValueError("a trusted manifest SHA-256 is required")
    content = package_path(directory, "manifest.json").read_bytes()
    if digest(content) != expected_manifest_sha256:
        raise ValueError("manifest differs from its trusted anchor")
    manifest = json.loads(content)
    files = manifest.get("files")
    if manifest.get("format") != format or not isinstance(files, dict) or not files or len(files) > 5000:
        raise ValueError("unsupported evidence package format or files")
    actual = {path.relative_to(directory).as_posix() for path in directory.rglob("*") if path.is_file()}
    if actual != {"manifest.json", *files}:
        raise ValueError("evidence package has missing or unexpected artifacts")
    for name, checksum in files.items():
        if not isinstance(checksum, str) or re.fullmatch(r"[0-9a-f]{64}", checksum) is None or digest(package_path(directory, name).read_bytes()) != checksum:
            raise ValueError("evidence artifact checksum differs: " + str(name))
    return manifest
