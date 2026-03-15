from __future__ import annotations

import json
import os
from uuid import uuid4
from dataclasses import dataclass
from urllib.parse import urljoin

import httpx
from litellm import completion, responses

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
        if provider.profile == "packy_openai_responses":
            return self._packy_openai_responses(provider=provider, prompt=prompt)
        if provider.profile == "packy_gemini_generate_content":
            return self._packy_gemini_generate_content(provider=provider, prompt=prompt)
        if provider.api_style == "responses":
            return self._litellm_responses(provider=provider, prompt=prompt)
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
        if provider.extra_headers:
            extra_kwargs["extra_headers"] = provider.extra_headers
        if provider.extra_body:
            extra_kwargs["extra_body"] = provider.extra_body

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

    def _litellm_responses(self, provider: ProviderConfig, prompt: str) -> str:
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
        response_headers = dict(provider.extra_headers)
        if "conversation_id" in response_headers and response_headers["conversation_id"] == "__UUID__":
            response_headers["conversation_id"] = str(uuid4())
        if "session_id" in response_headers and response_headers["session_id"] == "__UUID__":
            response_headers["session_id"] = str(uuid4())
        if response_headers:
            extra_kwargs["extra_headers"] = response_headers
        if provider.extra_body:
            extra_kwargs["extra_body"] = provider.extra_body

        response = responses(
            model=provider.model,
            input=[
                {
                    "type": "message",
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": prompt,
                        }
                    ],
                }
            ],
            temperature=provider.temperature,
            tool_choice="auto",
            include=["reasoning.encrypted_content"],
            text={"verbosity": "low"},
            reasoning={"effort": "high", "summary": "auto"},
            store=False,
            parallel_tool_calls=False,
            instructions="",
            **extra_kwargs,
        )
        output_text = getattr(response, "output_text", None)
        if isinstance(output_text, str) and output_text:
            return output_text
        dumped = response.model_dump() if hasattr(response, "model_dump") else response
        if isinstance(dumped, dict):
            maybe = dumped.get("output_text")
            if isinstance(maybe, str) and maybe:
                return maybe
        return str(response)

    def _packy_openai_responses(self, provider: ProviderConfig, prompt: str) -> str:
        api_key = self._read_required_api_key(provider)
        base_url = _normalize_base_url(provider.base_url or "https://api-slb.packyapi.com/v1")
        url = urljoin(base_url.rstrip("/") + "/", "responses")

        headers = {
            "authorization": f"Bearer {api_key}",
            "content-type": "application/json",
            "accept": "text/event-stream",
            "version": "0.58.0",
            "conversation_id": str(uuid4()),
            "session_id": str(uuid4()),
            "prompt_cache_key": str(uuid4()),
            "user-agent": "mao/0.1",
        }
        headers.update(provider.extra_headers)
        headers = _materialize_uuid_placeholders(headers)

        body = {
            "stream": True,
            "tool_choice": "auto",
            "include": ["reasoning.encrypted_content"],
            "input": [
                {
                    "type": "message",
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": prompt,
                        }
                    ],
                }
            ],
            "text": {"verbosity": "low"},
            "reasoning": {"effort": "high", "summary": "auto"},
            "instructions": "",
            "model": provider.model,
            "store": False,
            "parallel_tool_calls": False,
        }
        body.update(provider.extra_body)

        with httpx.Client(timeout=60.0, follow_redirects=True) as client:
            response = client.post(url, headers=headers, json=body)
            response.raise_for_status()
        return _extract_packy_responses_output(response.text)

    def _packy_gemini_generate_content(self, provider: ProviderConfig, prompt: str) -> str:
        api_key = self._read_required_api_key(provider)
        base_url = _normalize_base_url(provider.base_url or "https://api-slb.packyapi.com")
        path = f"/v1beta/models/{provider.model}:generateContent"
        url = urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))

        headers = {
            "authorization": f"Bearer {api_key}",
            "content-type": "application/json",
        }
        headers.update(provider.extra_headers)
        headers = _materialize_uuid_placeholders(headers)

        body = {
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": prompt}],
                }
            ],
            "generationConfig": {
                "temperature": provider.temperature,
            },
        }
        body.update(provider.extra_body)

        with httpx.Client(timeout=60.0, follow_redirects=True) as client:
            response = client.post(url, headers=headers, json=body)
            response.raise_for_status()
        payload = response.json()
        candidates = payload.get("candidates", [])
        if candidates:
            parts = candidates[0].get("content", {}).get("parts", [])
            if parts:
                text = parts[0].get("text")
                if isinstance(text, str):
                    return text
        return json.dumps(payload, ensure_ascii=False)

    def _read_required_api_key(self, provider: ProviderConfig) -> str:
        effective_api_key_env = provider.effective_api_key_env
        if not effective_api_key_env:
            raise RuntimeError(f"No API key env configured for model `{provider.model}`.")
        api_key = os.getenv(effective_api_key_env)
        if not api_key:
            raise RuntimeError(
                f"Missing environment variable `{effective_api_key_env}` for model `{provider.model}`."
            )
        return api_key

    def _mock_response(self, role: str, prompt: str) -> str:
        if role == "architect":
            if "TEAM_MODE:" in prompt and "routing assistant" in prompt:
                lowered = prompt.lower()
                if any(token in lowered for token in ["frontend", "backend", "react", "fastapi", "项目", "系统", "task", "build", "create"]):
                    return "TEAM_MODE: on"
                return "TEAM_MODE: off"
            return (
                "Delivery slice: establish the first user journey, shared API shape, and review points. "
                "Critical assumption: both workers must align on endpoint naming and payload fields."
            )
        if role == "frontend":
            if "DEFECT:" in prompt:
                return (
                    "Frontend proposal revised:\n"
                    "- Use `/api/tasks` for list and create.\n"
                    "- Render dashboard, loading state, empty state, and failure banner.\n"
                    "- Request fields: `title`, `status`, `assignee`.\n"
                    "- Response fields: `id`, `title`, `status`, `assignee`, `updatedAt`.\n"
                    "FILE_TARGETS:\n"
                    "- frontend/dashboard.tsx\n"
                    "- ui/task_list.tsx"
                )
            return (
                "Frontend proposal:\n"
                "- Build a dashboard page with task list and create form.\n"
                "- Use `/api/task-items` for fetching and creating tasks.\n"
                "- Request fields: `title`, `status`, `assignee`.\n"
                "- Response fields: `id`, `title`, `status`, `assignee`, `updatedAt`.\n"
                "- Include loading, empty, and error states.\n"
                "FILE_TARGETS:\n"
                "- frontend/dashboard.tsx\n"
                "- ui/task_list.tsx"
            )
        if role == "backend":
            if "DEFECT:" in prompt:
                return (
                    "Backend proposal revised:\n"
                    "- Expose `GET /api/tasks` and `POST /api/tasks`.\n"
                    "- Accept `title`, `status`, `assignee`.\n"
                    "- Return `id`, `title`, `status`, `assignee`, `updatedAt`.\n"
                    "- Validate missing titles and return explicit error payloads.\n"
                    "FILE_TARGETS:\n"
                    "- backend/tasks_api.py\n"
                    "- api/tasks_routes.py"
                )
            return (
                "Backend proposal:\n"
                "- Expose `GET /api/tasks` and `POST /api/tasks`.\n"
                "- Accept `title`, `status`, `assignee`.\n"
                "- Return `id`, `title`, `status`, `assignee`, `updatedAt`.\n"
                "- Validate missing titles and return explicit error payloads.\n"
                "FILE_TARGETS:\n"
                "- backend/tasks_api.py\n"
                "- api/tasks_routes.py"
            )
        if role == "integration":
            # Minimal structured integration report for mock workflows.
            if "/api/task-items" in prompt and "GET /api/tasks" in prompt:
                return "\n".join(
                    [
                        "INTEGRATION_REPORT:",
                        "ROUND: 0",
                        "STATUS: needs_changes",
                        "SUMMARY: Frontend and backend endpoints are inconsistent.",
                        "",
                        "KEY_FINDINGS:",
                        "- Frontend calls /api/task-items but backend exposes /api/tasks.",
                        "",
                        "BINDING:",
                        "ID: tasks-api",
                        "FRONTEND: GET/POST /api/task-items",
                        "BACKEND: GET/POST /api/tasks",
                        "REQUEST_FIELDS: title,status,assignee",
                        "RESPONSE_FIELDS: id,title,status,assignee,updatedAt",
                        "MATCH: no",
                        "NOTES: Align frontend route to /api/tasks.",
                        "",
                        "ISSUE:",
                        "ID: api-path-mismatch",
                        "OWNER: frontend",
                        "SEVERITY: high",
                        "TITLE: API path mismatch",
                        "SUMMARY: Frontend uses /api/task-items while backend uses /api/tasks.",
                        "ACTION: Update frontend to call /api/tasks.",
                        "",
                        "OPEN_QUESTIONS:",
                        "- None",
                        "",
                        "FILE_TARGETS:",
                        "- shared-contracts/tasks.schema.json",
                    ]
                )
            return "\n".join(
                [
                    "INTEGRATION_REPORT:",
                    "ROUND: 0",
                    "STATUS: ok",
                    "SUMMARY: Frontend and backend are aligned on API shape.",
                    "",
                    "KEY_FINDINGS:",
                    "- Endpoint names and request/response fields match.",
                    "",
                    "BINDING:",
                    "ID: tasks-api",
                    "FRONTEND: GET/POST /api/tasks",
                    "BACKEND: GET/POST /api/tasks",
                    "REQUEST_FIELDS: title,status,assignee",
                    "RESPONSE_FIELDS: id,title,status,assignee,updatedAt",
                    "MATCH: yes",
                    "NOTES: Keep this contract stable.",
                    "",
                    "OPEN_QUESTIONS:",
                    "- None",
                    "",
                    "FILE_TARGETS:",
                    "- shared-contracts/tasks.schema.json",
                ]
            )

        if role == "reviewer":
            # Reviewer should primarily rely on the Integration report.
            if "Integration report (PRIMARY):" in prompt and "MATCH: no" in prompt:
                return "\n".join(
                    [
                        "APPROVED: no",
                        "SUMMARY: Integration reports endpoint mismatch between FE and BE.",
                        "DEFECT:",
                        "ID: api-path-mismatch",
                        "OWNER: frontend",
                        "SEVERITY: high",
                        "TITLE: API path mismatch",
                        "SUMMARY: Integration reports frontend uses /api/task-items while backend exposes /api/tasks.",
                        "ACTION: Change the frontend integration to /api/tasks.",
                    ]
                )
            return "\n".join(
                [
                    "APPROVED: yes",
                    "SUMMARY: Integration indicates FE/BE contract is aligned.",
                    "DEFECT:",
                    "ID: no-blocking-issues",
                    "OWNER: shared",
                    "SEVERITY: low",
                    "TITLE: No blocking issues",
                    "SUMMARY: No blocking issues found in this round.",
                    "ACTION: Keep the shared contract stable.",
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


def _normalize_base_url(base_url: str) -> str:
    if base_url.startswith("http://") or base_url.startswith("https://"):
        return base_url
    return f"https://{base_url}"


def _materialize_uuid_placeholders(headers: dict[str, str]) -> dict[str, str]:
    rendered = {}
    for key, value in headers.items():
        rendered[key] = str(uuid4()) if value == "__UUID__" else value
    return rendered


def _extract_packy_responses_output(raw_text: str) -> str:
    chunks: list[str] = []
    for line in raw_text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("data:"):
            continue
        payload_text = stripped[len("data:") :].strip()
        if payload_text in {"[DONE]", ""}:
            continue
        try:
            payload = json.loads(payload_text)
        except json.JSONDecodeError:
            continue
        payload_type = payload.get("type", "")
        if payload_type == "response.output_text.delta":
            delta = payload.get("delta")
            if isinstance(delta, str):
                chunks.append(delta)
        elif payload_type == "response.completed":
            break
        else:
            maybe = payload.get("output_text")
            if isinstance(maybe, str):
                chunks.append(maybe)
    if chunks:
        return "".join(chunks)
    return raw_text
