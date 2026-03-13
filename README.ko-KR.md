# Multi-Agent Orchestrator

여러 벤더의 코딩 에이전트를 조율하는 로컬 우선 오케스트레이터입니다.

## 목표

- 제품 또는 개발 요구사항 수신
- 실행 계획과 공유 계약 생성
- 프론트엔드, 백엔드, 리뷰 작업을 서로 다른 모델에 분배
- 리뷰, 수정, 승인, 통합 흐름 실행
- 실행 기록, 세션, capability registry 저장

## 자주 쓰는 명령

```powershell
mao chat --mock
mao chat --live --config configs/live.multi-provider.example.yaml
mao skills import-local
mao mcp import-local
mao skills list
mao mcp list
mao policy show
```

## 채팅 모드

`mao chat` 는 현재 다음을 지원합니다.

- 세션 메모리와 복구
- 승인 큐와 diff 리뷰
- skill / MCP registry 조회
- 팀 모드 컨텍스트

주요 채팅 명령:

- `/history`
- `/context`
- `/skills`
- `/mcp`
- `/resume`
- `/queue`
- `/review`
- `/approve`
- `/reject`
- `/defer`

## Capability Registry

정식 실행 시에는 MAO의 자체 registry를 우선 사용합니다.

- `runtime/registry/skills.json`
- `runtime/registry/mcp_servers.json`

로컬 skill / MCP는 먼저 registry로 가져온 뒤 사용합니다.

## 언어 버전

- English: [README.md](E:\Ai\multi-agent-orchestrator\README.md)
- 简体中文: [README.zh-CN.md](E:\Ai\multi-agent-orchestrator\README.zh-CN.md)
