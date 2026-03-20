from fastapi import FastAPI, HTTPException, Header, Body
from pydantic import BaseModel
import subprocess
import os
import logging
import hmac
import hashlib

# Configure Logging
from pathlib import Path
from datetime import datetime
import json
from fastapi import Request

# Create logs directory (ensure this exists in the container or volume)
LOG_DIR = Path("/var/log/openclaw")
LOG_DIR.mkdir(parents=True, exist_ok=True)

# Configure structured JSON logger
audit_logger = logging.getLogger("openclaw_audit")
audit_handler = logging.FileHandler(LOG_DIR / "audit.log")
audit_handler.setFormatter(logging.Formatter('%(message)s'))
audit_logger.addHandler(audit_handler)
audit_logger.setLevel(logging.INFO)

# Standard logger for console
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("openclaw-api")

# Rate Limiting
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

limiter = Limiter(key_func=get_remote_address)

app = FastAPI(title="OpenClaw Execution API")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Configuration
HMAC_SECRET_KEY = os.getenv("HMAC_SECRET_KEY")
OPENCLAW_API_KEY = os.getenv("OPENCLAW_API_KEY")

class ExecuteRequest(BaseModel):
    command: str
    signature: str

def log_execution_attempt(
    command: str,
    signature: str,
    signature_valid: bool,
    auth_valid: bool,
    result: str,
    error: str = None,
    source_ip: str = None,
    user_agent: str = None
):
    """Log execution attempt with full context."""
    log_entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "event_type": "execution_attempt",
        "command": command,
        "signature_provided": bool(signature),
        "signature_valid": signature_valid,
        "auth_valid": auth_valid,
        "result": result,  # "approved", "rejected", "error"
        "error": error,
        "source_ip": source_ip,
        "user_agent": user_agent,
        "severity": "INFO" if result == "approved" else "WARNING"
    }
    audit_logger.info(json.dumps(log_entry))

def verify_signature(command: str, signature: str) -> bool:
    """Verify HMAC signature of the command."""
    if not HMAC_SECRET_KEY:
        logger.warning("HMAC_SECRET_KEY not set - signature verification disabled (INSECURE)")
        return False # Fail secure
        
    expected = hmac.new(
        HMAC_SECRET_KEY.encode('utf-8'),
        command.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()
    
    # DEBUG LOGGING REMOVED
    
    return hmac.compare_digest(expected, signature)

@app.get("/")
async def root():
    return {"status": "OpenClaw Active", "mode": "Host Network"}

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

@app.post("/execute")
@limiter.limit("10/minute")
async def execute_command(
    request: Request,
    body: ExecuteRequest,
    authorization: str = Header(None)
):
    """
    Execute a shell command after validating signature and API Key.
    """
    command = body.command
    signature = body.signature
    source_ip = request.client.host
    user_agent = request.headers.get("user-agent")

    # 1. API Key Authentication
    if OPENCLAW_API_KEY:
        if not authorization or not authorization.startswith("Bearer "):
             logger.warning("Rejected: Missing or invalid Authorization header")
             
             log_execution_attempt(
                command=command,
                signature=signature,
                signature_valid=False, # Not checked yet
                auth_valid=False,
                result="rejected",
                error="Missing or invalid Authorization header",
                source_ip=source_ip,
                user_agent=user_agent
             )
             raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
             
        token = authorization.split(" ")[1]
        if not hmac.compare_digest(token, OPENCLAW_API_KEY):
             logger.warning("Rejected: Invalid API Key")
             
             log_execution_attempt(
                command=command,
                signature=signature,
                signature_valid=False, # Not checked yet
                auth_valid=False,
                result="rejected",
                error="Invalid API Key",
                source_ip=source_ip,
                user_agent=user_agent
             )
             raise HTTPException(status_code=403, detail="Invalid API Key")
    else:
         logger.warning("OPENCLAW_API_KEY not set - authentication disabled (INSECURE)")

    # 2. HMAC Signature Verification
    # 2. HMAC Signature Verification
    if not verify_signature(command, signature):
        logger.warning(f"Rejected: Invalid signature for command: {command}")
        
        log_execution_attempt(
            command=command,
            signature=signature,
            signature_valid=False,
            auth_valid=True,
            result="rejected",
            error="Invalid signature",
            source_ip=source_ip,
            user_agent=user_agent
        )
        raise HTTPException(status_code=403, detail="Invalid signature")

    logger.info(f"Authorized execution: {command}")

    # COMMAND ALLOWLIST (Security Hardening P0)
    ALLOWED_PATTERNS = [
        "python3 lab/",
        "python3 core/",
        "pytest ",
        "ls -l",
        "cat lab/",
        "echo ",
        "find lab/",
        "tail -",
        "grep "
    ]
    
    is_allowed = any(command.startswith(pattern) for pattern in ALLOWED_PATTERNS)
    if not is_allowed:
        logger.warning(f"Rejected: Command not in allowlist: {command}")
        log_execution_attempt(
            command=command,
            signature=signature,
            signature_valid=True,
            auth_valid=True,
            result="rejected",
            error="Command not in allowlist",
            source_ip=source_ip,
            user_agent=user_agent
        )
        raise HTTPException(status_code=403, detail="Command not in allowlist")

    try:
        # Safe quoting for the inner command
        import json
        safe_cmd_str = json.dumps(command)
        
        firejail_command = f"firejail --quiet --noprofile --private=. --net=none -- /bin/sh -c {safe_cmd_str}"
        
        logger.info(f"Executing sandboxed: {firejail_command}")

        # Execute command
        result = subprocess.run(
            firejail_command,
            shell=True,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=30 # Prevent hanging processes
        )
        
        log_execution_attempt(
            command=command,
            signature=signature,
            signature_valid=True,
            auth_valid=True,
            result="approved",
            source_ip=source_ip,
            user_agent=user_agent
        )
        
        return {
            "status": "success",
            "output": result.stdout,
            "error": result.stderr,
            "return_code": result.returncode
        }
        
    except subprocess.CalledProcessError as e:
        logger.error(f"Command failed: {e.stderr}")
        
        log_execution_attempt(
            command=command,
            signature=signature,
            signature_valid=True,
            auth_valid=True,
            result="error",
            error=e.stderr,
            source_ip=source_ip,
            user_agent=user_agent
        )
        
        return {
            "status": "error",
            "output": e.stdout,
            "error": e.stderr,
            "return_code": e.returncode
        }
    except subprocess.TimeoutExpired:
        logger.error("Command timed out")
        
        log_execution_attempt(
            command=command,
            signature=signature,
            signature_valid=True,
            auth_valid=True,
            result="error",
            error="Command timed out",
            source_ip=source_ip,
            user_agent=user_agent
        )
        raise HTTPException(status_code=408, detail="Command execution timed out")
    except Exception as e:
        logger.exception("Unexpected execution error")
        
        log_execution_attempt(
            command=command,
            signature=signature,
            signature_valid=True,
            auth_valid=True,
            result="error",
            error=str(e),
            source_ip=source_ip,
            user_agent=user_agent
        )
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=9001)
