from __future__ import annotations

from pathlib import Path
from typing import Literal
from typing import Any

import yaml
from pydantic import BaseModel, Field, model_validator

REQUIRED_PROVIDER_ROLES = ("architect", "frontend", "backend", "integration", "reviewer")
ApprovalMode = Literal["auto", "manual", "reject"]
APIStyle = Literal["chat_completions", "responses", "messages", "generate_content"]
DEFAULT_API_KEY_ENVS = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
}


class ProviderConfig(BaseModel):
    adapter: str = Field(default="mock")
    profile: str = ""
    model: str
    api_key_env: str | None = None
    base_url: str | None = None
    temperature: float = Field(default=0.2, ge=0.0, le=2.0)
    extra_headers: dict[str, str] = Field(default_factory=dict)
    api_style: APIStyle = "chat_completions"
    extra_body: dict[str, Any] = Field(default_factory=dict)

    @property
    def uses_live_provider(self) -> bool:
        return self.adapter != "mock"

    @property
    def effective_api_key_env(self) -> str | None:
        if self.api_key_env:
            return self.api_key_env
        return DEFAULT_API_KEY_ENVS.get(self.adapter)


class WorkflowConfig(BaseModel):
    max_repair_rounds: int = Field(default=1, ge=0, le=5)


class ApprovalRule(BaseModel):
    mode: ApprovalMode = "manual"


class ApprovalConfig(BaseModel):
    default_mode: ApprovalMode = "manual"
    shared_path_mode: ApprovalMode = "manual"
    conflict_mode: ApprovalMode = "reject"
    role_overrides: dict[str, ApprovalRule] = Field(default_factory=dict)
    provider_overrides: dict[str, ApprovalRule] = Field(default_factory=dict)

    def resolve_mode(self, *, role: str, model: str) -> tuple[ApprovalMode, str]:
        if model in self.provider_overrides:
            return self.provider_overrides[model].mode, f"provider:{model}"
        if role in self.role_overrides:
            return self.role_overrides[role].mode, f"role:{role}"
        return self.default_mode, "default"


class AppConfig(BaseModel):
    version: int = 1
    project_name: str = "multi-agent-orchestrator"
    runtime_root: str = "runtime"
    artifacts_root: str = "artifacts"
    workflow: WorkflowConfig = Field(default_factory=WorkflowConfig)
    approval: ApprovalConfig = Field(default_factory=ApprovalConfig)
    providers: dict[str, ProviderConfig]

    @model_validator(mode="after")
    def validate_required_roles(self) -> "AppConfig":
        if "integration" not in self.providers and "reviewer" in self.providers:
            self.providers["integration"] = self.providers["reviewer"].model_copy(deep=True)
        missing_roles = [role for role in REQUIRED_PROVIDER_ROLES if role not in self.providers]
        if missing_roles:
            missing = ", ".join(missing_roles)
            raise ValueError(f"Config is missing required provider roles: {missing}")
        return self


def load_config(path: Path) -> AppConfig:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return AppConfig.model_validate(data)
