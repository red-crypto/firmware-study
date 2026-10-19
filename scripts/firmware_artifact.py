#!/usr/bin/env python3
"""Create and verify a portable STM32 firmware bundle (Python 3.11+, stdlib only).

SHA256 checks integrity, not publisher identity. Expected commit and image hash must
come from the reviewed GitHub Actions run or another trusted source, not this bundle.
The manifest records the builder's command declaration; it is not signed provenance.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import struct
import subprocess
import sys
import tomllib
from typing import Any


TARGET = "thumbv7em-none-eabihf"
BOARD = "STM32F411RETx"
BINARY = "f411_blinky"
IMAGE_NAME = BINARY + ".elf"
SHA_RE = re.compile(r"[0-9a-f]{64}\Z")
COMMIT_RE = re.compile(r"[0-9a-f]{40}\Z")
BUNDLE_FILES = (IMAGE_NAME, "SHA256SUMS", "manifest.json")


class VerifyError(ValueError):
    """A bundle or its declared inputs failed validation."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise VerifyError(message)


def _digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def _command(args: list[str], cwd: Path) -> str:
    result = subprocess.run(args, cwd=cwd, check=True, capture_output=True, text=True)
    return result.stdout.strip()


def _regular_file(directory: Path, name: str) -> Path:
    path = directory / name
    _require(not path.is_symlink(), f"Symlink is not allowed: {name}")
    _require(path.is_file(), f"Missing regular file: {name}")
    _require(path.resolve().parent == directory.resolve(), f"File escapes bundle: {name}")
    return path


def _policy_version(workspace: Path) -> str:
    path = workspace / "f411_blinky" / "rust-toolchain.toml"
    with path.open("rb") as stream:
        policy = tomllib.load(stream)["toolchain"]
    version = policy.get("channel")
    _require(isinstance(version, str) and re.fullmatch(r"\d+\.\d+\.\d+", version) is not None,
             "Rust toolchain must pin an exact stable version")
    _require(TARGET in policy.get("targets", []), "Rust policy must include the firmware target")
    return version


def _reject_input_redirects(root: Path, path: Path) -> None:
    """Check every ancestor, including Windows junctions that are not symlinks."""
    current = root
    for part in path.relative_to(root).parts:
        current /= part
        if current.exists() or current.is_symlink():
            attributes = getattr(current.lstat(), "st_file_attributes", 0)
            _require(not current.is_symlink() and not attributes & 0x400,
                     "Build inputs cannot use symlinks or Windows reparse points")
    _require(path.resolve().is_relative_to(root), "Build inputs cannot leave the repository")


def source_snapshot(workspace: str | Path) -> dict[str, Any]:
    """Hash explicit build inputs, including untracked sources, without recording contents."""
    root = Path(workspace).resolve()
    firmware = root / "f411_blinky"
    _require(_command(["git", "rev-parse", "--show-toplevel"], root).replace("\\", "/").lower()
             == root.as_posix().lower(), "Workspace must be the Git repository root")
    commit = _command(["git", "rev-parse", "HEAD"], root)
    _require(COMMIT_RE.fullmatch(commit) is not None, "Expected a full Git SHA-1 revision")
    dirty = bool(_command(["git", "status", "--porcelain", "--untracked-files=normal"], root))
    paths: set[Path] = set()
    for name in ("Cargo.toml", "Cargo.lock", "build.rs", "memory.x", "rust-toolchain.toml"):
        path = firmware / name
        if path.exists() or path.is_symlink():
            paths.add(path)
    for name in ("config", "config.toml"):
        path = firmware / ".cargo" / name
        if path.exists() or path.is_symlink():
            paths.add(path)
    for directory, suffixes in ((firmware / "src", None),
                                (root / ".github" / "workflows", (".yml", ".yaml"))):
        _reject_input_redirects(root, directory)
        if directory.exists():
            # Inspect directory entries before os.walk can descend. rglob skips
            # nested directory symlinks, which would hide an actual build input.
            for current, directories, files in os.walk(directory, topdown=True, followlinks=False):
                for name in directories + files:
                    path = Path(current) / name
                    _reject_input_redirects(root, path)
                    if name in files and (suffixes is None or path.suffix in suffixes):
                        paths.add(path)
    for name in ("Build-HilFirmware.ps1", "firmware_artifact.py"):
        path = root / "scripts" / name
        if path.exists() or path.is_symlink():
            paths.add(path)
    inputs = []
    for path in sorted(paths, key=lambda item: item.relative_to(root).as_posix()):
        _reject_input_redirects(root, path)
        relative = path.relative_to(root).as_posix()
        _require(not any(ord(char) < 32 for char in relative), "Invalid build input path")
        inputs.append({"path": relative, "sha256": _digest(path)})
    _require(bool(inputs), "No build inputs found")
    return {"commit": commit, "dirty": dirty,
            "fingerprint": hashlib.sha256(_canonical(inputs)).hexdigest(), "inputs": inputs}


