# CI-001: Rust 버전 고정과 동일 ELF의 CI → 로컬 HIL 연결

기준: [펌웨어 계약](../firmware-contract.md), [개발 흐름](../development-workflow.md), [AGENTS.md](../../AGENTS.md).

## 상태와 시작점

- 상태: done(로컬 구현·검증). 작업 모드: 펌웨어 빌드·HIL 포함(LED/UART 베이스라인). 원격 Actions 실행은 not-run.
- 날짜: 2026-10-19, Asia/Seoul. 시작 commit: `3cd3d0abc21c5ab735c78587a67f97d79e34ecf1`, 브랜치: `main`.
- 시작 시 미커밋: 기존 `AGENTS.md`·`README.md`, `docs/`, `hil/evidence/debug-validation.json`. 기존 문서·디버깅 기록을 보존한다.
- 연결 요구사항: REQ-BASE-001~003, REQ-PIPE-001~003. 시험: TEST-BUILD-001, TEST-HIL-001, TEST-TRACE-001, TEST-CI-001, TEST-CI-HIL-001.

## 목표·범위

현재 로컬에서 쓰던 Rust 1.98.1과 STM32 타깃을 고정한다. GitHub hosted runner는 장비 없이 빌드·검사를 수행하고 ELF·SHA256SUMS·출처 manifest를 보관한다. 신뢰한 실행의 commit과 ELF SHA256을 로컬에 전달하면, 재빌드 없이 그 ELF를 검증하고 Agentic HIL MCP로 플래시·UART 판정한 결과를 같은 해시에 연결한다.

| 구분 | 경로 |
| --- | --- |
| 읽기 | 현재 Rust 소스·Cargo/메모리/디버그 설정, HIL 계획·과거 증거, 기존 계약과 명세 |
| 수정/생성 | `f411_blinky/rust-toolchain.toml`, `.github/workflows/firmware-build.yml`, `scripts/Build-HilFirmware.ps1`, `scripts/firmware_artifact.py`, `scripts/Invoke-HilArtifact.ps1`, `scripts/hil_artifact.py`, `tests/test_firmware_artifact.py`, `tests/test_hil_artifact.py`, `.gitignore` |
| 문서·검증 요약 | `AGENTS.md`, `README.md`, `docs/firmware-contract.md`, `docs/development-workflow.md`, 본 작업 명세, `hil/evidence/ci-artifact-validation.json` |
| 보존 | Rust 애플리케이션 동작, 기존 HIL 계획·증거, 참조 원본, 외부 authoritative configuration과 권한 |
| 생성하되 Git 제외 | `artifacts/`와 `.agentic-hil/artifacts/`의 ELF·manifest·MCP 보고서 |

제어기·모터·엔코더 구현과 원격 브랜치 보호 설정은 범위 밖이다. CI 결과와 실제 보드 판정은 구분한다. 원격 실행에는 구현을 GitHub에 전달한 상태와 해당 workflow 실행 결과가 필요하며 로컬 성공을 원격 성공으로 표시하지 않는다.

## 수용 기준

| 기준 | 요구사항 | 합격 조건 | 시험 |
| --- | --- | --- | --- |
| AC-01 | REQ-BASE-001, REQ-PIPE-002 | 정확한 Rust 1.98.1·target으로 잠긴 빌드 성공 | TEST-BUILD-001 |
| AC-02 | REQ-PIPE-001 | source snapshot·commit/dirty·toolchain·ELF SHA를 담은 묶음을 생성하고 변조·다른 commit/hash는 거부 | TEST-TRACE-001, 단위시험 |
| AC-03 | REQ-PIPE-002 | hosted CI에 빌드·검사·산출물 업로드가 구성되고 immutable action 참조를 사용 | TEST-CI-001의 구성 검사. 원격 실행은 별도 기록 |
| AC-04 | REQ-BASE-002~003, REQ-PIPE-003 | 로컬 bridge가 같은 ELF SHA로 MCP 계획을 실행하고 플래시 읽기 검증·5초 내 Hello World·cleanup을 기록 | TEST-HIL-001, TEST-CI-HIL-001 |
| AC-05 | REQ-PIPE-003 | hash/commit 불일치 입력은 MCP·보드 접촉 전에 차단 | 의미 있는 단위시험과 로컬 거부 검사 |

## 실행·증거

| 항목 | 상태 | 근거 |
| --- | --- | --- |
| 사전 보드 확인·기존 정상 계획 | pass | MCP probe 성공 후 기존 Debug ELF의 `run-5e23aebb42743516` 정상 통과. 새 CI 묶음 검증과 구분 |
| 고정 도구 체인 설치·빌드 | pass | Rust 1.98.1·target 설치 후 `Build-HilFirmware.ps1 -Offline` 성공. 빌드 전후 입력 지문과 ELF 복사 SHA 일치 |
| 아티팩트·bridge 단위시험 | pass(일부 skip) | 35개 중 32개 통과·3개 Windows 심볼릭 링크 생성 권한으로 제외. junction 거부 모의시험은 통과 |
| workflow 정적 검사 | pass | 공식 checksum으로 검증한 actionlint 1.7.12 통과. immutable action SHA·hosted runner·최소 권한 확인 |
| GitHub-hosted 실행·업로드/다운로드 | not-run | 이번에는 commit·push하지 않았으므로 실제 GitHub 실행 결과는 없음 |
| 실제 잘못된 SHA 입력 | pass | exit 2, `Image SHA256 mismatch`. HIL 실행 폴더 수가 1개로 동일하며 MCP 시작 전 거부 |
| 전송한 묶음의 동일 ELF HIL | pass | 재빌드 없이 `Invoke-HilArtifact.ps1` 실행, run `run-179ca48df83d65d1`, flash SHA 일치·read-back·UART 13바이트·cleanup 성공 |

이번 보드 구동은 모터 없는 기존 LED/UART 펌웨어에 한정한다. 로컬 bridge는 신뢰한 저장소 코드로 실행하며 묶음에 포함된 스크립트·HIL 계획을 실행하지 않는다. SHA256은 출처 인증을 대신하지 않으므로 기대 commit·SHA는 신뢰한 GitHub 실행 요약 등에서 별도로 취득한다.

## 인계

- 재확인할 요약은 [ci-artifact-validation.json](../../hil/evidence/ci-artifact-validation.json)이며 실제 산출물은 Git에서 제외된 `artifacts/firmware/`에 있다. 원시 MCP 응답과 canonical 보고서 위치는 요약의 local_evidence에 보존했다.
- 실제 검증 ELF SHA256: `9479ced40d28fae1e0e3f167939fa71259974f3d4fe388b12017864f9101b312`.
- 이 검증은 시작 commit에 미커밋 구현을 포함한 로컬 산출물이다. `source.dirty: true`, 입력 지문 `192ab3645057bdbf2cf40cd1d5970eb9ba3c1e615ff4cd2e6c5de3f13300812b`, manifest SHA `7e5299dade8037af7a62755e49554e5a026454af7207c797feea9d75d4af03af`로 구분한다.
- 사용자 검토 후 GitHub에 변경을 전달하고, 실제 Actions 실행의 commit·artifact·ELF SHA로 기본 dirty 거부 경로를 재검증하면 원격 CI까지의 실행 증거가 완성된다. 실제 원격 동작 없이 TEST-CI-001을 통과로 기록하지 않는다.
- Rust 앱·기존 HIL 계획·과거 증거·외부 권한은 변경하지 않았다. 마지막 정상 계획은 run 리셋 후 UART 정리를 완료했고 장비 예약을 해제했다.
