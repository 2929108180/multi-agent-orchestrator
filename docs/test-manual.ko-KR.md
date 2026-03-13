# 테스트 매뉴얼

[English](./test-manual.md) | [简体中文](./test-manual.zh-CN.md) | 한국어

## 목적

이 문서는 MAO의 전체 기능 흐름을 검증하기 위한 테스트 매뉴얼입니다.

포함 범위:

- 기본 환경
- mock workflow
- 세션 메모리
- 승인 큐
- skill / MCP registry
- merge candidate
- live provider 사전 점검

## 권장 테스트 순서

다음 순서로 테스트하는 것을 권장합니다.

1. 기본 환경
2. mock workflow
3. 세션 메모리와 복구
4. 승인 큐
5. registry 관리
6. merge candidate
7. live provider preflight

## 1. 기본 환경

```powershell
cd E:\Ai\multi-agent-orchestrator
mao --help
mao status
mao doctor --mock
```

예상 결과:

- 명령이 정상적으로 표시됨
- `status` 에 핵심 기능이 구현됨으로 표시됨
- `doctor` 에서 mock provider 가 ready 로 표시됨

## 2. Mock Workflow

```powershell
mao chat --mock
```

입력:

```text
작업 목록과 상태 필터가 있는 작업 관리기를 만들어줘
/exit
```

예상 결과:

- workflow 단계 메시지가 표시됨
- run 디렉터리가 생성됨
- summary 가 출력됨
- approval queue 개수가 표시됨

## 3. 세션 메모리와 복구

첫 번째 세션:

```powershell
mao chat --mock
```

입력:

```text
작업 관리기를 만들어줘
/exit
```

최근 세션 복구:

```powershell
mao chat --mock --resume-latest
```

이후 입력:

```text
/history
/context
/last
/exit
```

예상 결과:

- `/history` 에 최소 한 개 이상의 turn 이 보임
- `/context` 에 요약된 컨텍스트가 보임
- `/last` 에 최근 run 경로가 보임

주의:

- 세션 복구는 이전 터미널 출력 전체를 다시 재생하지 않음
- 복구되는 것은 상태이지, 터미널 스크롤 버퍼가 아님

## 4. 승인 큐

```powershell
mao chat --mock
```

입력:

```text
작업 관리기를 만들어줘
/queue
/pick 1
d
/queue
/pick 2
y
/merge
/exit
```

예상 결과:

- `/queue` 가 승인 대기 항목을 표시함
- `/pick` 이 diff 를 표시함
- `d` 로 현재 항목을 보류 가능
- `y` 로 현재 항목을 승인 가능
- `/merge` 로 merge candidate 를 확인 가능

## 5. Registry 관리

```powershell
mao skills import-local
mao skills list
mao skills show mcp-builder

mao mcp import-local
mao mcp list
mao mcp show mao_mcp

mao policy show
```

예상 결과:

- 로컬 skill 이 registry 로 가져와짐
- 로컬 MCP 가 registry 로 가져와짐
- `list/show` 가 읽기 쉬운 형태로 출력됨
- `policy show` 에 승인 정책이 표시됨

## 6. 대화 중 capability 관리

```powershell
mao chat --mock
```

입력:

```text
/skill-import-local
/skills
/register-skill demo_skill C:\demo\SKILL.md demo skill description
/grant-skill role frontend demo_skill
/mcp-import-local
/mcp
/register-mcp demo_http streamable-http http://localhost:8123/mcp
/grant-mcp role reviewer demo_http
/exit
```

예상 결과:

- import 명령이 registry 를 갱신함
- `/skills` 가 skill 목록을 보여줌
- `/mcp` 가 MCP server 목록을 보여줌
- `grant` 명령이 접근 권한을 갱신함

## 7. Merge Candidate

최소 하나 이상의 변경을 승인한 뒤 실행:

```powershell
mao merge list
```

예상 결과:

- merge candidate 목록이 보임
- status 와 shared 여부가 표시됨

## 8. Live Provider Preflight

먼저 live 설정을 준비한 뒤:

```powershell
mao validate --config configs/live.multi-provider.example.yaml
```

예상 결과:

- key 가 없으면 누락된 환경변수를 표시
- key 가 올바르면 preflight 통과

그 다음:

```powershell
mao chat --live --config configs/live.multi-provider.example.yaml
```

예상 결과:

- 필요한 key 가 모두 있을 때만 live chat 이 시작됨

## 9. 전체 회귀

```powershell
pytest
```

예상 결과:

- 모든 테스트 통과

## 트러블슈팅

문제가 생기면 우선 다음을 수집하세요.

- 실행한 명령
- 터미널 출력
- 최신 run 디렉터리
- `run.json`
- `summary.md`
- `integration.json`
- `integration.md`

세션 복구 문제라면 추가로:

- `/history`
- `/context`
- `/queue`

를 함께 확인하세요.