def _validate_elf(path: Path) -> None:
    """Require a little-endian 32-bit ARM executable with a bounded load segment."""
    size = path.stat().st_size
    _require(52 <= size <= 64 * 1024 * 1024, "Unexpected firmware ELF size")
    with path.open("rb") as stream:
        header = stream.read(52)
        _require(header[:7] == b"\x7fELF\x01\x01\x01", "Expected a 32-bit little-endian ELF")
        fields = struct.unpack("<16sHHIIIIIHHHHHH", header)
        _, kind, machine, version, _, phoff, _, _, ehsize, phsize, phnum, _, _, _ = fields
        _require(kind == 2 and machine == 40 and version == 1 and ehsize == 52,
                 "Expected an ARM executable ELF")
        _require(phnum > 0 and phsize == 32 and phoff >= 52 and phoff + phnum * phsize <= size,
                 "Invalid ELF program headers")
        found_load = False
        for index in range(phnum):
            stream.seek(phoff + index * phsize)
            kind, offset, _, _, file_size, memory_size, _, _ = struct.unpack("<IIIIIIII", stream.read(32))
            if kind == 1:
                _require(file_size <= memory_size and offset + file_size <= size,
                         "Invalid ELF load segment")
                found_load = found_load or file_size > 0
        _require(found_load, "ELF has no nonempty load segment")


def _ci_context(source_commit: str) -> dict[str, str] | None:
    if os.environ.get("GITHUB_ACTIONS") != "true":
        return None
    names = {"repository": "GITHUB_REPOSITORY", "run_id": "GITHUB_RUN_ID",
             "run_attempt": "GITHUB_RUN_ATTEMPT", "sha": "GITHUB_SHA"}
    context = {key: os.environ.get(name, "") for key, name in names.items()}
    _require(all(context.values()), "Incomplete GitHub Actions context")
    _require(context["sha"] == source_commit, "GitHub Actions SHA differs from checkout HEAD")
    server = os.environ.get("GITHUB_SERVER_URL", "https://github.com").rstrip("/")
    _require(re.fullmatch(r"https://[A-Za-z0-9.-]+", server) is not None, "Invalid GitHub server URL")
    _require(re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", context["repository"]) is not None,
             "Invalid GitHub repository")
    _require(context["run_id"].isdigit() and context["run_attempt"].isdigit(), "Invalid GitHub run ID")
    context["url"] = f"{server}/{context['repository']}/actions/runs/{context['run_id']}"
    return context


