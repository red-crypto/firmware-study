"""Verify a firmware bundle, then run the trusted boot test through MCP only.

The downloaded bundle is data. No bundled Python, PowerShell, or test plan is
executed. Invoke this file from a reviewed local checkout with an operator-pinned
source commit and ELF SHA256 obtained from the selected CI run.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import queue
import shutil
import subprocess
import sys
import threading
import time
from typing import Any
import uuid

from firmware_artifact import verify_bundle


class HilError(RuntimeError):
    """A transport, evidence, or hardware verdict did not meet the contract."""


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _inside_workspace(workspace: Path, path: Path) -> Path:
    """Reject redirects in generated evidence and snapshot paths."""
    root = workspace.resolve(strict=True)
    try:
        relative = path.absolute().relative_to(root)
    except ValueError as error:
        raise HilError("Generated output must remain inside the local workspace.") from error
    current = root
    for part in relative.parts:
        current /= part
        if current.exists() or current.is_symlink():
            attributes = getattr(current.lstat(), "st_file_attributes", 0)
            if current.is_symlink() or attributes & 0x400:  # Windows reparse point
                raise HilError(f"Redirected output path is refused: {current}")
    if not path.resolve().is_relative_to(root):
        raise HilError("Generated output resolves outside the local workspace.")
    return path


def stage_verified_image(workspace: Path, verified: dict[str, Any]) -> Path:
    """Keep the exact validated bytes under HIL's existing artifact root."""
    image = Path(verified["image"])
    expected = verified["sha256"]
    destination = _inside_workspace(
        workspace,
        workspace / ".agentic-hil" / "artifacts" / "ci" / expected / "f411_blinky.elf",
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    _inside_workspace(workspace, destination)
    if not destination.exists():
        try:
            with image.open("rb") as source, destination.open("xb") as target:
                shutil.copyfileobj(source, target)
        except FileExistsError:
            pass
    if sha256(destination) != expected:
        raise HilError("The HIL snapshot SHA256 differs from the verified CI image.")
    return destination


def trusted_plan(image: Path, workspace: Path) -> dict[str, Any]:
    """Use the reviewed hello-world contract, changing only the image path."""
    image = _inside_workspace(workspace, image)
    return {
        "version": 3,
        "name": "ci-artifact-f411-hello-world",
        "steps": [
            {
                "device": "dut",
                "action": "flash",
                "image_path": image.relative_to(workspace).as_posix(),
                "reset_after_flash": False,
            },
            {"device": "dut_uart", "action": "uart_open", "clear_buffer": True},
            {"device": "dut", "action": "reset", "mode": "run"},
            {
                "device": "dut_uart",
                "action": "uart_read",
                "comparator": {"equals": "Hello World"},
                "timeout_s": 5,
            },
        ],
    }


class McpClient:
    """Small bounded JSON-RPC stdio client for the official MCP entry point."""

    def __init__(self, executable: str, workspace: Path, timeout_s: float = 120):
        self.timeout_s = timeout_s
        self._next_id = 0
        self._messages: queue.Queue[Any] = queue.Queue()
        self._stderr: list[str] = []
        self.process = subprocess.Popen(
            [executable, "mcp-stdio"],
            cwd=workspace,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="strict",
            bufsize=1,
            shell=False,
        )
        threading.Thread(target=self._read_stdout, daemon=True).start()
        threading.Thread(target=self._read_stderr, daemon=True).start()

    def _read_stdout(self) -> None:
        try:
            assert self.process.stdout is not None
            for line in self.process.stdout:
                if len(line) > 8 * 1024 * 1024:
                    raise HilError("MCP response exceeded the local evidence size limit.")
                if line.strip():
                    self._messages.put(json.loads(line))
        except Exception as error:
            self._messages.put(error)
        finally:
            self._messages.put(None)

    def _read_stderr(self) -> None:
        try:
            assert self.process.stderr is not None
            for line in self.process.stderr:
                self._stderr.append(line[-2048:])
                self._stderr[:] = self._stderr[-20:]
        except (OSError, UnicodeError):
            pass

    def _send(self, value: dict[str, Any]) -> None:
        if self.process.poll() is not None:
            raise HilError("Agentic HIL MCP server exited before the request.")
        assert self.process.stdin is not None
        self.process.stdin.write(json.dumps(value, allow_nan=False) + "\n")
        self.process.stdin.flush()

    def request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        self._next_id += 1
        request_id = self._next_id
        self._send({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})
        deadline = time.monotonic() + self.timeout_s
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise HilError(f"MCP request timed out: {method}; no automatic retry performed.")
            try:
                response = self._messages.get(timeout=remaining)
            except queue.Empty as error:
                raise HilError(f"MCP request timed out: {method}; no automatic retry performed.") from error
            if response is None:
                raise HilError("MCP connection closed before the result. " + "".join(self._stderr))
            if isinstance(response, Exception):
                raise HilError(f"Invalid MCP response: {response}") from response
            if not isinstance(response, dict) or response.get("jsonrpc") != "2.0":
                raise HilError("The server returned an invalid JSON-RPC response.")
            if "method" in response:
                if "id" in response:
                    # This client does not grant sampling, roots, or execution capabilities.
                    self._send({"jsonrpc": "2.0", "id": response["id"], "error": {
                        "code": -32601, "message": "Client method is not supported"}})
                continue
            if response.get("id") != request_id:
                raise HilError("MCP response ID does not match the pending request.")
            if "error" in response:
                raise HilError(f"MCP rejected {method}: {response['error']}")
            result = response.get("result")
            if not isinstance(result, dict):
                raise HilError("MCP result must be an object.")
            return result

    def initialize(self) -> None:
        result = self.request("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "stm32-trusted-artifact-hil", "version": "1.0"},
        })
        if result.get("protocolVersion") not in {"2024-11-05", "2025-03-26", "2025-06-18"}:
            raise HilError("The server selected an unsupported MCP protocol version.")
        self.initialization = result
        self._send({"jsonrpc": "2.0", "method": "notifications/initialized"})

    def call(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if name != "test_reactor_run":
            raise HilError("This operator entry point only permits the trusted test plan.")
        return self.request("tools/call", {"name": name, "arguments": arguments})

    def close(self) -> None:
        if self.process.stdin is not None:
            try:
                self.process.stdin.close()
            except OSError:
                pass
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)
        for stream in (self.process.stdout, self.process.stderr):
            if stream is not None:
                stream.close()


