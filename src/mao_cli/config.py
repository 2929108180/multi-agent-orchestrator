from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field


class ProviderConfig(BaseModel):
    adapter: str = Field(default="mock")
    model: str
    api_key_env: str | None = None
    base_url: str | None = None
    temperature: float = Field(default=0.2, ge=0.0, le=2.0)


class WorkflowConfig(BaseModel):
    max_repair_rounds: int = Field(default=1, ge=0, le=5)


class AppConfig(BaseModel):
    version: int = 1
    project_name: str = "multi-agent-orchestrator"
    runtime_root: str = "runtime"
    artifacts_root: str = "artifacts"
    workflow: WorkflowConfig = Field(default_factory=WorkflowConfig)
    providers: dict[str, ProviderConfig]


def load_config(path: Path) -> AppConfig:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return AppConfig.model_validate(data)
