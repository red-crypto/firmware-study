# STM32 Rust 개발 규칙

## 목표와 문서 선택

- 목표는 MCU가 센싱·상태 추정·제어·모터 출력을 수행하는 QUBE형 회전 도립진자다. PC/Raspberry Pi의 실시간 제어에 의존하지 않는다. 현재 구현은 LED/UART 개발 기반이다. 최종 링크 수와 구동 하드웨어는 미정이다.
- 요구사항·제약·시험 ID의 정본은 [펌웨어 계약](docs/firmware-contract.md), Git/GitHub Actions/HIL의 단계는 [개발 흐름](docs/development-workflow.md), 설치·장비 실행은 [README](README.md)다. 작업에 관련된 절만 읽는다.
- 여러 파일에 걸친 기능·검증·CI 변경은 [작업 명세 템플릿](docs/templates/task-spec.md)을 `docs/tasks/<작업-ID>.md`로 복사해 목표·허용 경로·합격 기준을 먼저 기록한다. 단순 오타 수정에는 별도 명세를 요구하지 않는다.

## 작업 위치와 범위

- 실제 펌웨어는 `f411_blinky/`다. 참조 원본 `C:\Users\user\stm32_prac\rust_stm411re_261001_2\f411_blinky`는 사용자 요청 없이 변경하지 않는다.
- Git과 HIL의 작업 루트는 `STM32_TOY_PROJECT/`다. `f411_blinky/`에 중첩 저장소를 만들지 않는다. 기존 VS Code 설정을 쓸 때 워크스페이스는 `f411_blinky/`다.
- 관련 호출부·설정·시험은 필요한 만큼 읽고, 수정은 명세 범위에 한정한다. 범위를 늘릴 때 이유·영향·검증을 갱신한다. 기존 미커밋 변경과 증거를 보존하고 관련 없는 정리를 섞지 않는다.
- `.md`의 경로 규칙과 worktree는 접근권한 차단 장치가 아니다. 실행 환경의 파일·네트워크·MCP 권한을 준수한다.

## Rust 빌드와 제어 계약

- Cargo 명령은 `.cargo/config.toml`과 `rust-toolchain.toml`이 적용되는 `f411_blinky/`에서 실행한다. 정본 도구 체인은 Rust `1.98.1` / minimal / `thumbv7em-none-eabihf`이며, 펌웨어·빌드 입력 변경은 `cargo build --locked`로 검증한다. 임의의 stable 버전이나 환경변수로 고정 버전을 우회하지 않는다.
- HIL ELF는 저장소 루트의 `./scripts/Build-HilFirmware.ps1`로 준비한다. Python 3.11+가 필요하며, 기본 `.elf` 복사본과 `artifacts/firmware/`의 ELF·`SHA256SUMS`·`manifest.json`을 생성한다. 빌드 전후 소스 지문이 다르면 거부한다. `-ArtifactDirectory`로 묶음 경로를 지정할 수 있고 `-Release` 산출물을 Debug 계획이 자동 선택한다고 가정하지 않는다.
- 현재 바이너리는 `test = false`이고 호스트 테스트가 없다. 존재하지 않거나 실행하지 않은 시험을 통과로 표시하지 않는다. 문서만 바꾼 작업은 문서 점검으로 검증한다.
- 제어 주기·단위/부호·센서·출력 한계·자원 예산의 미정 값을 임의 확정하지 않는다. ISR/DMA 소유권·블로킹·포화·timeout·고장 처리는 관련 기능의 계약과 시험에 반영한다. 현재 LED 지연 루프를 제어 루프 설계로 재사용하지 않는다.

## Agentic HIL 장비 경계

