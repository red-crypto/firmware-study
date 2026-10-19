"""Board-free checks of the artifact-to-HIL trust boundary and MCP transport."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import hil_artifact


COMMIT = "a" * 40


class FakeMcp:
    def __init__(self, workspace: Path, digest: str, *, verdict: bool = True,
                 flashed_digest: str | None = None, plan_digest: str | None = None,
                 result_overrides: dict | None = None, omit_keys: tuple = (),
                 flash_overrides: dict | None = None):
        self.workspace = workspace
        self.digest = digest
        self.verdict = verdict
        self.flashed_digest = flashed_digest
        self.plan_digest = plan_digest
        self.result_overrides = result_overrides or {}
        self.omit_keys = omit_keys
        self.flash_overrides = flash_overrides or {}
        self.calls: list[tuple[str, dict]] = []
        self.closed = False
        self.initialized = False

    def initialize(self):
        self.initialized = True

    def call(self, name, arguments):
        self.calls.append((name, arguments))
        plan = self.workspace / arguments["test_config_path"]
        result = {
            "ok": self.verdict,
            "run": "run-0123456789abcdef",
            "canonical_report_path": "operator-state/runs/run-0123456789abcdef.json",
            "test_config_sha256": self.plan_digest or hil_artifact.sha256(plan),
            "steps": [{"action": "flash", "result": {
                "ok": True, "artifact": {"sha256": self.flashed_digest or self.digest},
                "verify": True, "success_confirmed": True,
            }}],
            "cleanup_ok": True,
        }
        if not self.verdict:
            result["error_type"] = "permission_denied"
        result.update(self.result_overrides)
        for key in self.omit_keys:
            result.pop(key, None)
        result["steps"][0]["result"].update(self.flash_overrides)
        return {"structuredContent": result, "content": []}

    def close(self):
        self.closed = True


class ArtifactHilTests(unittest.TestCase):
    def setUp(self):
        temporary_root = Path(__file__).resolve().parents[1] / "artifacts" / "test-tmp"
        temporary_root.mkdir(parents=True, exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(dir=temporary_root)
        self.addCleanup(self.temporary.cleanup)
        self.workspace = Path(self.temporary.name).resolve()
        self.bundle = self.workspace / "download"
        self.bundle.mkdir()
        self.image = self.bundle / "f411_blinky.elf"
        self.image.write_bytes(b"\x7fELFexact downloaded bytes")
        self.digest = hashlib.sha256(self.image.read_bytes()).hexdigest()
        self.verified = {
            "verified": True, "image": str(self.image), "sha256": self.digest,
            "source_commit": COMMIT, "source_dirty": False, "profile": "debug",
        }

    def run_bundle(self, client):
        with mock.patch.object(hil_artifact, "verify_bundle", return_value=self.verified) as verify:
            result = hil_artifact.run_verified_bundle(
                self.workspace, self.bundle, COMMIT, self.digest,
                client_factory=lambda *args: client,
            )
            verify.assert_called_once_with(self.bundle, COMMIT, self.digest, allow_dirty=False)
        return result

    def test_exact_image_plan_and_report_are_connected(self):
        # A bundle-provided plan must never become executable HIL input.
        (self.bundle / "hello-world.json").write_text('{"steps":[{"action":"mass_erase"}]}')
        client = FakeMcp(self.workspace, self.digest)
        evidence_path = self.run_bundle(client)
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
        plan = json.loads((self.workspace / evidence["plan"]).read_text(encoding="utf-8"))
        self.assertEqual("passed", evidence["status"])
        self.assertEqual(self.digest, evidence["observed_flash_sha256"])
        self.assertEqual(COMMIT, evidence["artifact"]["source_commit"])
        self.assertEqual("run-0123456789abcdef", evidence["run"])
        self.assertEqual(self.digest, hil_artifact.sha256(self.workspace / evidence["snapshot"]))
        self.assertEqual(["flash", "uart_open", "reset", "uart_read"], [step["action"] for step in plan["steps"]])
        self.assertEqual({"equals": "Hello World"}, plan["steps"][-1]["comparator"])
        self.assertEqual(5, plan["steps"][-1]["timeout_s"])
        self.assertEqual("test_reactor_run", client.calls[0][0])
        self.assertEqual(1, len(client.calls))
        self.assertTrue(client.initialized)
        self.assertTrue(client.closed)

    def test_invalid_bundle_stops_before_server_or_snapshot(self):
        factory = mock.Mock()
        with mock.patch.object(hil_artifact, "verify_bundle", side_effect=ValueError("SHA mismatch")):
            with self.assertRaisesRegex(ValueError, "SHA mismatch"):
                hil_artifact.run_verified_bundle(
                    self.workspace, self.bundle, COMMIT, self.digest, client_factory=factory)
        factory.assert_not_called()
        self.assertFalse((self.workspace / ".agentic-hil").exists())

    def test_tampered_existing_snapshot_stops_before_server(self):
        destination = self.workspace / ".agentic-hil/artifacts/ci" / self.digest / "f411_blinky.elf"
        destination.parent.mkdir(parents=True)
        destination.write_bytes(b"tampered")
        factory = mock.Mock()
        with mock.patch.object(hil_artifact, "verify_bundle", return_value=self.verified):
            with self.assertRaisesRegex(hil_artifact.HilError, "snapshot SHA256"):
                hil_artifact.run_verified_bundle(
                    self.workspace, self.bundle, COMMIT, self.digest, client_factory=factory)
        factory.assert_not_called()

    def test_different_flashed_hash_is_a_failure_with_raw_evidence(self):
        client = FakeMcp(self.workspace, self.digest, flashed_digest="b" * 64)
        with self.assertRaisesRegex(hil_artifact.HilError, "different SHA256"):
            self.run_bundle(client)
        evidence = json.loads(next((self.workspace / "artifacts/hil").glob("*/evidence.json")).read_text())
        self.assertEqual("failed", evidence["status"])
        self.assertEqual("b" * 64, evidence["observed_flash_sha256"])
        self.assertEqual(1, len(evidence["calls"]))
        self.assertTrue(client.closed)

    def test_different_plan_hash_is_a_failure(self):
        client = FakeMcp(self.workspace, self.digest, plan_digest="c" * 64)
        with self.assertRaisesRegex(hil_artifact.HilError, "different test plan"):
            self.run_bundle(client)
        self.assertTrue(client.closed)

    def test_permission_denial_is_recorded_without_retry(self):
        client = FakeMcp(self.workspace, self.digest, verdict=False)
        with self.assertRaisesRegex(hil_artifact.HilError, "permission_denied"):
            self.run_bundle(client)
        evidence = json.loads(next((self.workspace / "artifacts/hil").glob("*/evidence.json")).read_text())
        self.assertEqual("failed", evidence["status"])
        self.assertEqual(1, len(client.calls))
        self.assertEqual("permission_denied", evidence["calls"][0]["result"]["structuredContent"]["error_type"])

    def test_compact_documented_success_defaults_are_accepted(self):
        client = FakeMcp(self.workspace, self.digest, omit_keys=("cleanup_ok", "audit_ok"))
        evidence = json.loads(self.run_bundle(client).read_text())
        self.assertEqual("passed", evidence["status"])

    def test_failed_cleanup_audit_and_quarantine_are_refused(self):
        for field, value in (
            ("cleanup_ok", False), ("audit_ok", False), ("cleanup_required", True),
            ("quarantined", True), ("cleanup_ok", None), ("audit_ok", "true"),
        ):
            with self.subTest(field=field, value=value):
                client = FakeMcp(self.workspace, self.digest, result_overrides={field: value})
                with self.assertRaises(hil_artifact.HilError):
                    self.run_bundle(client)
                self.assertEqual(1, len(client.calls))
                self.assertTrue(client.closed)

    def test_missing_canonical_run_identity_is_refused(self):
        for field in ("run", "canonical_report_path"):
            with self.subTest(field=field):
                client = FakeMcp(self.workspace, self.digest, omit_keys=(field,))
                with self.assertRaisesRegex(hil_artifact.HilError, "canonical run identity"):
                    self.run_bundle(client)

    def test_flash_must_confirm_success_and_read_back_verification(self):
        for field in ("ok", "verify", "success_confirmed"):
            with self.subTest(field=field):
                client = FakeMcp(self.workspace, self.digest, flash_overrides={field: False})
                with self.assertRaisesRegex(hil_artifact.HilError, "read-back verification"):
                    self.run_bundle(client)

    def test_client_shutdown_failure_still_persists_evidence(self):
        client = FakeMcp(self.workspace, self.digest)
        client.close = mock.Mock(side_effect=OSError("fake close failed"))
        with self.assertRaisesRegex(hil_artifact.HilError, "client shutdown failed"):
            self.run_bundle(client)
        evidence = json.loads(next((self.workspace / "artifacts/hil").glob("*/evidence.json")).read_text())
        self.assertEqual("failed", evidence["status"])
        self.assertEqual("fake close failed", evidence["client_close_error"])
        self.assertEqual(self.digest, evidence["observed_flash_sha256"])

    def test_output_cannot_escape_workspace(self):
        with self.assertRaisesRegex(hil_artifact.HilError, "inside the local workspace"):
            hil_artifact._inside_workspace(self.workspace, self.workspace.parent / "escape")

    def test_output_symlink_is_refused(self):
        outside = self.workspace / "elsewhere"
        outside.mkdir()
        redirect = self.workspace / "artifacts"
        try:
            redirect.symlink_to(outside, target_is_directory=True)
        except OSError:
            self.skipTest("This account cannot create a directory symlink.")
        with self.assertRaisesRegex(hil_artifact.HilError, "Redirected output"):
            hil_artifact._inside_workspace(self.workspace, redirect / "hil/evidence.json")

    def test_text_only_mcp_results_remain_supported(self):
        self.assertEqual({"ok": True}, hil_artifact.tool_payload({
            "content": [{"type": "text", "text": '{"ok": true}'}]}))


FAKE_SERVER = r'''
import json, sys
mode = sys.argv[1]
for line in sys.stdin:
    request = json.loads(line)
    if 'id' not in request:
        continue
    if request['method'] == 'initialize':
        result = {'protocolVersion': '2024-11-05', 'capabilities': {},
                  'serverInfo': {'name': 'fake-only-no-hardware', 'version': '1'}}
    else:
        if mode == 'timeout':
            continue
        print(json.dumps({'jsonrpc': '2.0', 'method': 'notifications/message', 'params': {}}), flush=True)
        result = {'structuredContent': {'ok': True}, 'content': []}
    response_id = request['id'] + (1 if mode == 'wrong_id' else 0)
    print(json.dumps({'jsonrpc': '2.0', 'id': response_id, 'result': result}), flush=True)
'''


class McpTransportTests(unittest.TestCase):
    def make_client(self, mode="ok", timeout=2):
        real_popen = subprocess.Popen

        def launch(*args, **kwargs):
            return real_popen([sys.executable, "-u", "-c", FAKE_SERVER, mode], **kwargs)

        with mock.patch.object(hil_artifact.subprocess, "Popen", side_effect=launch) as popen:
            client = hil_artifact.McpClient("trusted-agentic-hil", Path.cwd(), timeout_s=timeout)
            self.addCleanup(client.close)
            self.assertEqual(["trusted-agentic-hil", "mcp-stdio"], popen.call_args.args[0])
            self.assertFalse(popen.call_args.kwargs["shell"])
        return client

    def test_handshake_notification_and_tool_result(self):
        client = self.make_client()
        client.initialize()
        raw = client.call("test_reactor_run", {"test_config_path": "trusted.json"})
        self.assertTrue(hil_artifact.tool_payload(raw)["ok"])

    def test_mismatched_response_id_is_refused(self):
        client = self.make_client("wrong_id")
        with self.assertRaisesRegex(hil_artifact.HilError, "response ID"):
            client.initialize()

    def test_tool_timeout_is_bounded_without_retry(self):
        client = self.make_client("timeout", timeout=1)
        client.initialize()
        client.timeout_s = 0.05
        with self.assertRaisesRegex(hil_artifact.HilError, "no automatic retry"):
            client.call("test_reactor_run", {"test_config_path": "trusted.json"})

    def test_client_refuses_unneeded_tools(self):
        client = self.make_client()
        with self.assertRaisesRegex(hil_artifact.HilError, "only permits"):
            client.call("project_config_set", {})


if __name__ == "__main__":
    unittest.main()
