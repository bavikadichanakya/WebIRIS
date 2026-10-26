"""
Project IRIS - Tool Schemas and Action Plan Definitions
Provides structured schemas and validation contracts for model-generated actions.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ToolParameter(BaseModel):
    """Specification of a single tool parameter."""
    name: str
    type: str  # 'string', 'boolean', 'integer', 'number'
    description: str
    required: bool = True
    default: Optional[Any] = None


class ToolDefinition(BaseModel):
    """Metadata specification for a registered automation tool."""
    name: str
    description: str
    parameters: List[ToolParameter] = Field(default_factory=list)
    requires_confirmation: bool = False
    permission_key: str

    def to_schema_dict(self) -> Dict[str, Any]:
        """Convert tool metadata to schema format for LLM prompting."""
        params = {}
        for p in self.parameters:
            params[p.name] = {
                "type": p.type,
                "description": p.description,
                "required": p.required,
            }
        return {
            "name": self.name,
            "description": self.description,
            "parameters": params,
            "requires_confirmation": self.requires_confirmation,
        }


class PlanOutput(BaseModel):
    """Constrained JSON schema produced by SmolLM3-3B."""
    thought: Optional[str] = Field(
        default="",
        description="Brief internal reasoning step"
    )
    intent: str = Field(
        description="The identified operation or tool name"
    )
    arguments: Dict[str, Any] = Field(
        default_factory=dict,
        description="Arguments strictly matching the selected tool's parameter schema"
    )
    response: str = Field(
        description="Concise natural speech response to be spoken to the user"
    )

    @property
    def spoken_response(self) -> str:
        return self.response

    @property
    def tool_name(self) -> str:
        return self.intent


class ActionResult(BaseModel):
    """Result of executing an automation tool."""
    success: bool
    tool_name: str
    message: str
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
