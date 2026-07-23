"""Safe capability probes for locally installed coding-agent providers.

Default probes never submit a prompt. They inspect CLI metadata,
authentication state, and the Codex app-server JSON-RPC handshake. Sensitive
account fields are deliberately discarded before results are returned.
"""
from __future__ import annotations

import json
import selectors
import shutil
import subprocess
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Sequence


RunCommand = Callable[..., subprocess.CompletedProcess[str]]


@dataclass
class Check:
    name: str
    status: str
    detail: str
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ProviderReport:
    provider: str
    executable: str | None
    checks: list[Check]

    @property
    def ready(self) -> bool:
        return bool(self.executable) and all(
            check.status != "fail" for check in self.checks
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "executable": self.executable,
            "ready": self.ready,
            "checks": [check.to_dict() for check in self.checks],
        }


def _run(
    command: Sequence[str],
    *,
    cwd: Path,
    timeout: float = 10,
    runner: RunCommand = subprocess.run,
) -> subprocess.CompletedProcess[str]:
    return runner(
        list(command),
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def _combined_output(result: subprocess.CompletedProcess[str]) -> str:
    return "\n".join(part.strip() for part in (result.stdout, result.stderr) if part)


def _version_check(
    executable: str,
    *,
    cwd: Path,
    runner: RunCommand,
) -> Check:
    result = _run([executable, "--version"], cwd=cwd, runner=runner)
    output = _combined_output(result)
    version_lines = (result.stdout or "").strip().splitlines()
    return Check(
        name="version",
        status="pass" if result.returncode == 0 else "fail",
        detail=(
            version_lines[0]
            if version_lines
            else (output.splitlines()[0] if output else "No version output")
        ),
    )


def _capability_check(help_text: str, required: dict[str, str]) -> Check:
    capabilities = {name: flag in help_text for name, flag in required.items()}
    missing = [name for name, available in capabilities.items() if not available]
    return Check(
        name="capabilities",
        status="pass" if not missing else "fail",
        detail=(
            "Required integration flags are available"
            if not missing
            else f"Missing capabilities: {', '.join(missing)}"
        ),
        data=capabilities,
    )


def probe_claude(
    root: Path,
    *,
    executable: str = "claude",
    runner: RunCommand = subprocess.run,
) -> ProviderReport:
    resolved = shutil.which(executable)
    if not resolved:
        return ProviderReport(
            "claude",
            None,
            [Check("executable", "fail", f"{executable!r} was not found on PATH")],
        )

    checks = [_version_check(executable, cwd=root, runner=runner)]
    auth = _run([executable, "auth", "status", "--json"], cwd=root, runner=runner)
    try:
        payload = json.loads(auth.stdout)
    except (json.JSONDecodeError, TypeError):
        payload = {}

    # Never retain email, organization identifiers, access tokens, or paths.
    safe_auth = {
        key: payload.get(key)
        for key in ("loggedIn", "authMethod", "apiProvider", "subscriptionType")
        if key in payload
    }
    subscription_auth = (
        auth.returncode == 0
        and safe_auth.get("loggedIn") is True
        and safe_auth.get("authMethod") == "claude.ai"
    )
    checks.append(
        Check(
            "authentication",
            "pass" if subscription_auth else "fail",
            (
                "Authenticated through claude.ai subscription"
                if subscription_auth
                else "Claude subscription authentication was not confirmed"
            ),
            safe_auth,
        )
    )

    help_result = _run([executable, "--help"], cwd=root, runner=runner)
    help_text = _combined_output(help_result)
    checks.append(
        _capability_check(
            help_text,
            {
                "stream_input": "--input-format",
                "stream_output": "--output-format",
                "partial_messages": "--include-partial-messages",
                "hook_events": "--include-hook-events",
                "resume": "--resume",
                "session_id": "--session-id",
                "fork_session": "--fork-session",
                "remote_control": "--remote-control",
                "background_agents": "--background",
                "worktrees": "--worktree",
                "permissions": "--permission-mode",
            },
        )
    )
    checks.append(
        Check(
            "remote_streaming_compatibility",
            "warn",
            (
                "CLI metadata exposes structured streaming in print mode and "
                "Remote Control in interactive mode; runtime compatibility "
                "requires an explicit quota-consuming probe"
            ),
            {
                "structured_mode": "print",
                "remote_control_mode": "interactive",
                "verified_together": False,
            },
        )
    )
    return ProviderReport("claude", resolved, checks)


def _read_json_line(
    process: subprocess.Popen[str],
    *,
    timeout: float,
) -> dict[str, Any]:
    assert process.stdout is not None
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ)
    deadline = time.monotonic() + timeout
    try:
        while time.monotonic() < deadline:
            events = selector.select(max(0, deadline - time.monotonic()))
            if not events:
                continue
            line = process.stdout.readline()
            if not line:
                break
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                continue
    finally:
        selector.close()
    raise TimeoutError("Timed out waiting for a JSON-RPC response")


