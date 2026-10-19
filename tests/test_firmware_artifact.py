"""REQ-PIPE-001..003: reject wrong/corrupt firmware before any hardware access."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import struct
import subprocess
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "firmware_artifact.py"
SPEC = importlib.util.spec_from_file_location("firmware_artifact", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
artifact = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(artifact)


def arm_elf(machine: int = 40) -> bytes:
    ident = b"\x7fELF\x01\x01\x01" + b"\0" * 9
    header = struct.pack("<16sHHIIIIIHHHHHH", ident, 2, machine, 1, 0x08000001,
                         52, 0, 0x05000400, 52, 32, 1, 0, 0, 0)
    segment = struct.pack("<IIIIIIII", 1, 84, 0x08000000, 0x08000000, 4, 4, 5, 4)
    return header + segment + b"\x00\xbf\x00\xbf"


class FirmwareArtifactTests(unittest.TestCase):
    def setUp(self) -> None:
        temp_root = MODULE_PATH.parents[1] / "artifacts" / "test-temp"
        temp_root.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix="firmware-artifact-test-", dir=temp_root)
        def cleanup() -> None:
            # Git/Windows indexers can retain a short-lived directory handle.
            for attempt in range(6):
                try:
                    self.temp.cleanup()
                    return
                except PermissionError:
                    if attempt == 5:
                        raise
                    time.sleep(0.1 * 2 ** attempt)

        self.addCleanup(cleanup)
        base = Path(self.temp.name)
        self.root = base / "repo"
        self.root.mkdir()
        self.output = base / "bundle"
        self.image = base / "built.elf"
        self.image.write_bytes(arm_elf())
        self.firmware = self.root / "f411_blinky"
        (self.firmware / "src").mkdir(parents=True)
        (self.firmware / ".cargo").mkdir()
        (self.firmware / "src" / "main.rs").write_text("#![no_std]\n", encoding="utf-8")
        for name, content in {
            "Cargo.toml": '[package]\nname="f411_blinky"\nversion="0.1.0"\n',
            "Cargo.lock": "version = 4\n",
            "build.rs": "fn main() {}\n",
            "memory.x": "MEMORY {}\n",
            "rust-toolchain.toml": '[toolchain]\nchannel="1.98.1"\ntargets=["thumbv7em-none-eabihf"]\n',
        }.items():
            (self.firmware / name).write_text(content, encoding="utf-8")
        (self.firmware / ".cargo" / "config.toml").write_text('[build]\ntarget="thumbv7em-none-eabihf"\n', encoding="utf-8")
        subprocess.run(["git", "init", "--quiet", str(self.root)], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(self.root), "add", "."], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(self.root), "-c", "user.name=Artifact Test",
                        "-c", "user.email=artifact@example.invalid", "commit", "--quiet", "-m", "fixture"],
                       check=True, capture_output=True)
        original_command = artifact._command

        def fake_versions(args: list[str], cwd: Path) -> str:
            if args == ["rustc", "-Vv"]:
                return "rustc 1.98.1 (fixture 2026-09-25)\nbinary: rustc\nrelease: 1.98.1"
            if args == ["cargo", "-V"]:
                return "cargo 1.98.1 (fixture 2026-09-25)"
            return original_command(args, cwd)

        version_patch = patch.object(artifact, "_command", side_effect=fake_versions)
        version_patch.start()
        self.addCleanup(version_patch.stop)
        environment_patch = patch.dict(os.environ, {"GITHUB_ACTIONS": "false"})
        environment_patch.start()
        self.addCleanup(environment_patch.stop)
        self.snapshot = artifact.source_snapshot(self.root)
        self.commit = self.snapshot["commit"]
        self.sha = hashlib.sha256(self.image.read_bytes()).hexdigest()

    def create(self, snapshot: dict | None = None) -> dict:
        state = snapshot or self.snapshot
        return artifact.create_bundle(self.root, self.image, self.output, "debug",
                                      state["fingerprint"], state["commit"])

    def verify(self, **kwargs) -> dict:
        return artifact.verify_bundle(self.output, kwargs.pop("expected_commit", self.commit),
                                      kwargs.pop("expected_sha256", self.sha), **kwargs)

    def mutate_manifest(self, change) -> None:
        path = self.output / "manifest.json"
        manifest = json.loads(path.read_text(encoding="utf-8"))
        change(manifest)
        path.write_text(json.dumps(manifest), encoding="utf-8")

    def test_clean_bundle_preserves_exact_image_and_has_no_machine_paths(self) -> None:
        manifest = self.create()
        result = self.verify()
        self.assertTrue(result["verified"])
        self.assertEqual((self.output / artifact.IMAGE_NAME).read_bytes(), self.image.read_bytes())
        self.assertEqual(result["sha256"], self.sha)
        self.assertEqual(result["source_commit"], self.commit)
        self.assertEqual(result["source_fingerprint"], self.snapshot["fingerprint"])
        self.assertEqual(result["manifest_sha256"], hashlib.sha256((self.output / "manifest.json").read_bytes()).hexdigest())
        self.assertIsNone(result["ci"])
        self.assertFalse(manifest["source"]["dirty"])
        self.assertEqual(set(path.name for path in self.output.iterdir()), set(artifact.BUNDLE_FILES))
        self.assertNotIn(str(self.root), json.dumps(manifest))
        self.assertEqual(manifest["checks"]["assurance"], "builder-declared")

    def test_rejects_image_corruption(self) -> None:
        self.create()
        with (self.output / artifact.IMAGE_NAME).open("ab") as stream:
            stream.write(b"corruption")
        with self.assertRaisesRegex(artifact.VerifyError, "size mismatch"):
            self.verify()

    def test_rejects_wrong_expected_hash_or_revision(self) -> None:
        self.create()
        for expected in ({"expected_commit": "f" * 40}, {"expected_sha256": "f" * 64}):
            with self.subTest(expected=expected), self.assertRaises(artifact.VerifyError):
                self.verify(**expected)

    def test_dirty_bundle_requires_explicit_local_override(self) -> None:
        (self.root / "notes.md").write_text("Uncommitted work\n", encoding="utf-8")
        self.create()
        with self.assertRaisesRegex(artifact.VerifyError, "allow-dirty"):
            self.verify()
        self.assertTrue(self.verify(allow_dirty=True)["source_dirty"])

    def test_changed_build_source_rejected_after_snapshot(self) -> None:
        (self.firmware / "src" / "new.rs").write_text("const NEW: u32 = 1;\n", encoding="utf-8")
        self.assertNotEqual(self.snapshot["fingerprint"], artifact.source_snapshot(self.root)["fingerprint"])
        with self.assertRaisesRegex(artifact.VerifyError, "changed during"):
            self.create()
        self.assertFalse(self.output.exists())

    def test_unrelated_docs_do_not_change_build_fingerprint(self) -> None:
        (self.root / "README.md").write_text("Documentation\n", encoding="utf-8")
        state = artifact.source_snapshot(self.root)
        self.assertEqual(state["fingerprint"], self.snapshot["fingerprint"])
        self.assertTrue(state["dirty"])

    def test_source_snapshot_refuses_nested_directory_symlinks(self) -> None:
        external = self.root.parent / "external-source"
        external.mkdir()
        (external / "hidden.rs").write_text("const HIDDEN: u32 = 1;\n", encoding="utf-8")
        redirect = self.firmware / "src" / "external"
        try:
            redirect.symlink_to(external, target_is_directory=True)
        except OSError:
            self.skipTest("Creating directory symlinks is not permitted on this Windows host")
        with self.assertRaisesRegex(artifact.VerifyError, "symlinks"):
            artifact.source_snapshot(self.root)

    def test_source_snapshot_refuses_windows_junction_before_reading_it(self) -> None:
        redirect = self.firmware / "src" / "junction"
        redirect.mkdir()
        hidden = redirect / "hidden.rs"
        hidden.write_text("const HIDDEN: u32 = 1;\n", encoding="utf-8")
        original_lstat = Path.lstat
        original_digest = artifact._digest

        def junction_attributes(path, *args, **kwargs):
            if path == redirect:
                # Junctions expose this Windows attribute without is_symlink().
                return SimpleNamespace(st_file_attributes=0x400,
                                       st_mode=original_lstat(path, *args, **kwargs).st_mode)
            return original_lstat(path, *args, **kwargs)

        with patch.object(Path, "lstat", junction_attributes), \
                patch.object(artifact, "_digest", wraps=original_digest) as digest:
            with self.assertRaisesRegex(artifact.VerifyError, "reparse points"):
                artifact.source_snapshot(self.root)
        self.assertNotIn(hidden, [call.args[0] for call in digest.call_args_list])

    def test_wrong_architecture_is_not_accepted_as_an_elf(self) -> None:
        for data in (b"arbitrary payload", arm_elf(machine=3), arm_elf()[:60]):
            with self.subTest(length=len(data)):
                self.image.write_bytes(data)
                with self.assertRaises(artifact.VerifyError):
                    self.create()

    def test_rejects_manifest_path_traversal_and_source_hash_tampering(self) -> None:
        self.create()
        self.mutate_manifest(lambda value: value["image"].update(file="../built.elf"))
        with self.assertRaisesRegex(artifact.VerifyError, "filename"):
            self.verify()
        self.create()
        self.mutate_manifest(lambda value: value["source"]["inputs"][0].update(sha256="0" * 64))
        with self.assertRaisesRegex(artifact.VerifyError, "fingerprint"):
            self.verify()

    def test_rejects_checksum_file_mismatch(self) -> None:
        self.create()
        (self.output / "SHA256SUMS").write_text(f"{'0' * 64}  f411_blinky.elf\n", encoding="utf-8")
        with self.assertRaisesRegex(artifact.VerifyError, "SHA256SUMS mismatch"):
            self.verify()

    def test_rejects_unpinned_or_wrong_toolchain_metadata(self) -> None:
        self.create()
        self.mutate_manifest(lambda value: value["toolchain"].update(version="stable"))
        with self.assertRaisesRegex(artifact.VerifyError, "Rust version"):
            self.verify()

    def test_rejects_missing_locked_build_declaration(self) -> None:
        self.create()
        self.mutate_manifest(lambda value: value["checks"].update(build_command=["cargo", "build"]))
        with self.assertRaisesRegex(artifact.VerifyError, "build declaration"):
            self.verify()

    def test_ci_bundle_records_only_selected_context(self) -> None:
        context = {"GITHUB_ACTIONS": "true", "GITHUB_REPOSITORY": "example/firmware",
                   "GITHUB_RUN_ID": "42", "GITHUB_RUN_ATTEMPT": "1", "GITHUB_SHA": self.commit,
                   "GITHUB_SERVER_URL": "https://github.com", "SECRET_TEST_TOKEN": "must-not-appear"}
        with patch.dict(os.environ, context):
            manifest = self.create()
        self.assertEqual(manifest["ci"]["url"], "https://github.com/example/firmware/actions/runs/42")
        self.assertNotIn("must-not-appear", json.dumps(manifest))
        self.verify()

    def test_ci_refuses_dirty_source(self) -> None:
        (self.root / "notes.md").write_text("dirty\n", encoding="utf-8")
        context = {"GITHUB_ACTIONS": "true", "GITHUB_REPOSITORY": "example/firmware",
                   "GITHUB_RUN_ID": "42", "GITHUB_RUN_ATTEMPT": "1", "GITHUB_SHA": self.commit}
        with patch.dict(os.environ, context), self.assertRaisesRegex(artifact.VerifyError, "clean Git"):
            self.create()

    def test_malformed_manifest_is_a_controlled_validation_failure(self) -> None:
        self.create()
        (self.output / "manifest.json").write_text('{"schema_version":true}', encoding="utf-8")
        with self.assertRaises(artifact.VerifyError):
            self.verify()

    def test_rejects_symlink_instead_of_artifact_when_supported(self) -> None:
        self.create()
        destination = self.output / artifact.IMAGE_NAME
        destination.unlink()
        try:
            destination.symlink_to(self.image)
        except OSError:
            self.skipTest("Creating symlinks is not permitted on this Windows host")
        with self.assertRaisesRegex(artifact.VerifyError, "Symlink"):
            self.verify()


if __name__ == "__main__":
    unittest.main()
