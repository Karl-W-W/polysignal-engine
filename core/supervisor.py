#!/usr/bin/env python3
"""
supervisor_client.py
Security Supervisor client using LOCAL Ollama (DGX inference)
"""

import os
import json
import hmac
import hashlib
from typing import Dict, Any
from openai import OpenAI

# ============================================================================
# CONFIGURATION
# ============================================================================

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://172.17.0.1:11434")
OLLAMA_SUPERVISOR_MODEL = os.getenv("OLLAMA_SUPERVISOR_MODEL", "llama3.3:70b")

HMAC_SECRET = os.getenv("HMAC_SECRET_KEY", "default_insecure_key_for_dev").encode('utf-8')

# Safe commands that can be auto-approved without LLM audit
# Aligned with Identity Kernel: "Low Risk (Auto-Approve)" category
SAFE_COMMANDS = {'ls', 'cat', 'grep', 'find', 'echo', 'printf', 'date', 'whoami', 'pwd', 'head', 'tail', 'wc', 'du', 'df', 'file', 'stat', 'env', 'printenv'}

# Dangerous patterns that should always go through LLM audit
DANGEROUS_PATTERNS = {'rm', 'mv', 'chmod', 'chown', 'sudo', 'docker', 'systemctl', 'kill', 'mkfs', 'dd', 'wget', 'curl', '>', '>>', '|', ';', '&&', '$(', '`'}


def _is_safe_command(command: str) -> bool:
    """Check if command is safe for auto-approval (no LLM audit needed)."""
    cmd = command.strip()
    base_cmd = cmd.split()[0] if cmd.split() else ""
    
    # Check for dangerous patterns first
    for pattern in DANGEROUS_PATTERNS:
        if pattern in cmd:
            return False
    
    # Check if base command is in safe list
    return base_cmd in SAFE_COMMANDS


def _sign_action(draft: Dict[str, Any]) -> str:
    """Generate HMAC signature for approved action.
    Signs ONLY the command string to match OpenClaw's verify_signature().
    """
    command = draft.get("command", "")
    return hmac.new(HMAC_SECRET, command.encode('utf-8'), hashlib.sha256).hexdigest()


# ============================================================================
# AUDIT FUNCTION
# ============================================================================

