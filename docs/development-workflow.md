# STM32 Rust 개발 · 검증 · 통합 흐름

이 문서는 STM32 Rust 펌웨어를 작은 변경 단위로 개발하고 Agentic HIL 증거를 연결해 Git으로 이력을 남기는 절차다. 기능과 시험의 정본은 [펌웨어 계약 및 검증 대응표](firmware-contract.md), AI 작업의 기본 규칙은 [AGENTS.md](../AGENTS.md)다. 작업을 시작할 때 [작업 명세 템플릿](templates/task-spec.md)을 `docs/tasks/<작업-ID>.md`로 복사한다.

## 현재 상태와 목표

현재 구현은 `f411_blinky/`의 STM32F411RE Rust 부팅 메시지·LED 데모다. 정상 UART HIL·의도적 실패 HIL·배포 smoke 계획과 디버거 경로가 있으며, 정상·의도적 실패·디버거의 과거 검증 기록이 있다. smoke의 별도 실행 기록은 현재 요약에 없다. 기존 기록은 그때 실행한 산출물에 대한 증거이며 이후 변경의 통과를 보장하지 않는다.

Git은 소스·문서·설정의 버전 관리를 담당한다. [`firmware-build.yml`](../.github/workflows/firmware-build.yml)은 장비 없는 GitHub Actions 빌드와 artifact 보관을 구성하고, [`Invoke-HilArtifact.ps1`](../scripts/Invoke-HilArtifact.ps1)은 검토한 동일 ELF를 재빌드 없이 로컬 MCP에 전달한다. **구현과 실제 실행 통과를 구분한다. 원격 Actions 실행·필수 상태 검사·브랜치 보호 설정은 별도 확인이 필요하며, 이 문서 자체가 통과 증거는 아니다.**

장기 목표는 MCU에서 진자 계열 장치의 센싱·제어·구동·밸런싱을 수행하는 것이다. 진자의 축과 링크 수, 센서, 구동기, 전력단 및 제어 주기 등 확정되지 않은 값은 계약의 미정 항목으로 남긴다. 현재 데모의 검증 결과를 제어기 성능이나 모터 안전성 검증으로 확대하지 않는다.

## 1. 작업 정의와 문맥 선택

1. 현재 Git revision, 미커밋 변경, 담당 작업 명세를 확인한다. 다른 사람이나 작업의 변경은 보존한다.
2. 요구사항 ID를 선택하고 변경 목적·수용 기준·필요한 시험 ID를 작성한다. 새 동작이면 계약과 대응표에 요구사항과 시험을 함께 제안한다.
3. 관련 소스·호출부·설정·데이터시트 절을 읽는다. 자료의 버전·revision과 확인되지 않은 가정을 구분한다.
4. 수정할 경로를 작업 명세에 적는다. 새 파일도 경로를 먼저 명시한다. 추가 파일이 필요하면 명세의 범위·영향을 갱신하고 작업한다.

`AGENTS.md`에는 반복 적용되는 핵심 규칙만 유지한다. 작업 중 발견한 임시 상태는 작업 명세에, 장기 설계 결정과 이유는 계약 또는 별도 설계 결정 문서에 남긴다. 핀·클록·의존성처럼 정본에서 확인할 수 있는 값을 여러 문서에 복제하지 않는다.

## 2. 격리와 구현

- 저장소 루트를 Git 작업 루트로 사용하고, 새 작업 브랜치는 기본적으로 `codex/<설명>`으로 만든다. `f411_blinky/` 안에 별도 저장소를 만들지 않는다.
- 동시에 독립 작업을 진행하면 별도 worktree나 checkout으로 변경 충돌을 줄인다. worktree는 파일 접근 권한을 차단하는 장치가 아니므로 Sandbox·MCP 권한도 별도로 적용한다.
- 읽기 범위는 영향 분석에 필요한 호출부와 관련 문서까지 포함하고, 쓰기 범위는 명세에 정한 경로로 제한한다. 기존 참조 프로젝트와 저장소 밖 HIL authoritative configuration의 편집 경로를 혼동하지 않는다.
- 한 변경에는 하나의 논리적 목적을 둔다. 인터페이스·버퍼·타이밍·메모리·ISR 제약의 변화는 계약과 시험에 반영한다.
- 기존 실패를 없애려고 기대값·timeout·한계치를 임의로 완화하지 않는다. 요구사항이 바뀌어 합격 기준 변경이 필요하면 근거와 구현 변경을 함께 검토한다. 구현 AI의 자체 설명만으로 통과를 선언하지 않는다.

## 3. 빌드와 장비 없는 검증

검증은 변경에 필요한 범위로 선택한다. 문서만 바꿨다면 경로·링크·정본 간 일관성을 확인한다. 펌웨어나 빌드 입력을 바꿨다면 아래 빌드를 수행하고 결과를 `TEST-BUILD-001`에 연결한다.

