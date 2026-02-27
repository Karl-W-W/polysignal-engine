from langchain_core.tools import BaseTool, StructuredTool
from langchain_core.callbacks import CallbackManagerForToolRun
from typing import Optional, Type
from pydantic import BaseModel, Field
import requests
import os

class ExecCmdInput(BaseModel):
    """Input schema for OpenClaw execution."""
    command: str = Field(description="Shell command to execute in sandbox")

class OpenClawTool(BaseTool):
    """LangChain tool for OpenClaw execution."""
    
    name: str = "exec_cmd"
    description: str = "Execute a shell command in the secure OpenClaw sandbox."
    args_schema: Type[BaseModel] = ExecCmdInput
    
    def _run(
        self,
        command: str,
        run_manager: Optional[CallbackManagerForToolRun] = None
    ) -> str:
        """Execute command through Tri-State Protocol."""
        
        # Import here to avoid circular dependency
        from .supervisor import audit_action
        
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
            # Check if running in Docker network (default to localhost with host networking)
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
    
    async def _arun(
        self,
        command: str,
        run_manager: Optional[CallbackManagerForToolRun] = None
    ) -> str:
        """Async version (calls sync for now)."""
        return self._run(command, run_manager)

def get_tool():
    """Factory to return a properly named StructuredTool."""
    return StructuredTool.from_function(
        func=OpenClawTool()._run,
        coroutine=OpenClawTool()._arun,
        name="exec_cmd",
        description="Execute a shell command in the secure OpenClaw sandbox.",
        args_schema=ExecCmdInput
    )
