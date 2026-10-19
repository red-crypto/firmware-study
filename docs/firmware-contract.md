# 펌웨어 요구사항과 테스트 계약

이 문서는 현재 STM32F411 Rust 펌웨어가 무엇을 해야 하는지, 어떤 시험으로 확인하는지, 무엇이 아직 미구현인지 연결한다. 요구사항 ID는 코드·작업 명세·PR·시험 결과에서 공통으로 사용한다. 절차는 [개발 워크플로](development-workflow.md), 변경 단위의 작성 양식은 [작업 명세 템플릿](templates/task-spec.md)을 따른다.

## 1. 목표와 현재 범위

장기 목표는 [참고 영상의 QUBE Servo 3](https://www.youtube.com/watch?v=-G4H2DmhR28&t=1s)와 같은 회전 도립진자 장치를 MCU에서 제어하는 것이다. 제어 주기 실행·센서 취득·상태 추정·모터 명령·고장 처리는 MCU가 수행하고, PC는 개발·관측·시험에 사용한다.

현재 범위는 STM32F411RE의 빌드·부팅·UART·LED와 Agentic HIL 경로를 확인하는 개발 기반이다. 모터·드라이버·엔코더·기구부와 센서 구성은 확정하지 않았다. [QUBE Servo 3 공식 제품 설명](https://www.quanser.com/products/qube-servo-3/)과 [공식 인터페이스 문서](https://docs.quanser.com/quarc/documentation/qube_servo3_usb.html)는 모터축·진자축 엔코더와 기본 도립진자 구성을 설명한다. 이를 근거로 QUBE형 단일 회전 도립진자를 우선 참조하되, 영상 프레임은 이번 조사에서 직접 확인하지 못했다. 영상의 단일 링크/이중 링크 구성을 아직 요구사항으로 확정하지 않았으며 최종 링크 수는 TBD다.

QUBE Servo 3 실장비의 구매·STM32 직접 연결 여부도 미정이다. 공식 PC/USB 제어 경로를 STM32 직접 제어가 지원된다는 근거로 해석하거나 QUBE Servo 2의 SPI 정보를 Servo 3에 적용하지 않는다. STM32F411RE가 최종 제어기에 충분한지도 구현·측정 후 판단한다.

현재 확인한 정본은 다음과 같다. 이 표의 값은 기존 개발 기반을 설명하며, 최종 모터 제어용 핀·타이머 배정을 승인하는 자료가 아니다.

| 항목 | 현재 값과 정본 |
| --- | --- |
| 소스 | [`f411_blinky/src/main.rs`](../f411_blinky/src/main.rs), `#![no_std]`, `#![no_main]` Rust |
| 빌드 | [`Cargo.toml`](../f411_blinky/Cargo.toml), [`Cargo.lock`](../f411_blinky/Cargo.lock), [Cargo 설정](../f411_blinky/.cargo/config.toml), [`rust-toolchain.toml`](../f411_blinky/rust-toolchain.toml): Rust `1.98.1` / minimal / `thumbv7em-none-eabihf` |
| 산출물·CI | [`Build-HilFirmware.ps1`](../scripts/Build-HilFirmware.ps1)과 [`firmware-build.yml`](../.github/workflows/firmware-build.yml). 기본 묶음 `artifacts/firmware/`의 ELF·SHA256SUMS·manifest |
| 메모리 영역 | [`memory.x`](../f411_blinky/memory.x)의 Flash 512 KiB, RAM 128 KiB. 사용량·stack 여유의 합격 기준은 아직 없음 |
| 초기화·통신 | 소스의 HSI 기반 SYSCLK 48 MHz, USART2 PA2/PA3, 115200 8N1 |
| 표시 | 소스의 PA5 상태 전환, 전환 사이 명목 지연 1,000 ms |
| 장비·권한 | 저장소 외부 Agentic HIL authoritative configuration. 저장소의 [`agentic-hil.config.example.yaml`](../agentic-hil.config.example.yaml)은 새 호스트용 예시 |

## 2. 상태와 변경 원칙

| 상태 | 뜻 |
| --- | --- |
| 구현됨 / 과거 검증 기록 있음 | 코드·시험과 과거 관측 기록이 존재한다. 현재 작업 트리나 새 ELF에 대한 재검증을 뜻하지 않는다 |
| 구현됨 / 자동 검증 없음 | 코드에서 의도를 확인했지만 해당 동작의 판정 가능한 시험이 없다 |
| 계획 / 미구현 | 필요한 기능 또는 시험 제안이다. 수치·방법을 확정하고 구현하기 전에는 합격 판정을 내리지 않는다 |
| 현재 변경 검증 완료 | 이번 소스·산출물·시험·장비를 연결한 증거와 합격 판정이 있다. 과거 기록만으로 이 상태를 부여하지 않는다 |

표의 구현 상태와 각 작업의 실행 판정은 구분한다. 이번 변경의 빌드·CI·HIL 통과는 해당 작업 명세와 revision/ELF가 연결된 증거로 확인한다. 문서 정비 당시의 과거 기록만으로 현재 변경을 하드웨어 검증 완료로 표시하지 않는다.

CI-001의 [작업 기록](tasks/2026-10-19-build-ci-hil-artifact.md)과 [검증 요약](../hil/evidence/ci-artifact-validation.json)은 고정 도구 체인 빌드·전송한 동일 ELF의 실제 로컬 HIL·잘못된 입력 차단을 확인한다. 미커밋 로컬 산출물의 결과이며 GitHub-hosted 실행은 미실행이다.

- 요구사항을 바꾸면 관련 테스트와 작업 명세를 같은 변경에서 갱신한다. 삭제·대체한 ID를 다른 의미로 재사용하지 않는다.
- 기존 요구사항의 합격 기준을 구현에 맞추어 약화하지 않는다. 변경 이유와 영향, 요구사항 변경 승인을 작업 명세·PR에 남긴다.
- TBD는 결정이 필요한 값이다. AI가 관행적인 수치·핀·게인으로 채우지 않는다. 해당 기능 구현 전에 근거와 판정 기준을 확정한다.
- 구현 완료와 검증 완료를 구분한다. 미실행·측정 불가·실패는 그대로 기록하며, 기존 시험의 통과를 새로운 기능의 통과로 확대하지 않는다.

## 3. 현재 개발 기반 요구사항

| ID | 요구사항과 합격 기준 | 검증 연결 | 현재 상태·한계 |
| --- | --- | --- | --- |
| REQ-BASE-001 | 활성 복사본 `f411_blinky/`에서 `cargo build --locked`로 대상 ELF를 생성할 수 있어야 한다. HIL에 제공할 `.elf` 복사본의 SHA256이 Cargo 원본과 같아야 한다 | TEST-BUILD-001 | 고정 Rust/target 빌드와 ELF 복사·묶음 구현됨. 실제 변경의 빌드 판정은 작업별 증거로 확인 |
| REQ-BASE-002 | 기본 HIL 계획은 지정 ELF를 플래시하고 검증한 뒤, UART 수신을 준비하고 `run` 리셋해야 한다 | TEST-HIL-001: 전체 순서, TEST-HIL-003: flash/reset 부분만 | 구현됨 / 과거 정상 계획의 flash verified 기록 있음. smoke의 별도 실행 증거는 현재 요약에 없음 |
| REQ-BASE-003 | 정상 계획은 리셋 후 5초 이내에 UART 한 줄이 `Hello World`와 일치하는 것을 판정해야 한다 | TEST-HIL-001 | 구현됨 / 과거 통과 기록 있음. 중복 출력·출력 횟수·다음 부팅까지의 무출력은 검사하지 않음 |
| REQ-BASE-004 | PA5는 루프에서 상태 전환 후 명목 1,000 ms 지연을 반복해야 한다 | TEST-LED-001 — 계획 | 코드 구현됨 / 자동 물리 검증 없음. 상태 전환 간격이 약 1초이고 전체 켜짐/꺼짐 반복은 약 2초라는 의도이며, 정확도·오차 허용치는 미정 |
| REQ-BASE-005 | 잘못된 UART 기대값은 성공으로 판정되지 않아야 한다. 의도적 실패 원인은 `comparator_unmet`이어야 한다 | TEST-HIL-002 | 구현됨 / 과거 기대 실패 기록 있음. 다른 오류나 단순 `ok: false`만으로 합격 처리하지 않음 |
| REQ-BASE-006 | 정상·의도적 실패 HIL 실행 후 UART 세션을 정리해야 한다. 의도적 실패 시험 및 디버깅 뒤에는 정상 실행 복구를 확인해야 한다 | TEST-HIL-001, TEST-HIL-002, TEST-DEBUG-001 | 과거 cleanup 및 최종 `run` 기록 있음. 새로운 실행에서도 복구 결과를 확인해야 함 |
| REQ-BASE-007 | Debug ELF로 attach하여 소스 중단점 도달과 `main` 심볼 조회가 가능해야 하며, 종료 후 `run` 상태로 복구해야 한다 | TEST-DEBUG-001 | typed MCP 도구를 사용한 과거 기록 있음. 현재 소스의 줄 번호는 실행 전에 재확인 |

현재 소스는 부팅 경로에서 문자열을 한 번 쓰지만, TEST-HIL-001의 판정은 **5초 내 일치하는 한 줄 수신**이다. “부팅마다 정확히 한 번”을 검증 완료로 주장하려면 관측 구간과 중복 판정이 있는 별도 TEST-UART-001이 필요하다.

## 4. 목표 제어 시스템과 개발 파이프라인 요구사항

아래는 설계 논의를 시작하기 위한 **계획 / 미구현** 요구사항이다. 구현 시작 전에 작업 명세에서 적용 범위와 TBD를 확정한다. 제어율·안전 한계·게인·메모리 예산은 현재 확정하지 않는다.

| ID | 요구사항 초안 | 구현 전에 확정할 사항 | 예정 검증 |
| --- | --- | --- | --- |
| REQ-CTRL-001 | MCU에서 주기적으로 센서 취득→상태 계산→제어→출력의 전체 제어 루프를 실행해야 한다 | MCU·RTOS/실행 구조, 주기, 최악 실행시간·지터 한계, 기한 초과 처리 | TEST-CTRL-TIMING-001 |
| REQ-CTRL-002 | 각도·속도 및 필요한 상태를 일관된 단위·부호·기준점으로 제공해야 한다 | 링크 수·좌표계·센서 종류·해상도·샘플링·보정·필터·범위 | TEST-SENSOR-001, TEST-CTRL-MATH-001 |
| REQ-CTRL-003 | 모터 출력은 명시된 제한·극성·활성화 절차를 따라야 한다 | 드라이버·전원·전류/전압/명령 범위·포화·deadband·출력 핀 | TEST-ACTUATOR-001 |
| REQ-CTRL-004 | 초기화·대기·운전·고장 상태와 전이를 정의하고, 고장 상태에서는 합의한 안전 출력을 적용해야 한다 | 비활성화 수단, 센서 이상·통신/타이밍 이상·각도/속도 한계·복귀 조건 | TEST-FAULT-001, TEST-STATE-001 |
| REQ-CTRL-005 | 확정한 동작 조건에서 도립진자의 균형을 유지해야 한다 | 단일/이중 링크, 초기 자세·동작 범위, swing-up 포함 여부, 유지 시간·오차·외란·실패 기준 | TEST-BALANCE-001 |
| REQ-CTRL-006 | 관측·로그 전송이 제어 주기와 출력 제한을 깨뜨리지 않아야 한다 | 기록 항목·주기·버퍼·overflow 동작·전송 부하·타임스탬프 | TEST-TELEMETRY-001, TEST-CTRL-TIMING-001 |
| REQ-CTRL-007 | 확정된 Flash/RAM·stack 예산 안에서 동작해야 한다 | 사용량 상한·여유·측정 조건·최악 경로·동적 할당 허용 여부 | TEST-RESOURCE-001 |
| REQ-CTRL-008 | HAL과 분리 가능한 제어 계산·상태 전이에는 호스트에서 재현 가능한 입력·기대 결과를 제공해야 한다 | 라이브러리 경계·기준 모델·수치 오차·회귀 데이터·NaN/포화/경계 입력 | TEST-CTRL-MATH-001, TEST-STATE-001 |

핀·타이머·DMA·인터럽트·공유 버퍼의 소유 관계는 주변장치를 추가하는 작업의 설계에 포함한다. ISR에서 수행할 일, 공유 데이터의 동기화 방식, 블로킹 가능 구간과 `unsafe`의 근거도 그 작업에서 명시한다. 이 결정들이 생기면 코드와 연결되는 정본 표 또는 설계 결정 기록으로 관리한다.

다음은 Git/GitHub Actions/HIL 통합 요구사항이다. 고정 Rust 빌드·manifest 생성·Actions 설정과 동일 ELF의 로컬 MCP 진입점이 구현돼 있다. 원격 Actions 실행과 필수 상태 검사 설정을 완료로 간주하지 않으며, 정상 묶음 경로와 기존 의도적 실패/복구 경로를 분리해 판정한다.

| ID | 요구사항과 합격 조건 | 검증 연결 | 현재 구현·남은 판정 |
| --- | --- | --- | --- |
| REQ-PIPE-001 | 한 변경의 요구사항·시험 ID, 소스 commit/dirty 상태, 빌드 환경, ELF SHA256, 계획 해시와 실제 판정을 추적할 수 있어야 한다. 과거 결과·다른 산출물·미실행을 현재 통과로 표시하지 않아야 한다 | TEST-TRACE-001 | manifest·빌드 입력 지문·로컬 HIL evidence 연결 구현. 요구사항/시험 ID는 작업 명세에서 연결하며 실행별 대조 필요 |
| REQ-PIPE-002 | GitHub Actions는 특정 revision을 장비 없는 runner에서 고정한 Rust 도구 체인·target과 잠긴 의존성으로 빌드하고, ELF·해시·출처를 보관해야 한다. 빌드 실패를 성공으로 처리하지 않아야 한다 | TEST-CI-001 | workflow 구현: push/PR/수동, hosted Windows, 고정 actions/Rust, 장비 없는 Python 시험, Debug 묶음 14일 보관. hosted 실행 판정은 미실행 상태에서 통과로 올리지 않음 |
| REQ-PIPE-003 | HIL 연결은 검토한 revision·ELF SHA를 확인하고 신뢰된 입력만 직렬 실행해야 한다. 불일치 산출물·검토하지 않은 변경은 장비 호출 전에 거부하며, 정상·의도적 실패·복구와 종료 결과를 각각 보존해야 한다 | TEST-CI-HIL-001, TEST-HIL-002 | 정상 묶음은 사전 검증·고정 복사·로컬 고정 계획·MCP·관측 SHA 대조 구현. 의도적 실패/복구는 기존 별도 계획으로 수행하며 wrapper가 자동 실행하지 않음 |

## 5. 실행 가능한 테스트 목록

명령의 작업 위치와 산출물 경로가 시험의 일부다. Cargo는 `f411_blinky/`에서 실행하고 HIL의 workspace는 저장소 루트를 사용한다. 보드 관련 작업은 Agentic HIL MCP를 통해 수행한다.

| ID | 진입점·사전조건 | 관측과 합격 판정 | 해석 범위 |
| --- | --- | --- | --- |
| TEST-BUILD-001 | 저장소 루트에서 [`scripts/Build-HilFirmware.ps1`](../scripts/Build-HilFirmware.ps1). 내부적으로 `f411_blinky/`에서 고정 Rust로 `cargo build --locked --target thumbv7em-none-eabihf`. Python 3.11+ 필요. 기본 Debug, 도구·의존성 준비 후에만 `-Offline` | 빌드 exit 0, 원본과 `.elf` 복사본 SHA256 일치, 빌드 전후 입력 지문/commit 일치, ELF·SHA256SUMS·manifest 생성 | 컴파일·링크·산출물 준비. 동작·메모리 여유·타이밍 합격을 뜻하지 않음 |
| TEST-HIL-001 | TEST-BUILD-001의 Debug ELF, 채택·확인된 `dut`/`dut_uart`. MCP `test_reactor_run`에 `test_config_path: hil/hello-world.yaml` 명시. [계획](../hil/hello-world.yaml) | 플래시 읽기 검증, `run` 리셋, 5초 내 한 줄 `Hello World` 일치, 실행 성공 및 UART cleanup 확인 | 부팅 경로와 UART 기본 연결. 정확히 한 번 출력·LED·제어 동작은 검증하지 않음 |
| TEST-HIL-002 | 같은 Debug ELF로 `test_reactor_run`에 `test_config_path: hil/hello-world-negative.yaml` 명시. [계획](../hil/hello-world-negative.yaml) | **원본 결과는 실패**하고 원인이 `comparator_unmet`인 것이 예상 결과. 플래시·수신·cleanup도 확인. 이어 TEST-HIL-001을 다시 통과시켜 정상 실행으로 복구 | 잘못된 기대값을 검출하는 시험. 다른 실패 원인은 불합격/조사 대상. 일반 통과 회귀에 그대로 섞지 않음 |
| TEST-HIL-003 | 대상 보드를 MCP로 확인한 후 `test_reactor_run`에 `test_config_path: hil/smoke.yaml` 명시. [계획](../hil/smoke.yaml) | 지정 ELF 플래시·검증과 `run` 리셋 성공 | 배포 경로만 확인. UART·애플리케이션 판정은 없음 |
| TEST-DEBUG-001 | 현재 Debug ELF. `bench_run_start`에서 `dut` 선언→`debug_start_session` attach→현재 루프 위치 중단점→continue→stop reason·`main` symbol 조회 | 제한시간 내 `breakpoint_hit`, 심볼 확인, `debug_stop_session` 정리 후 `reset_target(mode: run)` 성공과 `bench_run_stop` 확인 | 디버깅 경로의 통합 확인. debugger 종료 직후 코어는 halted이므로 run 복구가 필요 |
| TEST-TRACE-001 | Python `unittest`의 산출물 검증과 작업 명세·manifest·실제 HIL evidence 대조 | schema·target·ARM ELF·size·checksum·commit·빌드 입력 지문·dirty 거부, 구현된 변조/불일치 사례의 실패 확인. 실제 기록의 revision/ELF/계획 SHA와 요구사항·시험 ID 연결 | 장비 없는 시험과 실제 실행 증거를 분리. manifest는 builder 선언이며 서명된 출처 증명이 아님 |
| TEST-CI-001 | [`firmware-build.yml`](../.github/workflows/firmware-build.yml)의 push/PR/수동 실행. 신뢰된 GitHub 실행 화면과 artifact 확인 | 실제 checkout SHA, 고정 도구 체인/target, 잠긴 빌드·Python 시험 성공과 artifact 대응. 의도적 빌드 실패는 실패 상태여야 함 | workflow 구성 존재. 원격 성공/실패 검증은 실제 실행 전 `not-run`이며 로컬 빌드로 대체하지 않음 |
| TEST-CI-HIL-001 | 신뢰된 로컬 [`Invoke-HilArtifact.ps1`](../scripts/Invoke-HilArtifact.ps1)에 `-BundlePath`, 별도 확인한 `-ExpectedCommit`, `-ExpectedSha256` 전달. Python 3.11+·Agentic HIL·확인한 보드 필요 | 불일치는 MCP 시작 전 거부. 동일 ELF 고정 복사 후 로컬 고정 정상 계획 실행, 실제 flash SHA·plan SHA·판정·cleanup·원시 응답 연결 | 재빌드 없음. 정상 시험 한 개만 실행. `-AllowDirty` 결과는 로컬 개발 증거로 구분. negative/복구 판정은 TEST-HIL-002로 별도 수행 |

TEST-HIL-001/002/003은 현재 계획의 Debug 경로를 사용한다. `-Release`로 만든 ELF가 자동으로 해당 계획의 입력이 되지는 않는다. Release 검증이 필요하면 산출물과 계획의 대응을 명시적으로 추가한다.

위 `run` 복구는 현재 LED/UART 펌웨어에 대한 절차다. 모터가 연결되기 전 해당 기구·드라이버의 안전 출력·에너지 차단·고장 후 재활성화 조건과 시험 종료 절차를 먼저 정의한다. 모터 제어 펌웨어에 현재의 `run` 리셋 복구를 그대로 적용하지 않는다.

현재 바이너리는 [`Cargo.toml`](../f411_blinky/Cargo.toml)의 `test = false`이며 펌웨어 제어 계산용 호스트 테스트 구조가 없다. Python `unittest`는 산출물·MCP 경계만 검증하며 `cargo test`를 현재 제어 기능 검증 수단으로 간주하지 않는다. REQ-CTRL-008 구현 시 순수 계산을 검증 가능한 라이브러리로 나누고 실제 의미 있는 호스트 테스트를 추가한다.

## 6. 계획 테스트와 아직 없는 판정

아래 ID는 추적용 예약이다. 실행 파일·도구·수치·측정 장치가 준비되지 않았으며 아직 CI 또는 HIL 통과 항목이 아니다.

| ID | 필요한 관측·판정 설계 |
| --- | --- |
| TEST-UART-001 | 리셋별 관측 구간·반복 횟수·종료 조건을 정하고 `Hello World` 정확히 1회, 추가 출력·누락·중복 판정 |
| TEST-LED-001 | PA5 전기 신호 또는 광학 신호의 실제 전환 간격·전체 주기 측정. 허용 오차와 측정 방법 확정 |
| TEST-CTRL-MATH-001 | 호스트에서 센서 변환·추정·제어 계산을 기준 결과·경계·잘못된 입력과 비교 |
| TEST-STATE-001 | 초기화·활성화·고장·복구 전이와 상태별 허용 출력 검증 |
| TEST-SENSOR-001 | 실제 각도 기준·방향·보정·센서 오류와 MCU 취득값 비교 |
| TEST-ACTUATOR-001 | 제한된 입력 조건에서 명령→실제 출력·극성·비활성화 검증 |
| TEST-FAULT-001 | 합의된 센서·타이밍·출력 이상을 주입하고 고장 검출 시간·안전 출력·복구 관측 |
| TEST-CTRL-TIMING-001 | 실제 MCU에서 부하·로그·경계 경로를 포함한 제어 주기·최악 실행시간·지터·기한 초과 측정 |
| TEST-TELEMETRY-001 | 정상·포화 부하의 로그 일관성·누락/overflow 동작과 제어 주기 영향 측정 |
| TEST-RESOURCE-001 | Release 및 실제 실행 조건의 Flash/RAM·stack 사용량을 합의된 예산과 비교 |
| TEST-BALANCE-001 | 확정한 기구·초기 조건·오차·시간·외란에 대해 균형 유지와 실패·복구 관측 |

## 7. 검증 증거와 판정 기록

각 검증 결과는 최소한 다음 항목을 함께 기록한다. 원본 Agentic HIL 보고서는 도구의 관리 위치에 두고 저장소에는 재확인 가능한 요약을 남긴다. USB 식별자·로컬 절대경로·비밀값을 공개 CI artifact에 무조건 복제하지 않는다.

| 분류 | 필요한 정보 |
| --- | --- |
| 변경 식별 | Git commit SHA, dirty 여부, dirty라면 검증한 diff의 식별자/해시와 포함되지 않은 파일 설명 |
| 빌드 식별 | Rust·Cargo 버전, target, Debug/Release, 명령, `Cargo.lock` 및 도구 체인 설정 식별, ELF SHA256 |
| 시험 식별 | 요구사항 ID·테스트 ID, 실행 시각·run ID, 계획 경로와 내용 해시, 실제 사용한 ELF SHA256 |
| 장비·환경 | 대상 보드/MCU, Agentic HIL·관련 도구 버전, 권한·설정 revision 또는 비밀값을 제외한 설정 지문, 장비 확인 결과 |
| 판정 | 기대 결과와 실제 결과, 원본 verdict/error type, 수치·로그·cleanup·복구 결과, 원본 보고서 위치 |
| CI 연결 | 해당 GitHub Actions run URL·job·artifact와 checksum. 호스트 빌드 성공과 보드 검증 결과를 별도 표시 |

증거 연결의 기준은 `소스 상태 → 빌드 환경 → ELF SHA256 → 시험 계획·장비 → 실제 관측 → 요구사항 판정`이다. 여러 단계에서 같은 ELF 해시를 확인해야 로컬 HIL 결과를 CI 산출물과 연결할 수 있다. 로컬에서 다시 빌드한 이미지라면 CI 이미지와 같다고 가정하지 않는다.

현재 묶음의 `manifest.json`은 명시적 빌드 입력과 Rust/Cargo·profile·ELF를 기록하고, 로컬 `artifacts/hil/<UTC-시각-ID>/evidence.json`은 해당 실행의 원시 응답·계획 SHA·관측 flash SHA를 연결한다. 다운로드한 manifest는 기대 SHA의 신뢰 출처로 사용하지 않는다. `ExpectedCommit`과 `ExpectedSha256`은 검토한 Actions 실행에서 별도로 확인한다. 미커밋 빌드는 source dirty와 입력 지문을 보존하며 clean CI 실행의 검증으로 표시하지 않는다. 원시 로컬 증거를 공개할 때에는 장치 식별자·로컬 경로를 점검한다.

현재 [`hil/evidence/validation.json`](../hil/evidence/validation.json)은 정상 통과→의도적 `comparator_unmet` 실패→정상 복구 통과의 과거 기록이다. [`hil/evidence/debug-validation.json`](../hil/evidence/debug-validation.json)은 attach·중단점·심볼·정리·run 복구의 과거 기록이다. 두 기록에는 당시 ELF SHA256이 있지만 소스 commit/dirty 상태·시험 계획 해시·완전한 빌드 환경이 모두 연결되어 있지 않다. 따라서 **기존 경로의 동작 이력**으로 사용하며, 현재 소스의 재현성이나 새 변경의 합격 증거로 승격하지 않는다.

## 8. 단계별 확장 제안

| 단계 | 다음 단계로 진행할 때 필요한 결과 |
| --- | --- |
| 개발 기반 | AGENTS·작업 명세·본 계약, GitHub Actions 빌드 결과, 정확한 ELF와 연결된 정상/의도적 실패 HIL 기록 |
| 기구·입출력 확정 | 단일/이중 링크 결정, MCU·모터·센서·드라이버·배선·좌표계·출력 제한·안전 상태 확정 |
| MCU 입출력·상태기계 | 센서·출력·고장 처리를 각각 검증한 증거와 제어 주기·자원 예산 측정 |
| 첫 균형 제어 | 기준 계산과 호스트 회귀 테스트, 실제 MCU의 타이밍, 정량적인 균형 유지 결과 |
| 고도화 | 필요 시 swing-up·외란·이중 링크로 확대하고 대응 요구사항과 검증 추가 |

먼저 단일 링크로 입출력·안전 상태·제어 주기를 검증한 뒤 확장하는 접근을 권장한다. 이는 단계적 개발 제안이며 사용자가 선택한 기구 사양이나 이중 링크 개발 취소를 의미하지 않는다.
