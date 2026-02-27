import traceback
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from langchain_openai import ChatOpenAI
from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain.tools import StructuredTool
from langchain_core.prompts import ChatPromptTemplate
from dotenv import load_dotenv
import json
import asyncio
import os
import requests

# Load environment variables
load_dotenv()

# LangSmith Tracing — DISABLED (API key expired, returns 403)
# To re-enable: set LANGCHAIN_TRACING_V2=true in .env with valid API key
os.environ["LANGCHAIN_TRACING_V2"] = "false"

app = FastAPI()

# Import OpenClaw tool
# from openclaw_bridge import get_tool
from core.bridge import OpenClawTool 
from langchain.tools import StructuredTool
from pydantic import BaseModel, Field

class InlineInput(BaseModel):
    command: str = Field(description="Shell command to execute in sandbox")

def inline_run(command: str):
    """Execute a shell command in the secure OpenClaw sandbox."""
    # Import here to avoid circular dependency
    from core.supervisor import audit_action
    
    # Step 1: Audit with NVIDIA Supervisor
    try:
        audit_result = audit_action({
            "tool": "exec_cmd",
            "command": command,
            "reasoning": "Agent execution"
        })
    except Exception as e:
        return f"❌ SUPERVISOR ERROR: {str(e)}"
    
    if audit_result.get("verdict") != "APPROVE":
        return f"❌ REJECTED by supervisor: {audit_result.get('reasoning')}"
    
    # Step 2: Extract HMAC signature
    signature = audit_result.get("signature")
    
    # Step 3: Execute in OpenClaw container
    try:
        openclaw_host = os.getenv("OPENCLAW_HOST", "http://localhost:9001")
        
        response = requests.post(
            f"{openclaw_host}/execute",
            json={
                "command": command,
                "signature": signature
            },
            headers={
                "Authorization": f"Bearer {os.getenv('OPENCLAW_API_KEY')}"
            },
            timeout=30
        )
        
        if response.status_code == 200:
            result = response.json()
            return f"✅ SUCCESS:\n{result['output']}"
        else:
            return f"❌ ERROR: {response.text}"
            
    except Exception as e:
        return f"❌ EXECUTION FAILED: {str(e)}"

async def inline_arun(command: str):
    from core.bridge import OpenClawTool
    return await OpenClawTool()._arun(command)

def get_tool():
    return StructuredTool.from_function(
        func=inline_run,
        coroutine=inline_arun,
        name="exec_cmd",
        description="Execute a shell command in the secure OpenClaw sandbox.",
        args_schema=InlineInput
    )


def get_llm():
    """Factory to get the configured LLM — LOCAL Ollama on DGX."""
    ollama_host = os.getenv("OLLAMA_HOST", "http://172.17.0.1:11434")
    model = os.getenv("OLLAMA_CHAT_MODEL", "llama3.2:3b")
    
    return ChatOpenAI(
        base_url=f"{ollama_host}/v1",
        model=model,
        api_key="ollama",  # Ollama doesn't need a real key
        streaming=True,
        temperature=0
    )

def _load_identity_kernel() -> str:
    """Load the Identity Kernel system prompt."""
    kernel_paths = [
        "/opt/loop/brain/identity_kernel.md",
        "/app/brain/identity_kernel.md",
        os.path.join(os.path.dirname(__file__), "..", "brain", "identity_kernel.md")
    ]
    for p in kernel_paths:
        if os.path.exists(p):
            with open(p) as f:
                # Escape curly braces so LangChain prompt template doesn't treat them as variables
                return f.read().replace("{", "{{").replace("}", "}}")
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

def create_streaming_agent():
    llm = get_llm()
    
    # Register tools
    tool = get_tool()
    tools = [tool]
    
    # Create agent with Identity Kernel
    prompt = ChatPromptTemplate.from_messages([
        ("system", SYSTEM_PROMPT),
        ("human", "{input}"),
        ("placeholder", "{agent_scratchpad}"),
    ])
    
    agent = create_tool_calling_agent(llm, tools, prompt)
    return AgentExecutor(agent=agent, tools=tools, verbose=True)

@app.post("/api/agent/stream")
async def agent_stream(request: dict):
    """Stream agent execution to client."""
    user_input = request.get("input")
    
    agent_executor = create_streaming_agent()
    
    async def generate():
        """Yield chunks as they're generated."""
        try:
            # Stream agent execution
            async for chunk in agent_executor.astream({"input": user_input}):
                # Extract clean output text from the chunk
                if isinstance(chunk, dict) and "output" in chunk:
                    content = chunk["output"]
                elif isinstance(chunk, dict):
                    # Intermediate step — skip tool calls, agent scratchpad, etc.
                    continue
                else:
                    content = str(chunk)
                
                if not content or not content.strip():
                    continue
                
                data = json.dumps({
                    "type": "chunk",
                    "content": content
                })
                yield f"data: {data}\n\n"
                
        except Exception as e:
            error_data = json.dumps({
                "type": "error",
                "message": str(e),
                "traceback": traceback.format_exc()
            })
            yield f"data: {error_data}\n\n"
        
        # Final message
        done_data = json.dumps({"type": "done"})
        yield f"data: {done_data}\n\n"
    
    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )

@app.get("/health")
async def health_check():
    """Comprehensive health check."""
    checks = {
        "service": "healthy",
        "openclaw_connection": "unknown",
        "supervisor_connection": "unknown",
        "llm_provider": os.getenv("LLM_PROVIDER", "openai")
    }
    
    # Test OpenClaw
    openclaw_host = os.getenv("OPENCLAW_HOST", "http://localhost:9001")
    try:
        # Try checking the root path which is more likely to exist than /health on raw containers
        response = requests.get(f"{openclaw_host}/", timeout=2)
        checks["openclaw_connection"] = "healthy" if response.ok else "unhealthy"
    except Exception as e:
        # Keep it concise but maybe log it if we had a logger
        checks["openclaw_connection"] = "unreachable"
    
    # Test NVIDIA Supervisor (Simulated check as we don't want to spam actual API)
    try:
        from supervisor_client import audit_action
        # Just check import is working, actual connection verification might be cleaner separately
        checks["supervisor_connection"] = "library_loaded" 
    except:
        checks["supervisor_connection"] = "error"
    
    return checks