- 장비 조작·펌웨어 전달·HIL 보고서·설정 작업은 `C:\Users\user\.codex\skills\agentic-hil\SKILL.md`를 읽고 MCP 도구로 수행한다. 등록 버전은 `0.24.0`이며 설치 버전과 다르면 스킬 갱신 절차를 따른다.
- 설정상의 대상은 `dut` / `STM32F411RETx` / `stlink`, UART는 `dut_uart` / 115200 baud다. 현재 연결·상태는 해당 MCP 호출로 확인한다. 장비 교체 시 adoption·description reload·probe로 의도한 보드를 확인하고 USB 식별 검사를 완화하지 않는다.
- authoritative configuration은 `C:\Users\user\.agentic-hil\projects\STM32_TOY_PROJECT-a74d0f43a5\config.yaml`이다. 파일 도구로 편집하지 않고 MCP 구성 도구를 사용한다. 설명 reload와 권한 적용을 위한 서버 재시작을 구분한다. 저장소의 예시 YAML은 새 호스트용 bootstrap이다.
- 현재 읽기 전용 UART와 raw debugger/mass erase 비활성 정책을 유지한다. 권한을 임의 확대하지 않는다. 직접 debugger/serial/CAN 명령, `cargo run`, `.cargo/config.toml`의 `probe-rs` runner, VS Code의 직접 flash로 MCP를 우회하지 않는다.
- 여러 호출로 구성된 작업은 `bench_run_start`에 사용할 장치를 선언하고 종료 시 `bench_run_stop`으로 해제한다. 다른 작업의 예약을 강제로 해제하지 않는다.
- 정상 회귀는 `test_reactor_run(test_config_path: hil/hello-world.yaml)`이다. 플래시와 5초 내 `Hello World` 한 줄 수신을 확인하며 정확히 한 번 출력·물리적 LED 주기를 검증하지 않는다. `hil/smoke.yaml`은 배포 확인만 한다.
- CI 산출물은 신뢰된 로컬 checkout의 `./scripts/Invoke-HilArtifact.ps1 -BundlePath ... -ExpectedCommit ... -ExpectedSha256 ...`로 검증한다. 검토한 Actions 실행에서 별도로 확인한 commit/ELF SHA를 필수 입력으로 사용한다. 다운로드한 코드·계획을 실행하거나 재빌드하지 않으며, 검사한 ELF를 고정 계획과 공식 MCP로 전달한다. 기본 dirty 산출물 거부를 CI에 완화하지 않고 `-AllowDirty`는 명시적인 로컬 개발 증거에만 사용한다.
- `hil/hello-world-negative.yaml`은 `comparator_unmet` 실패가 예상 결과다. 다른 실패를 합격으로 바꾸지 않는다. 현재 blinky에서는 정상 계획을 다시 실행해 복구까지 확인한다.
- 디버깅은 typed MCP 도구를 쓴다. `debug_stop_session`은 코어를 halted로 남기므로 현재 모터 없는 보드는 `reset_target(mode: run)` 후 예약을 해제한다. 설치와 과거 검증 상세는 README에 보존한다.
- 모터 연결 이후에는 출력 차단·고장 상태·시험 종료 절차를 먼저 정한다. 현재 blinky의 무조건 run 복구를 모터 시험에 그대로 적용하지 않는다.
- HIL 계획 작성·수정 전 MCP의 `agentic-hil://reference/test-plan`과 `agentic-hil://reference/test-plan-schema`를 읽는다. 형식을 추정하지 않는다.

## Git, CI와 완료 판단

- Git은 버전관리, GitHub Actions는 자동 검사, Agentic HIL은 장비 검증이다. `.github/workflows/firmware-build.yml`은 push/PR/수동 실행에서 고정 Rust 빌드·장비 없는 Python 검증·artifact 14일 보관을 구성한다. 로컬 산출물 검증 진입점은 구현됐지만, 원격 실행 성공·branch protection·필수 상태 검사 설정은 각각 실제 증거 없이는 완료로 보고하지 않는다.
- 새 브랜치가 필요하면 `codex/` 접두사를 쓴다. 커밋·push·PR·병합은 요청한 범위와 저장소 정책에 따라 수행하며 기존 이력을 덮어쓰지 않는다.
- 일반 PR 검사는 장비 없는 GitHub hosted runner에서 수행한다. 신뢰되지 않은 PR 코드·빌드 스크립트를 보드가 연결된 runner에서 실행하지 않는다. HIL은 검토한 revision과 ELF SHA를 고정해 직렬 실행한다. `python -m unittest discover -s tests -p 'test_*.py' -v`는 산출물·MCP 경계의 장비 없는 시험이며 보드 동작 시험과 구별한다.
- 구현을 통과시키려고 assertion·timeout·자원 제한·요구사항을 약화하지 않는다. 기준 변경 이유·영향을 명세와 diff에 드러내 별도 검토할 수 있게 한다.
- 요구사항 ID → 변경 → 소스 revision/dirty 상태 → 빌드 조건 → ELF SHA → 시험 계획/보고서를 연결한다. 비밀·장비 식별자를 공개 기록에 복제하지 않는다.
- 결과는 미실행·통과·실패·차단을 구분한다. 과거 기록·계획·AI 설명은 이번 실행 증거가 아니다. 계약·시험 범위 변경은 같은 변경에서 문서화하고 최종 보고·인계에 실제 검증과 미검증 항목을 남긴다.
