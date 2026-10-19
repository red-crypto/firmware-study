# STM32F411RE Rust + Agentic HIL

[Agentic HIL Nucleo 데모](https://github.com/agentic-hil/agentic-hil/tree/master/examples/nucleo-f446re_demo)의 빌드 → 플래시 → 리셋 → UART 검증 흐름을 STM32F411RE Rust 프로젝트에 적용한 구성입니다.

## 개발 목표와 문서

장기 목표는 QUBE형 회전 도립진자의 균형 제어를 STM32 Rust 펌웨어로 구현하는 것입니다. 센싱·상태 추정·제어·모터 출력은 MCU에서 수행하고, PC는 개발·분석·GitHub Actions CI·Agentic HIL 검증에 사용합니다. 현재 코드는 LED/UART 개발 베이스라인이며 모터·엔코더·진자 제어는 아직 구현하지 않았습니다.

영상의 실제 링크 구조는 아직 확인되지 않았으므로 단일/이중 진자 여부와 최종 기구 사양은 미정입니다. QUBE-Servo 3는 참고 모델이며 해당 제품의 구매·STM32 직접 연결을 전제로 하지 않습니다.

- [AI 개발 규칙](AGENTS.md): 작업 위치·범위·빌드·장비 경계·완료 기준
- [펌웨어 계약과 요구사항–테스트 추적](docs/firmware-contract.md): 현재 동작, 목표 요구사항, 합격 기준, 미검증 범위
- [Git / GitHub Actions / HIL 개발 흐름](docs/development-workflow.md): 로컬 개발부터 CI 산출물과 보드 검증까지의 절차
- [작업 명세 템플릿](docs/templates/task-spec.md): `docs/tasks/<작업-ID>.md`로 복사해 사용
- [이번 문서 정비 작업 기록](docs/tasks/2026-10-19-documentation-foundation.md)
- [Rust 버전 고정·CI·동일 ELF HIL 작업 기록](docs/tasks/2026-10-19-build-ci-hil-artifact.md)

GitHub Actions 빌드와 산출물 보관, 같은 ELF를 로컬 Agentic HIL로 검증하는 진입점이 구성돼 있습니다. 원격 CI 실행과 보드 실행의 통과 여부는 각각 실제 기록으로 판단합니다. GitHub branch protection과 필수 상태 검사는 이 변경에서 조회하거나 설정하지 않았습니다.

## 대상과 펌웨어

- MCU: STM32F411RE, Cortex-M4F (`thumbv7em-none-eabihf`)
- 클록: HSI 기반 SYSCLK 48 MHz
- 메모리: Flash 512 KiB, RAM 128 KiB
- LD2: PA5, 코드상 1초 지연마다 상태 전환(이상적인 전체 점멸 주기는 약 2초, 실측하지 않음)
- UART: USART2 PA2(TX)/PA3(RX), ST-LINK Virtual COM Port, 115200 8N1
- 부팅 메시지: `Hello World\r\n`, 코드상 초기화 후 한 번 출력. 현재 HIL은 5초 내 한 줄 수신을 검사하며 중복 출력 부재는 검사하지 않음

소스는 `f411_blinky/`에 있고, Git과 HIL의 작업 루트는 이 저장소의 최상위 폴더입니다.

## 빌드

Rustup, Git, Python 3.11+와 PowerShell이 필요합니다. [`f411_blinky/rust-toolchain.toml`](f411_blinky/rust-toolchain.toml)이 Rust `1.98.1`, minimal profile, `thumbv7em-none-eabihf`를 고정합니다. 최초 빌드에서는 Rustup이 이 버전을 설치하므로 네트워크가 필요하며, 전역 stable을 업데이트해도 프로젝트 버전은 바뀌지 않습니다. Cargo는 `f411_blinky/`에서 실행합니다.

저장소 루트의 PowerShell에서 실행합니다.

```powershell
.\scripts\Build-HilFirmware.ps1
```

도구 체인과 의존성이 모두 설치·캐시돼 있으면 `-Offline`을 추가할 수 있습니다. 스크립트는 `f411_blinky/`에서 `cargo build --locked --target thumbv7em-none-eabihf`를 실행하고, Cargo의 ELF 출력과 같은 내용의 `.elf` 파일을 생성해 SHA256을 확인합니다. 빌드 전후 입력 파일 지문을 비교하고, 다르면 산출물 생성을 거부합니다. `CARGO_TARGET_DIR`·`RUSTFLAGS` 등의 빌드 덮어쓰기도 표준 산출물 경로에서 거부합니다.

기본 보관 폴더는 `artifacts/firmware/`이며 `-ArtifactDirectory`로 바꿀 수 있습니다. `-PythonExecutable`은 사용할 Python 실행파일을 지정합니다. `-Release`는 Release 산출물을 만들지만 기존 Debug HIL 계획의 입력을 바꾸지는 않습니다.

| 파일 | 용도 |
|---|---|
| `f411_blinky.elf` | 실제 HIL에 전달할 ELF |
| `SHA256SUMS` | ELF 파일명과 SHA256 |
| `manifest.json` | 소스 commit·dirty 상태·빌드 입력 지문, Rust/Cargo·target·profile, ELF SHA/크기, 해당하는 CI 실행 정보 |

이 묶음은 검증할 데이터이며 실행할 스크립트나 시험 계획을 포함하지 않습니다. SHA는 무결성을 확인하고, 출처는 검토한 GitHub 실행과 별도로 대조합니다. manifest는 서명된 공급망 증명이 아닙니다.

기본 테스트가 사용하는 Debug 이미지는 다음 경로입니다.

```text
f411_blinky/target/thumbv7em-none-eabihf/debug/f411_blinky.elf
```

## GitHub Actions → 같은 ELF의 로컬 HIL

[`firmware-build.yml`](.github/workflows/firmware-build.yml)은 push·pull request·수동 실행에서 장비 없는 `windows-2025` runner를 사용합니다. 실제 checkout SHA를 확인한 뒤 고정 도구 체인을 설치하고, Python 검증 시험과 잠긴 Cargo 빌드를 실행합니다. ELF·SHA256SUMS·manifest 묶음은 `firmware-<commit>-<run ID>-<attempt>` 이름으로 14일 보관합니다. Actions 코드는 공식 release의 commit SHA로 고정하고 저장소 읽기 권한만 부여합니다.

1. 검토한 Actions 실행의 성공 여부와 checkout commit을 확인합니다. PR 실행은 PR head가 아닌 GitHub의 시험용 merge commit을 빌드할 수 있으므로 요약에 표시된 실제 commit을 사용합니다.
2. 실행 요약에서 ELF SHA256을 확인하고 artifact를 내려받아 `artifacts/download/selected-firmware/`에 압축을 풉니다. GitHub archive digest와 ELF SHA256은 다른 값입니다.
3. 보드 연결을 확인한 신뢰된 로컬 checkout에서 아래 명령에 검토한 commit·ELF SHA를 직접 넣어 실행합니다. 값은 다운로드한 manifest만 읽어 자동으로 신뢰하지 않습니다.

```powershell
.\scripts\Invoke-HilArtifact.ps1 `
  -BundlePath .\artifacts\download\selected-firmware `
  -ExpectedCommit '<검토한 40자리 commit SHA>' `
  -ExpectedSha256 '<Actions 요약의 64자리 ELF SHA256>'
```

이 명령은 재빌드하지 않습니다. 묶음 검증을 먼저 통과해야 MCP 서버를 시작하고, 검사한 ELF를 `.agentic-hil/artifacts/ci/<SHA>/`에 고정한 뒤 로컬 코드가 만든 정상 계획을 공식 `agentic-hil mcp-stdio`에 전달합니다. 플래시 단계에서 관측한 ELF SHA와 실제 계획 SHA도 대조합니다. 결과와 해당 실행의 원시 응답은 `artifacts/hil/<UTC-시각-ID>/evidence.json`, 실행 계획은 같은 폴더의 `hello-world.json`에 남습니다.

기본 경로는 dirty 산출물을 거부합니다. 명시적으로 미커밋 로컬 개발본을 시험할 때만 `-AllowDirty`를 사용하고 그 결과를 clean CI 산출물의 검증으로 표시하지 않습니다. `-PythonExecutable`·`-HilExecutable`은 신뢰된 로컬 설치 실행파일을 지정합니다. 다운로드한 코드나 계획을 실행하지 않으며, 보드 연결 runner를 GitHub PR에 붙이지 않습니다.

연결 진입점은 정상 `Hello World` 시험 한 개를 실행합니다. 의도적 실패와 복구는 아래 기존 계획으로 별도 수행합니다. 출력은 현재 blinky용이므로 모터 연결 전에 안전 출력·종료 절차와 별도 계약을 먼저 마련해야 합니다.

장비 없이 산출물 변조·revision 불일치·dirty 거부와 MCP 경계를 점검하는 시험은 다음과 같습니다. 이 시험은 제어 기능이나 보드 동작의 합격을 뜻하지 않습니다.

```powershell
python -m unittest discover -s tests -p 'test_*.py' -v
```

로컬 빌드·묶음 전송·동일 ELF의 실제 MCP HIL 검증을 수행한 요약은 [`ci-artifact-validation.json`](hil/evidence/ci-artifact-validation.json)에 있습니다. 미커밋 로컬 산출물의 검증이며 GitHub-hosted workflow 실행·업로드/다운로드는 아직 수행하지 않았습니다. 원격 실행 결과와 구분합니다.

## HIL 구성

이 PC에는 Agentic HIL 0.24.0이 Codex의 stdio MCP로 설치되어 있습니다. 디버거 `dut`는 STM32CubeProgrammer의 ST-Link 백엔드를 사용하고, UART는 `dut_uart`입니다. 실제 연결에서 STM32F411 계열과 ST-LINK VCP 통신을 확인했습니다.

ST-Link 시리얼 번호, USB 식별자, COM 번호, 실행파일 경로와 권한은 저장소 밖의 authoritative configuration에 보관됩니다. UART는 시리얼 번호와 USB VID/PID로 확인하므로 COM 번호만 보고 다른 장치에 연결하지 않습니다. 보드를 다시 연결했을 때는 MCP `project_config_adopt_hardware`로 확인하고 `project_config_reload_description`으로 적용합니다.

재연결로 COM 번호만 바뀐 경우 adoption은 기존 값을 보존합니다. `com_port_identity_mismatch`가 반환한 `expected_device`를 확인하고, MCP `project_config_set`으로 `com_ports.dut_uart.device`를 고친 뒤 description reload를 수행합니다.

새 PC에서 사람이 최초 설치할 때는 저장소 루트에서 다음 절차를 사용할 수 있습니다. Rust의 `thumbv7em-none-eabihf` 타깃과 STM32CubeProgrammer CLI도 필요합니다.

```powershell
uv tool install --python 3.12 'agentic-hil[can]==0.24.0'
agentic-hil setup --agent codex
```

`agentic-hil.config.example.yaml`은 장치 이름과 초기 요구사항을 선언하는 bootstrap profile입니다. `setup`은 이를 바탕으로 외부 구성을 생성합니다. 이미 존재하는 외부 구성의 변경은 MCP 구성 도구로 진행합니다. 보드 작업은 `agentic-hil` MCP를 사용합니다.

## 실제 보드 테스트

빌드 후 Codex에서 다음과 같이 요청하면 됩니다.

> `hil/hello-world.yaml`을 Agentic HIL MCP로 실행해줘.

이는 MCP `test_reactor_run`의 `test_config_path`에 `hil/hello-world.yaml`을 전달합니다. 계획은 다음 순서로 실행되고, 종료 시 UART 세션을 정리합니다.

1. ELF 플래시 및 읽기 검증
2. UART 열기와 수신 버퍼 초기화
3. MCU를 run 모드로 리셋
4. 5초 안에 완전한 한 줄 `Hello World`가 수신되는지 비교

`hil/hello-world-negative.yaml`은 기대 문구만 바꾼 의도적인 실패 테스트입니다. 실제 보드가 `Hello World`를 보내더라도 `comparator_unmet`으로 실패해야 합니다. 실패 시 기본 복구가 MCU를 halt 상태로 둘 수 있으므로, 이 테스트 후에는 정상 계획을 다시 실행합니다.

`hil/smoke.yaml`은 UART 판정 없이 플래시와 리셋만 확인하는 별도 계획입니다.

## HIL 디버깅

이 PC의 STM32Cube 도구 번들에 있는 ST-LINK GDB server `7.14.0+st.2`를 `debuggers.dut.gdb_server_executable`에 등록했습니다. GDB 클라이언트는 기존 `gdb-multiarch`를 사용합니다. 실행파일의 절대 경로는 외부 authoritative configuration에 저장되며, MCP description reload로 적용했습니다.

새 PC에서는 ST의 STM32Cube 도구 번들에서 `stlink-gdbserver`와 GDB를 설치하고 실제 실행파일 경로를 확인합니다. `project_config_describe` 후 `project_config_set`으로 `debuggers.dut.gdb_server_executable`을 설정하고 `project_config_reload_description`을 호출합니다. `debug.gdb_executable`도 변경했다면 해당 debug 섹션은 MCP 서버 재시작으로 적용합니다.

빌드된 Debug ELF를 사용해 다음과 같이 요청할 수 있습니다.

> HIL로 실행 중인 보드에 attach해서 LED 루프에 중단점을 걸고, 도달 위치와 `main` 심볼을 확인한 뒤 종료해줘.

실제로 검증한 MCP 흐름은 다음과 같습니다.

1. `bench_run_start`: `debugger` 장치 `dut` 선언
2. `debug_start_session`: 위 Debug ELF의 `image_path`, `mode: attach` — 펌웨어를 다시 쓰지 않고 연결하며 코어는 halted로 반환
3. `debug_set_breakpoint`: 현재 소스의 LED 루프 위치 지정 (`file: f411_blinky/src/main.rs`, `line: 45`)
4. `debug_continue`: `timeout_s: 5` 안에 `breakpoint_hit` 확인
5. `debug_get_stop_reason`으로 함수·소스 위치 확인, `debug_symbol_info`로 `main` 주소와 크기 확인
6. `debug_stop_session`으로 중단점과 디버그 세션 정리
7. `reset_target`의 `mode: run`으로 프로그램 실행 후 `bench_run_stop`으로 장치 해제

소스가 바뀌면 중단점 줄 번호도 다시 확인합니다. 컴파일러의 명령어·소스 매핑 때문에 요청한 줄과 정지 프레임의 줄은 다를 수 있습니다. `debug_stop_session`은 코어가 halted임을 확인하고 끝나므로 정상 실행으로 돌려놓을 때는 마지막 run 리셋을 수행합니다. `debug_continue`는 다음 정지까지 기다리는 호출이며, 제한시간에 도달하면 코어를 다시 중단시킵니다.

raw debugger 명령과 mass erase 권한은 비활성 상태에서 검증했습니다. 결과는 `hil/evidence/debug-validation.json`에 기록했습니다.

## 확인한 결과

실제 보드에서 정상 계획 통과 → 잘못된 기대값의 실패 확인 → 정상 계획 재통과까지 수행했습니다. UART로 13바이트 `Hello World\r\n`을 수신했고 플래시 읽기 검증과 세션 정리도 성공했습니다. 결과 요약과 각 실행의 원본 보고서 경로는 `hil/evidence/validation.json`에 있습니다.

ST-LINK GDB 서버를 통한 attach, 소스 중단점 도달, `main` 심볼 조회와 종료 후 run 리셋도 실제 보드에서 확인했습니다. LED의 물리적 점멸은 자동 측정하지 않았습니다.