| 목적 | 실행 위치 | 현재 실행 방법 |
|---|---|---|
| 펌웨어 빌드 | `f411_blinky/` | `cargo build --locked` |
| HIL용 Debug ELF와 추적 가능한 묶음 생성 | 저장소 루트 | `./scripts/Build-HilFirmware.ps1` |
| 산출물·MCP 경계의 장비 없는 시험 | 저장소 루트 | `python -m unittest discover -s tests -p 'test_*.py' -v` |

[`rust-toolchain.toml`](../f411_blinky/rust-toolchain.toml)이 Rust `1.98.1` / minimal / `thumbv7em-none-eabihf`를 고정한다. 빌드 스크립트는 Python 3.11+를 사용하며 내부적으로 `f411_blinky/`에서 `cargo build --locked --target thumbv7em-none-eabihf`를 실행한다. 최초 Rustup 설치에는 네트워크가 필요하다. `-Offline`은 도구 체인과 의존성이 이미 준비됐을 때 사용한다.

원본과 SHA256이 같은 `.elf` 복사본을 기존 경로에 유지하고, 기본 `artifacts/firmware/`에 ELF·`SHA256SUMS`·`manifest.json` 세 파일을 만든다. manifest는 commit·dirty 상태·명시적 빌드 입력들의 해시·합성 지문, Rust/Cargo·target·profile, ELF SHA/크기와 해당하는 CI 실행 정보를 기록한다. 빌드 전후 입력 지문과 commit이 다르면 거부한다. 환경의 target 디렉터리·Rust flags 덮어쓰기도 표준 빌드에서 거부한다. `-ArtifactDirectory`는 묶음 출력 위치, `-PythonExecutable`은 Python을 지정한다.

기본 기존 HIL 계획은 `f411_blinky/target/thumbv7em-none-eabihf/debug/f411_blinky.elf`를 사용한다. 스크립트의 `-Release`로 만든 산출물은 이 계획이 자동으로 선택하지 않는다. CI는 현재 Debug를 표준 묶음으로 만든다.

현재 바이너리는 `test = false`이며 호스트에서 실행하는 제어 로직 테스트 구조가 없다. Python 산출물 검증 시험을 펌웨어 제어 로직 시험으로 간주하거나 `cargo test`를 이미 구성된 검증으로 기록하지 않는다. 향후 제어 수식·상태기계·오류 판단을 HAL에서 분리하면 호스트용 테스트를 추가하고 시험 ID·실행 위치·허용 오차를 먼저 정의한다. `fmt`, `clippy`, 메모리 상한 검사도 CI에 실제 도입한 뒤 필수 검사로 표시한다.

## 4. Agentic HIL 검증

보드에 접근하는 작업은 Agentic HIL skill을 읽고 MCP 도구로 수행한다. 이 절의 도구명은 MCP 호출이며 Shell 명령이 아니다. HIL workspace는 저장소 루트다.

| 시험 ID | 현재 MCP 실행 | 판정과 종료 조건 |
|---|---|---|
| `TEST-HIL-001` | `test_reactor_run`, `test_config_path: hil/hello-world.yaml` | 계획 성공과 5초 내 `Hello World` 한 줄 수신. 정확히 한 번 출력, LED 주기 및 전기적 신호 품질은 이 시험의 측정 범위가 아님 |
| `TEST-HIL-002` | `test_reactor_run`, `test_config_path: hil/hello-world-negative.yaml` 실행 후 정상 계획 재실행 | 의도적 실패 계획은 `comparator_unmet`이어야 하며, 정상 계획 복구까지 성공해야 전체 검증 완료. 장비 연결 실패·timeout 등 다른 이유의 실패는 기대된 의도적 실패 판정이 아님 |
| `TEST-HIL-003` | `test_reactor_run`, `test_config_path: hil/smoke.yaml` | 플래시·run 리셋 성공. 기능 검증을 대체하지 않음 |
| `TEST-DEBUG-001` | 명시적 bench run 안에서 typed debug MCP 도구 사용 | attach·소스 중단점·심볼 조회·세션 정리 결과 확인. 현재 데모를 정상 실행으로 복귀시켰는지도 기록 |

단일 `dut`와 `dut_uart`를 사용하는 실행은 reactor의 장치 예약으로 직렬화한다. 다른 작업의 예약을 강제 해제하지 않는다. 여러 호출에 걸친 디버깅은 `bench_run_start`로 장치 사용 범위를 선언한다. 연결 대상이 바뀌면 adoption·description reload 후 `probe_target`으로 대상 보드를 확인한다.