def create_bundle(workspace: str | Path, image: str | Path, output: str | Path,
                  profile: str, expected_source_fingerprint: str, expected_commit: str,
                  offline: bool = False) -> dict[str, Any]:
    root = Path(workspace).resolve()
    image_path = Path(image).resolve()
    output_path = Path(output).resolve()
    _require(profile in ("debug", "release"), "Invalid build profile")
    _require(SHA_RE.fullmatch(expected_source_fingerprint) is not None, "Invalid expected source fingerprint")
    _require(COMMIT_RE.fullmatch(expected_commit) is not None, "Invalid expected commit")
    source = source_snapshot(root)
    _require(source["commit"] == expected_commit, "Source commit changed during the build")
    _require(source["fingerprint"] == expected_source_fingerprint, "Build inputs changed during the build")
    version = _policy_version(root)
    rustc = _command(["rustc", "-Vv"], root / "f411_blinky")
    cargo = _command(["cargo", "-V"], root / "f411_blinky")
    _require(rustc.startswith(f"rustc {version} (") and cargo.startswith(f"cargo {version} ("),
             "Active Rust/Cargo version differs from rust-toolchain.toml")
    _validate_elf(image_path)
    image_hash = _digest(image_path)
    command = ["cargo", "build", "--locked", "--target", TARGET]
    if profile == "release":
        command.append("--release")
    if offline:
        command.append("--offline")
    manifest: dict[str, Any] = {
        "schema_version": 1, "target": TARGET, "board": BOARD, "binary": BINARY,
        "profile": profile, "source": source,
        "toolchain": {"version": version, "rustc": rustc, "cargo": cargo},
        "image": {"file": IMAGE_NAME, "sha256": image_hash, "size": image_path.stat().st_size},
        "checks": {"build_command": command, "assurance": "builder-declared", "source_snapshot_matched": True},
    }
    ci = _ci_context(source["commit"])
    if ci is not None:
        _require(not source["dirty"], "CI bundle requires a clean Git checkout")
        manifest["ci"] = ci
    output_path.mkdir(parents=True, exist_ok=True)
    for name in BUNDLE_FILES:
        destination = output_path / name
        _require(not destination.is_symlink() and (not destination.exists() or destination.is_file()),
                 f"Refusing unsafe output file: {name}")
    destination_image = output_path / IMAGE_NAME
    _require(image_path != destination_image, "Input image must be outside its output bundle")
    shutil.copyfile(image_path, destination_image)
    _require(_digest(destination_image) == image_hash, "Image changed while copying")
    (output_path / "SHA256SUMS").write_text(f"{image_hash}  {IMAGE_NAME}\n", encoding="utf-8", newline="\n")
    (output_path / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n")
    return manifest


def verify_bundle(bundle: str | Path, expected_commit: str, expected_sha256: str,
                  allow_dirty: bool = False) -> dict[str, Any]:
    """Verify a bundle against externally trusted revision and image hash before HIL."""
    directory = Path(bundle).resolve()
    _require(COMMIT_RE.fullmatch(expected_commit) is not None, "Expected commit must be a full lowercase SHA")
    _require(SHA_RE.fullmatch(expected_sha256) is not None, "Expected SHA256 must be 64 lowercase hex digits")
    files = {name: _regular_file(directory, name) for name in BUNDLE_FILES}
    _require(files["manifest.json"].stat().st_size <= 1024 * 1024, "Manifest is too large")
    try:
        manifest_bytes = files["manifest.json"].read_bytes()
        manifest = json.loads(manifest_bytes.decode("utf-8"))
        _require(isinstance(manifest, dict) and type(manifest["schema_version"]) is int
                 and manifest["schema_version"] == 1, "Unsupported manifest schema")
        _require(manifest["target"] == TARGET and manifest["board"] == BOARD
                 and manifest["binary"] == BINARY, "Unexpected firmware target")
        _require(manifest["profile"] in ("debug", "release"), "Invalid build profile")
        image_info = manifest["image"]
        _require(image_info["file"] == IMAGE_NAME, "Image filename must be f411_blinky.elf")
        _require(type(image_info["size"]) is int and image_info["size"] == files[IMAGE_NAME].stat().st_size,
                 "Image size mismatch")
        _require(image_info["sha256"] == expected_sha256 and _digest(files[IMAGE_NAME]) == expected_sha256,
                 "Image SHA256 mismatch")
        _require(files["SHA256SUMS"].stat().st_size < 256
                 and files["SHA256SUMS"].read_text(encoding="utf-8") == f"{expected_sha256}  {IMAGE_NAME}\n",
                 "SHA256SUMS mismatch")
        source = manifest["source"]
        _require(source["commit"] == expected_commit, "Source revision mismatch")
        _require(type(source["dirty"]) is bool, "Invalid source dirty state")
        _require(not source["dirty"] or allow_dirty, "Dirty source bundle requires explicit --allow-dirty")
        inputs = source["inputs"]
        _require(isinstance(inputs, list) and bool(inputs), "Missing source input hashes")
        paths = []
        for item in inputs:
            _require(isinstance(item, dict) and set(item) == {"path", "sha256"}, "Invalid source input")
            name = item["path"]
            _require(isinstance(name, str) and bool(name) and "\\" not in name and ":" not in name
                     and not PurePosixPath(name).is_absolute() and ".." not in PurePosixPath(name).parts
                     and not any(ord(char) < 32 for char in name), "Invalid source input path")
            _require(isinstance(item["sha256"], str) and SHA_RE.fullmatch(item["sha256"]) is not None,
                     "Invalid source input hash")
            paths.append(name)
        _require(paths == sorted(set(paths)), "Source inputs must be sorted and unique")
        _require(source["fingerprint"] == hashlib.sha256(_canonical(inputs)).hexdigest(), "Source fingerprint mismatch")
        toolchain = manifest["toolchain"]
        policy = _policy_version(Path(__file__).resolve().parents[1])
        _require(toolchain["version"] == policy, "Bundle Rust version differs from local policy")
        _require(isinstance(toolchain["rustc"], str) and toolchain["rustc"].startswith(f"rustc {policy} (")
                 and isinstance(toolchain["cargo"], str) and toolchain["cargo"].startswith(f"cargo {policy} ("),
                 "Invalid toolchain metadata")
        checks = manifest["checks"]
        command = checks["build_command"]
        expected_command = ["cargo", "build", "--locked", "--target", TARGET] + (["--release"] if manifest["profile"] == "release" else [])
        _require(command in (expected_command, expected_command + ["--offline"])
                 and checks["assurance"] == "builder-declared" and checks["source_snapshot_matched"] is True,
                 "Invalid build declaration")
        if "ci" in manifest:
            ci = manifest["ci"]
            _require(isinstance(ci, dict) and set(ci) == {"repository", "run_id", "run_attempt", "sha", "url"}
                     and all(isinstance(value, str) and bool(value) for value in ci.values()), "Invalid CI metadata")
            _require(ci["sha"] == source["commit"] and not source["dirty"], "CI source metadata mismatch")
            _require(re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", ci["repository"]) is not None
                     and ci["run_id"].isdigit() and ci["run_attempt"].isdigit(), "Invalid CI identity")
            _require(re.fullmatch(r"https://[A-Za-z0-9.-]+/" + re.escape(ci["repository"])
                                 + r"/actions/runs/" + re.escape(ci["run_id"]), ci["url"]) is not None,
                     "Invalid CI run URL")
    except (KeyError, TypeError, json.JSONDecodeError, UnicodeError) as error:
        raise VerifyError("Malformed manifest") from error
    _validate_elf(files[IMAGE_NAME])
    return {"verified": True, "image": str(files[IMAGE_NAME]), "sha256": expected_sha256,
            "source_commit": expected_commit, "profile": manifest["profile"], "source_dirty": source["dirty"],
            "source_fingerprint": source["fingerprint"],
            "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
            "toolchain_version": policy, "ci": manifest.get("ci")}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    snapshot = commands.add_parser("snapshot", help="Capture source state before building")
    snapshot.add_argument("--workspace", required=True)
    create = commands.add_parser("create", help="Package the successful builder's output")
    create.add_argument("--workspace", required=True)
    create.add_argument("--image", required=True)
    create.add_argument("--output", required=True)
    create.add_argument("--profile", choices=("debug", "release"), required=True)
    create.add_argument("--expected-source-fingerprint", required=True)
    create.add_argument("--expected-commit", required=True)
    create.add_argument("--offline", action="store_true")
    verify = commands.add_parser("verify", help="Verify trusted revision/hash before local HIL")
    verify.add_argument("--bundle", required=True)
    verify.add_argument("--expected-commit", required=True)
    verify.add_argument("--expected-sha256", required=True)
    verify.add_argument("--allow-dirty", action="store_true")
    args = vars(parser.parse_args())
    command = args.pop("command")
    try:
        result = {"snapshot": source_snapshot, "create": create_bundle, "verify": verify_bundle}[command](**args)
        print(json.dumps(result, indent=2))
        return 0
    except (VerifyError, OSError, subprocess.CalledProcessError, tomllib.TOMLDecodeError) as error:
        print(f"Firmware artifact error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
