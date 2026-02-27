"""
Tests for core/supervisor.py — NVIDIA Supervisor security audit.
"""

import hmac
import hashlib
import pytest
from unittest.mock import patch, MagicMock
from core.supervisor import (
    audit_action,
    verify_signature,
    _is_safe_command,
    _sign_action,
    SAFE_COMMANDS,
    DANGEROUS_PATTERNS,
)


class TestSafeCommandDetection:
    """Test the fast-path auto-approve logic."""

    @pytest.mark.parametrize("cmd", [
        "ls -la /mnt/workplace",
        "cat /etc/hostname",
        "grep -r 'pattern' .",
        "find . -name '*.py'",
        "echo hello",
        "date",
        "whoami",
        "pwd",
        "head -n 10 file.txt",
        "tail -f log.txt",
        "wc -l file.txt",
    ])
    def test_safe_commands_detected(self, cmd):
        assert _is_safe_command(cmd), f"Expected safe: {cmd}"

    @pytest.mark.parametrize("cmd", [
        "rm -rf /",
        "sudo reboot",
        "chmod 777 /etc/passwd",
        "docker exec bash",
        "systemctl stop openclaw",
        "kill -9 1234",
        "cat file | grep secret",
        "ls; rm -rf /",
        "echo $(whoami)",
        "cat file > /etc/passwd",
    ])
    def test_dangerous_commands_detected(self, cmd):
        assert not _is_safe_command(cmd), f"Expected dangerous: {cmd}"


class TestFastPathAudit:
    """Test that safe commands get auto-approved without LLM call."""

    def test_safe_command_auto_approved(self):
        result = audit_action({"command": "ls -la /tmp", "tool": "exec_cmd"})
        assert result["verdict"] == "APPROVE"
        assert result["risk_level"] == "low"
        assert result["signature"] is not None

    def test_safe_command_has_valid_signature(self):
        result = audit_action({"command": "echo hello", "tool": "exec_cmd"})
        sig = result["signature"]
        assert verify_signature({"command": "echo hello"}, sig)


class TestHMACSigning:
    """Test HMAC signature generation and verification."""

    def test_sign_and_verify_roundtrip(self):
        draft = {"command": "ls -la /tmp"}
        sig = _sign_action(draft)
        assert verify_signature(draft, sig)

    def test_wrong_command_fails_verification(self):
        draft = {"command": "ls -la /tmp"}
        sig = _sign_action(draft)
        assert not verify_signature({"command": "rm -rf /"}, sig)

    def test_tampered_signature_fails(self):
        draft = {"command": "echo test"}
        sig = _sign_action(draft)
        tampered = sig[:-4] + "dead"
        assert not verify_signature(draft, tampered)

    def test_empty_command_signs_correctly(self):
        draft = {"command": ""}
        sig = _sign_action(draft)
        assert verify_signature(draft, sig)


class TestSlowPathAudit:
    """Test LLM-based audit for dangerous commands (mocked)."""

    @patch("core.supervisor.OpenAI")
    def test_dangerous_command_goes_to_llm(self, mock_openai_cls):
        # Mock the LLM to return a JSON APPROVE verdict
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_client.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(
                content='{"verdict": "APPROVE", "reasoning": "Test approved", "risk_level": "medium"}'
            ))]
        )

        result = audit_action({"command": "rm old_file.txt", "tool": "exec_cmd"})
        assert result["verdict"] == "APPROVE"
        assert result["signature"] is not None
        mock_client.chat.completions.create.assert_called_once()

    @patch("core.supervisor.OpenAI")
    def test_llm_reject_returns_no_signature(self, mock_openai_cls):
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_client.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(
                content='{"verdict": "REJECT", "reasoning": "Too dangerous", "risk_level": "critical"}'
            ))]
        )

        result = audit_action({"command": "rm -rf /", "tool": "exec_cmd"})
        assert result["verdict"] == "REJECT"
        assert result["signature"] is None

    @patch("core.supervisor.OpenAI")
    def test_llm_error_rejects_safely(self, mock_openai_cls):
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_client.chat.completions.create.side_effect = Exception("Connection refused")

        result = audit_action({"command": "python script.py", "tool": "exec_cmd"})
        assert result["verdict"] == "REJECT"
        assert result["signature"] is None
        assert "communication failed" in result["reasoning"].lower()
