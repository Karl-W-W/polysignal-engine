"""
agents/streaming.py
===================
FastAPI streaming agent endpoint using LangGraph ReAct agent.

Migrated from deprecated AgentExecutor (LangChain 0.x) to
langgraph.prebuilt.create_react_agent (LangGraph 0.2.x).

Migration date: 2026-02-27
Reason: AgentExecutor removed in LangChain 1.x, caused 30s crash loop.
"""

import traceback
import json
import os
import requests
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from langchain_openai import ChatOpenAI
from langchain_core.tools import StructuredTool
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.prebuilt import create_react_agent
from pydantic import BaseModel, Field
from dotenv import load_dotenv

load_dotenv()

# LangSmith Tracing — controlled by .env (default: off)
# To enable: set LANGCHAIN_TRACING_V2=true in .env with a valid LANGCHAIN_API_KEY
if not os.getenv("LANGCHAIN_TRACING_V2"):
    os.environ["LANGCHAIN_TRACING_V2"] = "false"

app = FastAPI()


# ============================================================================
# TOOL DEFINITION
# ============================================================================

class InlineInput(BaseModel):
    command: str = Field(description="Shell command to execute in sandbox")


def inline_run(command: str) -> str:
    """Execute a shell command in the secure OpenClaw sandbox."""
    from core.supervisor import audit_action

    # Step 1: Audit with NVIDIA Supervisor
    try:
        audit_result = audit_action({
            "tool": "exec_cmd",
            "command": command,
            "reasoning": "Agent execution"
        })
    except Exception as e:
        return f"SUPERVISOR ERROR: {e}"

    if audit_result.get("verdict") != "APPROVE":
        return f"REJECTED by supervisor: {audit_result.get('reasoning')}"

    # Step 2: Extract HMAC signature
    signature = audit_result.get("signature")

    # Step 3: Execute in OpenClaw container
    try:
        openclaw_host = os.getenv("OPENCLAW_HOST", "http://localhost:9001")
        response = requests.post(
            f"{openclaw_host}/execute",
            json={"command": command, "signature": signature},
            headers={"Authorization": f"Bearer {os.getenv('OPENCLAW_API_KEY')}"},
            timeout=30,
        )
        if response.status_code == 200:
            result = response.json()
            return f"SUCCESS:\n{result['output']}"
        else:
            return f"ERROR ({response.status_code}): {response.text}"
    except Exception as e:
        return f"EXECUTION FAILED: {e}"


def get_tool():
    return StructuredTool.from_function(
        func=inline_run,
        name="exec_cmd",
        description="Execute a shell command in the secure OpenClaw sandbox.",
        args_schema=InlineInput,
    )


# ============================================================================
# LLM CONFIGURATION
# ============================================================================

def get_llm():
    """Factory to get the configured LLM — LOCAL Ollama on DGX."""
    ollama_host = os.getenv("OLLAMA_HOST", "http://172.17.0.1:11434")
    model = os.getenv("OLLAMA_CHAT_MODEL", "llama3.2:3b")
    return ChatOpenAI(
        base_url=f"{ollama_host}/v1",
        model=model,
        api_key="ollama",
        streaming=True,
        temperature=0,
    )


def _load_identity_kernel() -> str:
    """Load the Identity Kernel system prompt."""
    kernel_paths = [
        "/opt/loop/brain/identity_kernel.md",
        "/app/brain/identity_kernel.md",
        os.path.join(os.path.dirname(__file__), "..", "brain", "identity_kernel.md"),
    ]
    for p in kernel_paths:
        if os.path.exists(p):
            with open(p) as f:
                return f.read()
    return ""


_KERNEL_TEXT = _load_identity_kernel()

SYSTEM_PROMPT = f"""You are the PolySignal Autonomous Agent — a secure AI operating system.

{_KERNEL_TEXT}

## YOUR CAPABILITIES
You have ONE tool: `exec_cmd` — it executes shell commands in the secure OpenClaw sandbox.

## CRITICAL RULES
- When a user asks you to DO something (list files, run a script, check status, etc.), you MUST call the `exec_cmd` tool. Do NOT just describe what the tool does — actually USE it.
- When a user asks a QUESTION (what is 2+2, explain something), answer directly without using tools.
- After executing a command, report the results clearly and concisely.
- If a command is rejected by the NVIDIA Supervisor, explain why and suggest alternatives.
"""


# ============================================================================
# AGENT (LangGraph ReAct)
# ============================================================================

def create_streaming_agent():
    llm = get_llm()
    tools = [get_tool()]
    return create_react_agent(llm, tools, prompt=SYSTEM_PROMPT)


# ============================================================================
# ENDPOINTS
# ============================================================================

@app.post("/api/agent/stream")
async def agent_stream(request: dict):
    """Stream agent execution to client via SSE."""
    user_input = request.get("input", "")
    agent = create_streaming_agent()

    async def generate():
        try:
            async for event in agent.astream_events(
                {"messages": [HumanMessage(content=user_input)]},
                version="v2",
            ):
                kind = event.get("event")

                # Stream LLM token chunks
                if kind == "on_chat_model_stream":
                    content = event["data"]["chunk"].content
                    if content:
                        data = json.dumps({"type": "chunk", "content": content})
                        yield f"data: {data}\n\n"

                # Stream tool results
                elif kind == "on_tool_end":
                    output = event["data"].get("output", "")
                    if output:
                        data = json.dumps({"type": "tool_result", "content": str(output)})
                        yield f"data: {data}\n\n"

        except Exception as e:
            error_data = json.dumps({
                "type": "error",
                "message": str(e),
                "traceback": traceback.format_exc(),
            })
            yield f"data: {error_data}\n\n"

        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    checks = {
        "service": "healthy",
        "openclaw_connection": "unknown",
        "supervisor_connection": "unknown",
        "llm_provider": os.getenv("LLM_PROVIDER", "ollama"),
    }

    openclaw_host = os.getenv("OPENCLAW_HOST", "http://localhost:9001")
    try:
        response = requests.get(f"{openclaw_host}/", timeout=2)
        checks["openclaw_connection"] = "healthy" if response.ok else "unhealthy"
    except Exception:
        checks["openclaw_connection"] = "unreachable"

    try:
        from core.supervisor import audit_action  # noqa: F401
        checks["supervisor_connection"] = "library_loaded"
    except Exception:
        checks["supervisor_connection"] = "error"

    return checks