def audit_action(draft: Dict[str, Any]) -> Dict[str, Any]:
    """
    Audit a proposed action. Fast-path for safe commands, LLM audit for risky ones.
    """
    command = draft.get("command", "")
    
    # FAST PATH: Auto-approve safe read-only commands
    if _is_safe_command(command):
        return {
            "verdict": "APPROVE",
            "reasoning": f"Auto-approved: '{command.split()[0]}' is a safe read-only operation.",
            "risk_level": "low",
            "signature": _sign_action(draft)
        }
    
    # SLOW PATH: Full LLM audit for potentially dangerous commands
    nvidia_key = os.getenv("NVIDIA_API_KEY")
    if nvidia_key and os.getenv("USE_NVIDIA_CLOUD", "").lower() == "true":
        client = OpenAI(
            base_url="https://integrate.api.nvidia.com/v1",
            api_key=nvidia_key
        )
        model = "meta/llama-3.3-70b-instruct"
    else:
        client = OpenAI(
            base_url=f"{OLLAMA_HOST}/v1",
            api_key="ollama"
        )
        model = OLLAMA_SUPERVISOR_MODEL
    
    # Load identity kernel
    try:
        # Try production path first, then relative for local test
        paths = ["/opt/loop/brain/identity_kernel.md", "../brain/identity_kernel.md", "identity_kernel.md"]
        kernel = "IDENTITY KERNEL NOT FOUND"
        for p in paths:
             if os.path.exists(p):
                 with open(p, "r") as f:
                     kernel = f.read()
                 break
    except Exception as e:
        print(f"Warning loading kernel: {e}")
        kernel = "IDENTITY KERNEL NOT FOUND - OPERATING IN DEGRADED MODE"
    
    # Load auditor system prompt
    try:
        paths = ["/opt/loop/brain/auditor_prompt.txt", "../brain/auditor_prompt.txt", "auditor_prompt.txt"]
        auditor_prompt = "You are a security auditor."
        for p in paths:
             if os.path.exists(p):
                 with open(p, "r") as f:
                     auditor_prompt = f.read()
                 break
    except Exception as e:
         print(f"Warning loading prompt: {e}")
         auditor_prompt = "You are a security auditor. Evaluate if actions are safe."
    
    # Build audit request
    messages = [
        {
            "role": "system",
            "content": auditor_prompt
        },
        {
            "role": "user",
            "content": f"""
IDENTITY KERNEL:
{kernel}

DRAFT ACTION TO AUDIT:
{json.dumps(draft, indent=2)}

Analyze this action and provide your verdict in JSON format with these fields:
- verdict: "APPROVE" or "REJECT" or "REQUEST_HUMAN_APPROVAL"
- reasoning: Your step-by-step analysis
- risk_level: "low" or "medium" or "high" or "critical"
- modifications: (optional) Safer alternatives if rejecting

Return ONLY valid JSON, no additional text.
"""
        }
    ]
    
    try:
        # Call LLM API (Ollama local or NVIDIA Cloud)
        completion = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0.1,  # Low temperature for consistent security decisions
            top_p=0.7,
            max_tokens=1024,
            stream=False
        )
        
        # Parse response
        response_text = completion.choices[0].message.content
        
        # Extract JSON (handle cases where LLM adds markdown code blocks)
        if "```json" in response_text:
            response_text = response_text.split("```json")[1].split("```")[0]
        elif "```" in response_text:
            response_text = response_text.split("```")[1].split("```")[0]
        
        # strict=False tolerates control characters (newlines/tabs) inside JSON
        # string values, which Ollama's llama3.3:70b sometimes produces
        verdict = json.loads(response_text.strip(), strict=False)
        
        # Generate HMAC signature if approved
        if verdict.get("verdict") == "APPROVE":
            # BUG FIX: Sign ONLY the command string to match OpenClaw's verification logic
            # The OpenClaw API only receives the command, so it can only verify that.
            payload = draft.get("command", "")
            signature = hmac.new(
                HMAC_SECRET,
                payload.encode('utf-8'),
                hashlib.sha256
            ).hexdigest()
            verdict["signature"] = signature
            verdict["signed_at"] = "NVIDIA_API_SUPERVISOR"
        else:
            verdict["signature"] = None
        
        # Add metadata
        verdict["supervisor"] = "NVIDIA_API_Llama_3.3_70B"
        verdict["model"] = "meta/llama-3.3-70b-instruct"
        
        return verdict
    
    except json.JSONDecodeError as e:
        # Fallback if LLM doesn't return valid JSON
        return {
            "verdict": "REJECT",
            "reasoning": f"Supervisor returned invalid JSON: {str(e)}. Response: {response_text[:200]}",
            "risk_level": "critical",
            "signature": None,
            "error": "INVALID_RESPONSE_FORMAT"
        }
    
    except Exception as e:
        # Hard failure - reject for safety
        return {
            "verdict": "REJECT",
            "reasoning": f"Supervisor communication failed: {str(e)}",
            "risk_level": "critical",
            "signature": None,
            "error": str(e)
        }

# ============================================================================
# VERIFICATION FUNCTION (For OpenClaw Bridge)
# ============================================================================

def verify_signature(draft: Dict[str, Any], signature: str) -> bool:
    """
    Verify HMAC signature matches the draft action.
    
    This is the "Hardware Veto" enforcement point.
    NOTE: Signs ONLY the command string, matching audit_action's signing behavior.
    """
    # BUG FIX: audit_action signs only draft.get("command", ""), not the whole JSON dict
    payload = draft.get("command", "")
    expected = hmac.new(
        HMAC_SECRET,
        payload.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()
    
    return hmac.compare_digest(expected, signature)

# ============================================================================
# EXAMPLE USAGE / TESTING
# ============================================================================

if __name__ == "__main__":
    # Test 1: Safe action
    print("TEST 1: Safe Action")
    test_draft = {
        "tool": "openclaw_execute",
        "command": "ls -la /mnt/workplace",
        "workspace": "/mnt/workplace",
        "reasoning": "List project files"
    }
    
    result = audit_action(test_draft)
    print(json.dumps(result, indent=2))
    print()
    
    # Test 2: Malicious action
    print("TEST 2: Malicious Action")
    malicious_draft = {
        "tool": "openclaw_execute",
        "command": "rm -rf /",
        "workspace": "/",
        "reasoning": "Clean up files"
    }
    
    result = audit_action(malicious_draft)
    print(json.dumps(result, indent=2))
