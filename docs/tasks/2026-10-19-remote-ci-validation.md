# CI-002: GitHub push와 원격 CI·동일 ELF HIL 검증

기준: [개발 흐름](../development-workflow.md), [요구사항 계약](../firmware-contract.md), [이전 구현·로컬 검증](2026-10-19-build-ci-hil-artifact.md).

## 요청과 범위

- 사용자 요청: GitHub에 push하고 원격 CI를 실행한 결과 보고.
- 시작 revision: `3cd3d0abc21c5ab735c78587a67f97d79e34ecf1`, 현재 main의 미커밋 문서·빌드·CI 구현을 보존한다.
- 원격: `red-crypto/firmware-study`. 새 작업 브랜치 `codex/ci-artifact-hil`에 커밋·push한다. main에 병합하거나 강제 push하지 않는다.
- 게시 범위: 앞선 요청으로 만든 개발 문서·템플릿, Rust 고정·CI·산출물/HIL 연결 코드와 시험, 작은 검증 요약·기존 디버깅 요약. ELF·로그·개인 장비 설정·자격증명은 제외한다.
- 필요 시 CI 실패를 고치고 같은 브랜치에 후속 커밋한다. 결과·증거 문서는 본 파일과 `hil/evidence/remote-ci-validation.json`에 기록한다.
- 연결: REQ-PIPE-001~003, TEST-CI-001, TEST-CI-HIL-001, TEST-TRACE-001, TEST-HIL-001.
- 상태: done(원격 정상 CI와 동일 산출물의 실제 HIL 검증 완료).

## 수용 기준

| 항목 | 합격 조건 | 상태 |
| --- | --- | --- |
| push | 로컬 커밋과 원격 작업 브랜치 SHA가 일치 | pass: b4397b5 |
| 원격 CI | 특정 commit의 GitHub Actions 작업이 실제 완료·성공하고 로그·시험 결과 확인 | pass: run 39211945467 |
| 산출물 | 같은 실행의 ELF·SHA256SUMS·manifest를 다운로드하고 commit·해시·clean 상태 확인 | pass: artifact 12166944970 |
| 로컬 HIL | 다운로드한 ELF를 재빌드·AllowDirty 없이 검증하고 실제 flash SHA·UART·cleanup 연결 | pass: run-8cef31d187299fb9 |
| 보고 | 실행 URL·commit·산출물·검증 범위와 실패·수정 사항 기록 | pass: 아래 요약과 JSON |

## 실행 기록

1. `b4397b5a7b6c52a1f46b7c17f63a5300f67f98c7`을 작업 브랜치에 커밋·push했다. main에 병합하지 않았다.
2. [GitHub Actions run 39211945467](https://github.com/red-crypto/firmware-study/actions/runs/39211945467)이 첫 시도에서 성공했다. Rust/Cargo 1.98.1, 잠긴 STM32 Debug 빌드, 시험 35개 모두 통과(제외 0개), 산출물 3개 업로드를 확인했다. 구현 수정·실패 재실행은 없었다.
3. 같은 실행의 artifact 12166944970을 다운로드했다. GitHub metadata의 ZIP SHA와 CI 로그의 ELF SHA를 별도로 대조하고 manifest의 commit·clean 상태를 확인했다.
4. 다운로드한 ELF를 재빌드·AllowDirty 없이 로컬 MCP로 검증했다. 실제 flash SHA가 CI ELF와 같고 읽기 검증·5초 내 `Hello World` 13바이트·UART 정리가 성공했다.

검증 ELF SHA256은 `f5b0c055cccbb43828032543764ec08a631d3a4743c0efffa0c1f165a2650659`다. 상세 결과는 [remote-ci-validation.json](../../hil/evidence/remote-ci-validation.json), 원시 응답과 canonical 보고서 위치는 Git에서 제외한 `artifacts/hil/20261019T065002Z-9ca3773be919/evidence.json`에 있다.

로컬 구현 때의 ELF와 원격 ELF 해시가 다르다는 사실을 정상적으로 구분했다. 로컬 재빌드로 원격 산출물을 대체하지 않았다. 현재 대상은 모터 없는 LED/UART 보드이며 장비 접근은 기존 Agentic HIL MCP 경로만 사용했다. LED 물리 동작·출력 중복 부재·진자 제어와 의도적 원격 빌드 실패는 이번에 검증하지 않았다.

컴파일 경고는 없었다. Rustup은 `rustup show`의 암시적 도구 체인 설치가 향후 지원 중단될 예정이라고 알렸지만 이번 설치·CI는 성공했다. 실제 실패가 아니므로 이 실행을 위해 workflow를 바꾸거나 재실행하지 않았다.

이 보고서는 검증한 구현 commit 다음의 문서·증거 전용 commit으로 게시한다. 해당 후속 push의 CI는 별도로 확인하며, 펌웨어·빌드 입력에 변화가 없으므로 물리 HIL을 반복하지 않는다.
