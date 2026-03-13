from __future__ import annotations

import os
from dataclasses import dataclass

from litellm import completion

from mao_cli.config import AppConfig, ProviderConfig


@dataclass
class ProviderHealth:
    role: str
    adapter: str
    model: str
    mode: str
    api_key_env: str | None
    api_key_present: bool
    ready: bool
    note: str


class ModelGateway:
    def __init__(self, config: AppConfig, force_mock: bool = False) -> None:
        self.config = config
        self.force_mock = force_mock

    def complete(self, role: str, prompt: str) -> str:
        provider = self.config.providers[role]
        if self.force_mock or provider.adapter == "mock":
            return self._mock_response(role=role, prompt=prompt)
        return self._litellm_complete(provider=provider, prompt=prompt)

    def _litellm_complete(self, provider: ProviderConfig, prompt: str) -> str:
        extra_kwargs = {}
        effective_api_key_env = provider.effective_api_key_env
        if effective_api_key_env:
            api_key = os.getenv(effective_api_key_env)
            if not api_key:
                raise RuntimeError(
                    f"Missing environment variable `{effective_api_key_env}` for model `{provider.model}`."
                )
            extra_kwargs["api_key"] = api_key
        if provider.base_url:
            extra_kwargs["base_url"] = provider.base_url

        response = completion(
            model=provider.model,
            temperature=provider.temperature,
            messages=[
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
            **extra_kwargs,
        )
        message = response["choices"][0]["message"]["content"]
        return message if isinstance(message, str) else str(message)

    def _mock_response(self, role: str, prompt: str) -> str:
        if role == "architect":
            return (
                "Delivery slice: establish the first user journey, shared API shape, and review points. "
                "Critical assumption: both workers must align on endpoint naming and payload fields."
            )
        if role == "frontend":
            if "Reviewer feedback:" in prompt and "NONE" not in prompt:
                return (
                    "Frontend proposal revised:\n"
                    "- Use `/api/tasks` for list and create.\n"
                    "- Render dashboard, loading state, empty state, and failure banner.\n"
                    "- Request fields: `title`, `status`, `assignee`.\n"
                    "- Response fields: `id`, `title`, `status`, `assignee`, `updatedAt`."
                )
            return (
                "Frontend proposal:\n"
                "- Build a dashboard page with task list and create form.\n"
                "- Use `/api/task-items` for fetching and creating tasks.\n"
                "- Request fields: `title`, `status`, `assignee`.\n"
                "- Response fields: `id`, `title`, `status`, `assignee`, `updatedAt`.\n"
                "- Include loading, empty, and error states."
            )
        if role == "backend":
            if "Reviewer feedback:" in prompt and "NONE" not in prompt:
                return (
                    "Backend proposal revised:\n"
                    "- Expose `GET /api/tasks` and `POST /api/tasks`.\n"
                    "- Accept `title`, `status`, `assignee`.\n"
                    "- Return `id`, `title`, `status`, `assignee`, `updatedAt`.\n"
                    "- Validate missing titles and return explicit error payloads."
                )
            return (
                "Backend proposal:\n"
                "- Expose `GET /api/tasks` and `POST /api/tasks`.\n"
                "- Accept `title`, `status`, `assignee`.\n"
                "- Return `id`, `title`, `status`, `assignee`, `updatedAt`.\n"
                "- Validate missing titles and return explicit error payloads."
            )
        if role == "reviewer":
            if "/api/task-items" in prompt and "GET /api/tasks" in prompt:
                return "\n".join(
                    [
                        "APPROVED: no",
                        "SUMMARY: Frontend and backend endpoint names are inconsistent.",
                        "FINDINGS:",
                        "- Frontend uses `/api/task-items` while backend exposes `/api/tasks`.",
                        "FRONTEND_ACTION: Change the frontend integration to `/api/tasks`.",
                        "BACKEND_ACTION: NONE",
                    ]
                )
            return "\n".join(
                [
                    "APPROVED: yes",
                    "SUMMARY: Frontend and backend are aligned on API shape and states.",
                    "FINDINGS:",
                    "- No blocking issues found in this round.",
                    "FRONTEND_ACTION: NONE",
                    "BACKEND_ACTION: NONE",
                ]
            )
        return f"Unhandled mock role `{role}`. Prompt was: {prompt}"


def inspect_providers(config: AppConfig, force_mock: bool = False) -> list[ProviderHealth]:
    health_rows: list[ProviderHealth] = []
    for role, provider in config.providers.items():
        mode = "mock" if force_mock or provider.adapter == "mock" else "live"
        effective_api_key_env = provider.effective_api_key_env
        api_key_present = bool(effective_api_key_env and os.getenv(effective_api_key_env))

        if mode == "mock":
            ready = True
            note = "Mock mode is ready."
        elif not effective_api_key_env:
            ready = False
            note = "No API key env configured for this live provider."
        elif not api_key_present:
            ready = False
            note = f"Missing environment variable `{effective_api_key_env}`."
        else:
            ready = True
            note = f"Environment variable `{effective_api_key_env}` is available."

        health_rows.append(
            ProviderHealth(
                role=role,
                adapter=provider.adapter,
                model=provider.model,
                mode=mode,
                api_key_env=effective_api_key_env,
                api_key_present=api_key_present,
                ready=ready,
                note=note,
            )
        )
    return health_rows
