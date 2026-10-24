"""API request/response schemas (Pydantic v2)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field

# ----------------------------------------------------------------- auth


class RegisterRequest(BaseModel):
    email: EmailStr
    name: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    name: str
    created_at: datetime


# ---------------------------------------------------------------- agents


class AgentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = ""
    system_prompt: str = ""
    model_provider: str
    model_name: str = Field(min_length=1, max_length=120)
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_output_tokens: int | None = Field(default=None, ge=1, le=200_000)
    enabled_tools: list[str] = Field(default_factory=list)
    memory_enabled: bool = False
    knowledge_base_ids: list[str] = Field(default_factory=list)


class AgentUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = None
    system_prompt: str | None = None
    model_provider: str | None = None
    model_name: str | None = Field(default=None, min_length=1, max_length=120)
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    max_output_tokens: int | None = Field(default=None, ge=1, le=200_000)
    enabled_tools: list[str] | None = None
    memory_enabled: bool | None = None
    knowledge_base_ids: list[str] | None = None


class AgentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str
    system_prompt: str
    model_provider: str
    model_name: str
    temperature: float
    max_output_tokens: int | None
    enabled_tools: list[str]
    memory_enabled: bool
    knowledge_base_ids: list[str]
    created_at: datetime
    updated_at: datetime


# --------------------------------------------------------- conversations


class ConversationCreate(BaseModel):
    agent_id: uuid.UUID
    title: str | None = Field(default=None, max_length=200)


class ConversationUpdate(BaseModel):
    title: str = Field(min_length=1, max_length=200)


class ToolCallOut(BaseModel):
    id: str | None = None
    name: str | None = None
    args: dict[str, Any] | None = None


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    run_id: uuid.UUID | None
    role: str
    content: str
    tool_calls: list[ToolCallOut] | None = None
    tool_call_id: str | None = None
    name: str | None = None
    created_at: datetime


class ConversationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    agent_id: uuid.UUID
    title: str
    created_at: datetime
    updated_at: datetime


class ConversationDetail(ConversationOut):
    messages: list[MessageOut] = Field(default_factory=list)


class SendMessageRequest(BaseModel):
    content: str = Field(min_length=1, max_length=32_000)


# ----------------------------------------------------------------- runs


class UsageOut(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    model_calls: int = 0


class RunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    conversation_id: uuid.UUID
    agent_id: uuid.UUID
    status: str
    error_code: str | None
    error_message: str | None
    input_text: str
    usage: dict | None
    started_at: datetime
    finished_at: datetime | None


class RunEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    event_type: str
    payload: dict
    created_at: datetime


class RunDetail(RunOut):
    events: list[RunEventOut] = Field(default_factory=list)


# ------------------------------------------------------- meta / tools


class ToolOut(BaseModel):
    name: str
    description: str
    category: str


class ProviderModelInfo(BaseModel):
    id: str
    label: str
    configured: bool
    models: list[str]


class ErrorOut(BaseModel):
    code: str
    message: str
    detail: str | None = None


# ---------------------------------------------------------------- memories


class MemoryCreate(BaseModel):
    content: str = Field(min_length=1, max_length=4000)
    category: str = Field(default="fact", pattern="^(preference|project|fact)$")
    agent_id: uuid.UUID | None = None


class MemoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    agent_id: uuid.UUID | None
    category: str
    content: str
    source: str
    conversation_id: uuid.UUID | None
    created_at: datetime