CI 묶음 검증은 6절의 로컬 진입점을 사용한다. 정상 시험은 위 `TEST-HIL-001`과 같은 flash→UART 준비→run reset→5초 내 `Hello World` 계약이며 이미지 경로만 검증한 고정 복사본으로 바꾼다. 현재 연결 진입점에는 negative/smoke/debug 자동 실행이 없으므로 각각의 통과를 대신 주장하지 않는다.

의도적 실패 계획은 기본 성공 회귀 묶음과 분리한다. 기대된 comparator 실패와 복구 성공을 각각 남기고, 일반적인 실행 실패를 성공으로 바꾸는 처리로 감추지 않는다. `debug_stop_session`은 코어를 halted로 남기므로 현재 blinky를 정상 실행으로 되돌릴 때는 `reset_target`의 `mode: run`과 bench run 종료가 필요하다.

**위 복귀 절차는 현재 LED/UART 데모에 한정된다.** 향후 모터 전원이 연결된 시스템에서는 코어 정지·리셋이 안전 상태를 보장하지 않는다. 구동기 차단, PWM 출력, 재시작 조건, 비상 정지와 bench 종료 상태를 전용 요구사항·절차·시험으로 정하고 검증한 뒤 구동 시운전을 진행한다.

## 5. 증거와 변경의 연결

작업 명세에는 시험별 `planned`, `not-run`, `pass`, `fail`, `blocked` 상태와 실제 실행 결과를 기록한다. 실패한 의도적 실패 계획의 원시 결과는 실패로 보존하고, 기대한 실패 유형 및 복구 성공을 근거로 `TEST-HIL-002` 전체 판정을 별도로 기록한다.

펌웨어 검증 기록에는 최소한 다음 연결이 필요하다.

- 시험한 소스 commit SHA와 미커밋 변경 유무. 미커밋 빌드면 diff 또는 패치 식별자를 함께 기록하고 commit 단독 검증으로 표시하지 않는다.
- Rust 도구·target·빌드 profile, 의존성 잠금 파일, HIL 도구 버전 및 실행한 시험 계획의 revision.
- 실제 사용한 ELF 경로와 SHA256, 빌드 결과, HIL run ID 및 원본 보고서·로그 위치.
- 합격·실패·미실행과 미측정 항목, 시험 종료 시 보드 상태 및 남은 문제.

ELF나 대용량 로그를 무조건 Git에 넣지 않는다. 산출물은 CI artifact에 보관하며 로컬 `artifacts/`와 `.agentic-hil/artifacts/`는 Git에서 제외한다. 로컬 연결은 `artifacts/hil/<UTC-시각-ID>/`에 실행한 `hello-world.json`과 `evidence.json`을 저장하고, evidence에는 해당 MCP 호출의 원시 응답·run·보고서 위치·계획 해시·관측 ELF SHA를 연결한다. 원시 로컬 증거에는 절대경로나 장비 정보가 포함될 수 있으므로 공유 시 검토한 작은 요약만 남기고 장치 식별자·자격증명을 복제하지 않는다.

## 6. GitHub Actions 산출물과 로컬 HIL 연결

현재 workflow와 로컬 진입점은 다음 역할을 분리한다. 원격 workflow를 실제 실행하지 않았다면 `TEST-CI-001`을 통과로 표시하지 않는다.

| 단계 | 실행 환경·입력 | 통합 조건 |
|---|---|---|
| PR/push/수동 빌드 | GitHub hosted `windows-2025`, 트리거된 checkout SHA | `contents: read`, checkout 인증정보 미보존, 고정 Rust, Python 경계 시험, `cargo build --locked`. 보드·벤치 자격증명 접근 없음 |
| 산출물 보관 | 빌드를 통과한 정확한 commit | ELF·SHA256SUMS·manifest를 `firmware-<commit>-<run ID>-<attempt>` 이름으로 14일 보관. 요약에 ELF SHA와 GitHub archive digest를 구별해 표시 |
| 로컬 HIL | 신뢰된 로컬 코드, 선택한 묶음과 별도로 확인한 commit/ELF SHA | 검증 후 고정 ELF를 공식 MCP로 전달. reactor의 장치 예약과 원시 응답·계획/ELF SHA 확인. 정상 시험 한 개 실행 |
| 통합 검토 | PR의 현재 revision과 검증 기록 | 변경에 필요한 검사가 해당 revision을 검증했는지 확인한 뒤 merge 판단 |

외부 PR과 검토되지 않은 코드가 물리 벤치에 접근하도록 트리거를 연결하지 않는다. hosted job에는 HIL 호출이 없다. 로컬 [`hil_artifact.py`](../scripts/hil_artifact.py)는 설치된 `agentic-hil mcp-stdio`에 JSON-RPC로 `test_reactor_run`을 호출하는 제한된 MCP client이며, debugger·UART를 직접 열지 않는다. 다운로드한 묶음은 데이터로 취급하고 포함된 스크립트나 시험 계획을 실행하지 않는다.