def tool_payload(raw: dict[str, Any]) -> dict[str, Any]:
    structured = raw.get("structuredContent")
    if isinstance(structured, dict):
        return structured
    for item in raw.get("content", []):
        if item.get("type") == "text":
            try:
                value = json.loads(item.get("text", ""))
            except (TypeError, json.JSONDecodeError):
                continue
            if isinstance(value, dict):
                return value
    raise HilError("Agentic HIL did not return a machine-readable tool result.")


def flash_sha256(result: dict[str, Any]) -> str:
    """Read the actual flash step's artifact identity, never a caller's label."""
    for step in result.get("steps", []):
        if step.get("action") != "flash":
            continue
        payload = step.get("result", step)
        if not isinstance(payload, dict) or any(
            payload.get(key) is not True for key in ("ok", "verify", "success_confirmed")
        ):
            raise HilError("The flash step did not confirm successful read-back verification.")
        for value in (payload, payload.get("artifact", {})):
            if isinstance(value, dict):
                observed = value.get("sha256") or value.get("firmware_sha256")
                if isinstance(observed, str):
                    return observed.lower()
    raise HilError("The reactor result has no observed flash SHA256; evidence is incomplete.")


def write_json(path: Path, value: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def run_verified_bundle(
    workspace: Path,
    bundle: Path,
    expected_commit: str,
    expected_sha256: str,
    *,
    allow_dirty: bool = False,
    executable: str = "agentic-hil",
    client_factory: Any = McpClient,
) -> Path:
    workspace = workspace.resolve(strict=True)
    # This must precede server startup, snapshot staging, and every hardware call.
    verified = verify_bundle(bundle, expected_commit, expected_sha256, allow_dirty=allow_dirty)
    snapshot = stage_verified_image(workspace, verified)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_directory = _inside_workspace(workspace, workspace / "artifacts" / "hil" / f"{stamp}-{uuid.uuid4().hex[:12]}")
    run_directory.mkdir(parents=True)
    plan_path = run_directory / "hello-world.json"
    write_json(plan_path, trusted_plan(snapshot, workspace))
    evidence_path = run_directory / "evidence.json"
    evidence: dict[str, Any] = {
        "schema_version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "not_run",
        "artifact": verified,
        "snapshot": snapshot.relative_to(workspace).as_posix(),
        "plan": plan_path.relative_to(workspace).as_posix(),
        "plan_sha256": sha256(plan_path),
        "verification_scope": "Flash verification and Hello World within 5 seconds; no physical LED or control-loop measurement.",
        "calls": [],
    }
    write_json(evidence_path, evidence)
    client = None
    try:
        client = client_factory(executable, workspace)
        client.initialize()
        evidence["mcp_server"] = getattr(client, "initialization", None)
        evidence["status"] = "running"
        write_json(evidence_path, evidence)
        raw_run = client.call("test_reactor_run", {"test_config_path": evidence["plan"]})
        evidence["calls"].append({"tool": "test_reactor_run", "result": raw_run})
        write_json(evidence_path, evidence)
        result = tool_payload(raw_run)
        # Save this run's own response. A later last-report read could belong to
        # another operator after the reactor releases its device leases.
        evidence["run"] = result.get("run")
        evidence["canonical_report_path"] = result.get("canonical_report_path")
        if raw_run.get("isError") or result.get("ok") is not True:
            raise HilError(f"HIL did not pass: {result.get('error_type', 'unknown_verdict')}; see {evidence_path}")
        # The published MCP catalogue defines omitted cleanup_ok/audit_ok as
        # true, and omitted cleanup_required/quarantined as false. Preserve
        # those compact defaults while refusing malformed explicit values.
        if any(result.get(key, True) is not True for key in ("cleanup_ok", "audit_ok")):
            raise HilError("The hardware run did not confirm successful cleanup and audit.")
        if any(result.get(key, False) is not False for key in ("cleanup_required", "quarantined")):
            raise HilError("The hardware run still requires cleanup or reports quarantine.")
        if not evidence["run"] or not evidence["canonical_report_path"]:
            raise HilError("The reactor returned no canonical run identity; evidence is incomplete.")
        if result.get("test_config_sha256") != evidence["plan_sha256"]:
            raise HilError("The reactor executed a different test plan SHA256.")
        observed = flash_sha256(result)
        evidence["observed_flash_sha256"] = observed
        if observed != verified["sha256"]:
            raise HilError("The reactor flashed a different SHA256 than the pinned CI artifact.")
        if sha256(snapshot) != verified["sha256"]:
            raise HilError("The verified HIL snapshot changed during execution.")
        evidence["status"] = "passed"
    except Exception as error:
        evidence["status"] = "failed"
        evidence["error"] = str(error)
        raise HilError(f"{error}\nEvidence: {evidence_path}") from error
    finally:
        pending_error = sys.exc_info()[0] is not None
        close_error = None
        try:
            if client is not None:
                client.close()
        except Exception as error:
            close_error = error
            evidence["client_close_error"] = str(error)
            evidence["status"] = "failed"
        finally:
            write_json(evidence_path, evidence)
        if close_error is not None and not pending_error:
            raise HilError(f"MCP client shutdown failed: {close_error}\nEvidence: {evidence_path}") from close_error
    return evidence_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--expected-commit", required=True)
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument("--allow-dirty", action="store_true", help="Only for explicit local development evidence, never clean CI provenance.")
    parser.add_argument("--hil-executable", default="agentic-hil", help="Trusted installed Agentic HIL executable; no shell is used.")
    arguments = parser.parse_args(argv)
    workspace = Path(__file__).resolve().parents[1]
    try:
        executable = shutil.which(arguments.hil_executable)
        if executable is None:
            raise HilError("Agentic HIL is not installed or its executable is unavailable.")
        evidence = run_verified_bundle(
            workspace, arguments.bundle.resolve(strict=True), arguments.expected_commit,
            arguments.expected_sha256, allow_dirty=arguments.allow_dirty, executable=executable,
        )
    except (OSError, ValueError, HilError) as error:
        print(str(error), file=sys.stderr)
        return 2
    print(json.dumps({"ok": True, "evidence": str(evidence)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
