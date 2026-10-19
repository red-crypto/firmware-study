# STM32F411RE Rust + Agentic HIL

[Agentic HIL Nucleo 데모](https://github.com/agentic-hil/agentic-hil/tree/master/examples/nucleo-f446re_demo)의 빌드 → 플래시 → 리셋 → UART 검증 흐름을 STM32F411RE Rust 프로젝트에 적용한 구성입니다.

## 대상과 펌웨어

- MCU: STM32F411RE, Cortex-M4F (`thumbv7em-none-eabihf`)
- 클록: HSI 기반 SYSCLK 48 MHz
- 메모리: Flash 512 KiB, RAM 128 KiB
- LD2: PA5, 1초마다 상태 전환
- UART: USART2 PA2(TX)/PA3(RX), ST-LINK Virtual COM Port, 115200 8N1
- 부팅 메시지: `Hello World\r\n`, 리셋마다 한 번 출력

소스는 `f411_blinky/`에 있고, Git과 HIL의 작업 루트는 이 저장소의 최상위 폴더입니다.

## 빌드

저장소 루트의 PowerShell에서 실행합니다.

```powershell
.\scripts\Build-HilFirmware.ps1
```

의존성이 캐시에 있으면 `-Offline`을 추가할 수 있습니다. 스크립트는 Cargo 설정이 적용되도록 `f411_blinky/`에서 빌드하고, Cargo의 ELF 출력과 같은 내용의 `.elf` 파일을 생성해 SHA256을 확인합니다.

기본 테스트가 사용하는 Debug 이미지는 다음 경로입니다.

```text
f411_blinky/target/thumbv7em-none-eabihf/debug/f411_blinky.elf
```

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

## 확인한 결과

실제 보드에서 정상 계획 통과 → 잘못된 기대값의 실패 확인 → 정상 계획 재통과까지 수행했습니다. UART로 13바이트 `Hello World\r\n`을 수신했고 플래시 읽기 검증과 세션 정리도 성공했습니다. 결과 요약과 각 실행의 원본 보고서 경로는 `hil/evidence/validation.json`에 있습니다.

이 검증은 펌웨어 플래시와 UART 부팅 출력에 대한 것입니다. LED의 물리적 점멸은 자동 측정하지 않았습니다. 현재 구성의 대화형 디버그 세션에는 추가로 ST-LINK GDB server가 필요합니다.