def _read_response(
    process: subprocess.Popen[str],
    request_id: int,
    *,
    timeout: float,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        response = _read_json_line(
            process,
            timeout=max(0.1, deadline - time.monotonic()),
        )
        if response.get("id") == request_id:
            return response
    raise TimeoutError(f"Timed out waiting for JSON-RPC response {request_id}")


def _send_json(process: subprocess.Popen[str], payload: dict[str, Any]) -> None:
    assert process.stdin is not None
    process.stdin.write(json.dumps(payload, separators=(",", ":")) + "\n")
    process.stdin.flush()


def probe_codex_app_server(
    root: Path,
    *,
    executable: str = "codex",
    timeout: float = 8,
    popen_factory: Callable[..., subprocess.Popen[str]] = subprocess.Popen,
) -> Check:
    process = popen_factory(
        [executable, "app-server", "--stdio"],
        cwd=root,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    try:
        _send_json(
            process,
            {
                "id": 1,
                "method": "initialize",
                "params": {
                    "clientInfo": {
                        "name": "rocketry-provider-probe",
                        "version": "0.1.0",
                    },
                    "capabilities": {"experimentalApi": False},
                },
            },
        )
        initialized = _read_response(process, 1, timeout=timeout)
        if initialized.get("id") != 1 or "result" not in initialized:
            raise RuntimeError(f"Unexpected initialize response: {initialized}")

        _send_json(
            process,
            {"method": "initialized", "params": {}},
        )
        _send_json(
            process,
            {
                "id": 2,
                "method": "account/read",
                "params": {"refreshToken": False},
            },
        )
        account_response = _read_response(process, 2, timeout=timeout)
        if account_response.get("id") != 2 or "result" not in account_response:
            raise RuntimeError(f"Unexpected account response: {account_response}")

        result = account_response["result"]
        account = result.get("account") or {}
        # The email returned by app-server is intentionally not retained.
        safe_account = {
            "type": account.get("type"),
            "planType": account.get("planType"),
            "requiresOpenaiAuth": result.get("requiresOpenaiAuth"),
        }
        is_chatgpt = account.get("type") == "chatgpt"
        return Check(
            "app_server_handshake",
            "pass" if is_chatgpt else "fail",
            (
                "JSON-RPC initialized and confirmed ChatGPT authentication"
                if is_chatgpt
                else "JSON-RPC initialized but ChatGPT authentication was not confirmed"
            ),
            safe_account,
        )
    except (OSError, RuntimeError, TimeoutError) as exc:
        return Check("app_server_handshake", "fail", str(exc))
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2)


def probe_codex(
    root: Path,
    *,
    executable: str = "codex",
    runner: RunCommand = subprocess.run,
    protocol: bool = True,
) -> ProviderReport:
    resolved = shutil.which(executable)
    if not resolved:
        return ProviderReport(
            "codex",
            None,
            [Check("executable", "fail", f"{executable!r} was not found on PATH")],
        )

    checks = [_version_check(executable, cwd=root, runner=runner)]
    auth = _run([executable, "login", "status"], cwd=root, runner=runner)
    auth_text = _combined_output(auth)
    chatgpt_auth = auth.returncode == 0 and "using ChatGPT" in auth_text
    checks.append(
        Check(
            "authentication",
            "pass" if chatgpt_auth else "fail",
            (
                "Authenticated through ChatGPT"
                if chatgpt_auth
                else "ChatGPT authentication was not confirmed"
            ),
            {"authMethod": "chatgpt" if chatgpt_auth else "unknown"},
        )
    )

    help_result = _run([executable, "app-server", "--help"], cwd=root, runner=runner)
    help_text = _combined_output(help_result)
    checks.append(
        _capability_check(
            help_text,
            {
                "app_server": "Run the app server",
                "stdio": "stdio://",
                "unix_socket": "unix://",
                "websocket": "ws://",
                "schema_generation": "generate-json-schema",
            },
        )
    )
    if protocol:
        checks.append(probe_codex_app_server(root, executable=executable))
    return ProviderReport("codex", resolved, checks)


def probe_all(root: Path, *, codex_protocol: bool = True) -> dict[str, Any]:
    reports = [
        probe_codex(root, protocol=codex_protocol),
        probe_claude(root),
    ]
    return {
        "schemaVersion": 1,
        "quotaConsumed": False,
        "root": str(root.resolve()),
        "providers": [report.to_dict() for report in reports],
    }