선택한 Actions 실행의 checkout commit과 요약에 표시된 **ELF SHA256**을 먼저 확인하고 artifact를 내려받아 압축을 푼다. PR의 기본 checkout은 시험용 merge commit일 수 있으므로 PR head와 혼동하지 않는다. 신뢰된 로컬 checkout에서 실행한다.

```powershell
.\scripts\Invoke-HilArtifact.ps1 `
  -BundlePath .\artifacts\download\selected-firmware `
  -ExpectedCommit '<검토한 40자리 commit SHA>' `
  -ExpectedSha256 '<Actions 요약의 64자리 ELF SHA256>'
```

`ExpectedCommit`·`ExpectedSha256`은 다운로드한 manifest를 그대로 읽어 채우지 않는다. verifier는 schema·target·보드·Rust 버전·ARM ELF 구조·크기·checksum·commit·source 지문·dirty 상태를 확인한다. 불일치는 MCP 서버 시작 전에 거부하고, 통과한 바이트는 `.agentic-hil/artifacts/ci/<ELF SHA>/f411_blinky.elf`에 저장한다. 재빌드 없이 로컬 코드의 고정 정상 계획을 실행하며 reactor가 보고한 플래시 SHA, 실행 계획 SHA와 복사본 SHA도 대조한다. nonzero 종료나 cleanup/판정 실패를 성공으로 취급하지 않는다.

`-AllowDirty`는 미커밋 로컬 개발 산출물에만 명시적으로 사용한다. source 입력 지문과 dirty 상태를 유지하며 clean Actions 산출물 검증으로 보고하지 않는다. SHA와 manifest는 서명된 출처 증명이 아니므로 신뢰는 검토한 실행과 로컬 코드에서 시작한다.

HIL은 이름이 `latest`인 파일이나 브랜치의 최신 HEAD를 그대로 플래시하지 않는다. 검토 대상으로 선택한 정확한 commit의 산출물을 받거나 그 commit을 깨끗한 작업공간에서 빌드하고, 실제 ELF SHA256을 결과와 연결한다. 재빌드했다면 앞선 hosted 빌드와 동일 바이너리라고 가정하지 않고 새 빌드의 출처와 해시를 남긴다.

PR에 새 commit이 추가되면 기존 검증을 새 revision의 통과로 재사용하지 않는다. merge commit이나 squash 결과가 달라지면 그 revision에 필요한 검증 범위를 다시 판단한다. 필수 검사·보호 규칙을 실제 설정하기 전에는 문서상 절차가 자동으로 merge를 차단한다고 표현하지 않는다.

## 7. 리뷰와 인계

PR은 문제와 최종 동작, 요구사항 ID, 변경한 계약·인터페이스, 시험 결과·근거, 미실행 항목을 포함한다. AI 사용 기록이 필요하면 도구·모델·버전을 기재하되, 대화 전체를 정본으로 삼지 않는다.

리뷰에서는 구현과 함께 합격 기준 변경, ISR/동시성/버퍼/메모리 영향, 관측한 범위를 확인한다. AI 검토는 보조 수단이며 merge 판단과 물리 구동 시운전 책임은 담당자에게 둔다.

작업을 중단하거나 다음 세션으로 넘길 때는 현재 revision·dirty 상태, 변경 파일, 실제 시험 결과와 근거, 남은 결정·다음 행동을 작업 명세에 남긴다. 다음 세션은 기록을 현재 Git 상태와 대조한다. commit·push·PR 생성·merge는 해당 작업에서 요청하거나 합의한 범위에 따라 진행하며, 문서 작성만 요청받은 작업에서 자동으로 수행하지 않는다.

## CI 구성 시 확인할 공식 문서

- [Rustup 도구 체인 파일](https://rust-lang.github.io/rustup/overrides.html#the-toolchain-file): 고정 버전·profile·target 적용 규칙.
- [고정한 checkout v7.0.1](https://github.com/actions/checkout/commit/3d3c42e5aac5ba805825da76410c181273ba90b1), [고정한 upload-artifact v7.0.2](https://github.com/actions/upload-artifact/commit/cf430e030ddbb5b0abf93d22962f4752f3646cd9): workflow가 실행하는 공식 action 코드.
- [GitHub self-hosted runner](https://docs.github.com/en/actions/concepts/runners/self-hosted-runners): 실행 환경·유지관리 책임과 연결 범위를 결정할 때 참조한다.
- [GitHub Actions 보안](https://docs.github.com/en/actions/reference/security/secure-use): 외부 PR, runner 신뢰 경계와 최소 권한 구성을 검토할 때 참조한다.
- [Workflow artifacts](https://docs.github.com/en/actions/concepts/workflows-and-actions/workflow-artifacts): 빌드 산출물·로그의 전달과 보관 정책을 정할 때 참조한다.
