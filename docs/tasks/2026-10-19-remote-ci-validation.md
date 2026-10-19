# CI-002: GitHub push와 원격 CI·동일 ELF HIL 검증

기준: [개발 흐름](../development-workflow.md), [요구사항 계약](../firmware-contract.md), [이전 구현·로컬 검증](2026-10-19-build-ci-hil-artifact.md).

## 요청과 범위

- 사용자 요청: GitHub에 push하고 원격 CI를 실행한 결과 보고.
- 시작 revision: `3cd3d0abc21c5ab735c78587a67f97d79e34ecf1`, 현재 main의 미커밋 문서·빌드·CI 구현을 보존한다.
- 원격: `red-crypto/firmware-study`. 새 작업 브랜치 `codex/ci-artifact-hil`에 커밋·push한다. main에 병합하거나 강제 push하지 않는다.
- 게시 범위: 앞선 요청으로 만든 개발 문서·템플릿, Rust 고정·CI·산출물/HIL 연결 코드와 시험, 작은 검증 요약·기존 디버깅 요약. ELF·로그·개인 장비 설정·자격증명은 제외한다.
- 필요 시 CI 실패를 고치고 같은 브랜치에 후속 커밋한다. 결과·증거 문서는 본 파일과 `hil/evidence/remote-ci-validation.json`에 기록한다.
- 연결: REQ-PIPE-001~003, TEST-CI-001, TEST-CI-HIL-001, TEST-TRACE-001, TEST-HIL-001.

## 수용 기준

| 항목 | 합격 조건 | 상태 |
| --- | --- | --- |
| push | 로컬 커밋과 원격 작업 브랜치 SHA가 일치 | not-run |
| 원격 CI | 특정 commit의 GitHub Actions 작업이 실제 완료·성공하고 로그·시험 결과 확인 | not-run |
| 산출물 | 같은 실행의 ELF·SHA256SUMS·manifest를 다운로드하고 commit·해시·clean 상태 확인 | not-run |
| 로컬 HIL | 다운로드한 ELF를 재빌드·AllowDirty 없이 검증하고 실제 flash SHA·UART·cleanup 연결 | not-run |
| 보고 | 실행 URL·commit·산출물·검증 범위와 실패·수정 사항 기록 | not-run |

## 실행 기록

원격 CI와 로컬 HIL 결과를 실행 후 기록한다. 이전 로컬 빌드의 성공을 이번 원격 실행의 성공으로 대체하지 않는다. 현재 대상은 모터 없는 LED/UART 보드이며 장비 접근은 기존 Agentic HIL MCP 경로만 사용한다.
