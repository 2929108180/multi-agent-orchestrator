# Multi-Agent Orchestrator

[English](./README.md) | [简体中文](./README.zh-CN.md) | 한국어

여러 벤더의 코딩 모델을 하나의 팀처럼 조율하는 로컬 우선 오케스트레이터입니다.  
MAO의 목표는 단일 모델 챗봇을 하나 더 만드는 것이 아니라, 여러 모델, skill, MCP, 승인 정책, 통합 흐름을 하나의 작업 체계로 묶는 것입니다.

## 왜 MAO를 선택하나

- 멀티 벤더 협업
  계획, 프론트엔드, 백엔드, 리뷰를 서로 다른 모델에 맡길 수 있습니다.
- 로컬 우선
  세션, 실행 기록, 승인 큐, skill registry, MCP registry가 로컬에 저장됩니다.
- 능력 계층 통제
  skill, MCP, policy, approval, capability 노출을 MAO가 직접 관리합니다.
- 팀 모드
  모델들을 개별 챗봇이 아니라 하나의 AI 팀으로 운영합니다.
- 검토 가능성과 복구 가능성
  diff를 보고 승인하거나 보류할 수 있으며, 나중에 같은 세션을 다시 이어갈 수 있습니다.

## 핵심 기능

- 멀티 모델 팀 오케스트레이션
  `architect / frontend / backend / reviewer`
- 계층형 메모리
  `session memory / task memory / review memory`
- 세션 복구
  `--resume-latest`, `--session-id`, 대화 중 `/resume`
- 승인 정책
  팀 기본값, 역할별 오버라이드, 모델별 오버라이드
- diff 승인 큐
  `/queue`, `/pick`, `/approve`, `/reject`, `/defer`
- integration worktree
  승인된 변경은 별도 integration 작업공간에 적용
- capability registry
  skill과 MCP를 통합 등록, 조회, 권한 부여
- 직접 연결과 프록시 연결
  공식 API와 `base_url` 기반 중계 경로 모두 지원

## 현재의 특징

### 1. 팀 기반 작업 흐름

기본 흐름은 다음과 같습니다.

1. 사용자가 요구사항을 입력
2. `architect` 가 계획과 공유 계약을 생성
3. `frontend` 와 `backend` 가 병렬로 제안 생성
4. `reviewer` 가 일관성을 검사하고 defect 생성
5. 시스템이 defect를 적절한 역할에 다시 분배
6. 승인 큐에서 변경을 검토
7. 승인된 변경은 integration worktree 로 이동

### 2. 충돌 방지

MAO는 여러 worker가 같은 파일을 마음대로 고치게 두지 않습니다. 현재 포함된 보호 장치는:

- `allowed_paths / restricted_paths`
- shared file 식별
- 충돌 파일 식별
- integration layer 결정을 통한 차단
- 정책 기반 `auto / manual / reject`

### 3. 통합 capability layer

모델이 스스로 “무슨 skill 이 있는지” 추측하게 두지 않고, MAO가 다음을 직접 관리합니다.

- 로컬 발견
- registry 로 가져오기
- 권한 부여
- 역할/모델별 capability 노출

## 자주 쓰는 명령

```powershell
mao chat --mock
mao chat --live --config configs/live.multi-provider.example.yaml

mao skills import-local
mao skills list
mao skills show mcp-builder
mao skills register demo_skill --description "demo skill" --path C:\demo\SKILL.md
mao skills grant demo_skill --role frontend

mao mcp import-local
mao mcp list
mao mcp show mao_mcp
mao mcp register demo_mcp --transport streamable-http --url http://localhost:8123/mcp
mao mcp grant demo_mcp --role reviewer

mao policy show
```

## 채팅 모드

`mao chat` 는 현재 다음을 지원합니다.

- 세션 메모리와 복구
- 연속 대화 컨텍스트 주입
- 실시간 작업 단계 표시
- skill / MCP 조회
- 승인 큐와 diff 리뷰
- integration worktree 적용

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
- `/skill-import-local`
- `/mcp-import-local`
- `/grant-skill role <role> <skill>`
- `/grant-mcp role <role> <server>`
- `/register-skill <name> <path> <description>`
- `/register-mcp <name> <transport> <command|url> [args...]`

## Capability Registry

정식 실행에서는 MAO 자체 registry를 우선 사용합니다.

- `runtime/registry/skills.json`
- `runtime/registry/mcp_servers.json`

로컬 스캔은 이제 “가져오기 소스”일 뿐이며, 공식 실행 시의 단일 진실 원천은 registry 입니다.

즉:

- 기존 로컬 skill / MCP 를 가져올 수 있고
- 새 skill / MCP 를 수동 등록할 수 있으며
- 역할이나 모델 기준으로 접근 권한을 배분할 수 있습니다

## Live Provider 지원

MAO는 두 가지 연결 방식을 지원합니다.

- 공식 API 직접 연결
- `base_url` 기반 프록시 / 호환 게이트웨이 연결

통합 provider config 에서 다음을 설정할 수 있습니다.

- `api_key_env`
- `base_url`
- `extra_headers`
- approval policy

## 어떤 사용자에게 적합한가

- 여러 모델을 하나의 개발 팀처럼 운영하고 싶은 개인 개발자
- 단일 모델 한계를 낮추고 싶은 팀
- 로컬 감사, 승인, 복구, capability governance가 필요한 엔지니어링 팀
- skill, MCP, approval, session 을 통합적으로 관리하고 싶은 AI 엔지니어

## 현재 단계

MAO는 이미 “진지하게 시험해볼 수 있는” 수준에 도달했습니다.  
현재 특히 잘 맞는 용도는 다음과 같습니다.

- 요구사항 분해
- 아키텍처 설계
- 프론트엔드/백엔드 계약 정렬
- 리뷰 및 수정 루프
- 승인과 integration 관리

앞으로 더 강화할 부분:

- 더 세밀한 patch / merge
- 더 강한 shared file integration actor
- 대상 브랜치까지의 명확한 병합 흐름
- 더 보기 좋은 승인 UI
- skill / MCP 의 자연어 기반 설치와 등록 경험

## 개발과 검증

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e .[dev]
pytest
```

## 관련 문서

- [README.md](./README.md)
- [README.zh-CN.md](./README.zh-CN.md)
- [docs/architecture-baseline.md](./docs/architecture-baseline.md)
- [docs/progress.md](./docs/progress.md)
- [docs/team-mode.md](./docs/team-mode.md)
