# NUCLEO-F411RE Rust 개발 환경

STM32F411RET6용 Rust 펌웨어와, 보드 없이 검사하는 기능 로직을 분리한 시작 프로젝트입니다. 예제는 보드의 LD2(PA5)를 약 500ms마다 켜고 끕니다. 내부 HSI 클록과 SysTick을 사용하므로 외부 크리스털 설정이 필요하지 않습니다. 지연과 루프 실행 시간이 포함되어 정밀한 시계로 쓰는 예제는 아닙니다.

## 클라우드에서 시작하기

Linux x86_64 환경에서 Python 3.11 이상, `curl`, `sha256sum`, `make`와 호스트 C 링커가 필요합니다. 현재 클라우드에는 이 기본 도구가 준비되어 있습니다.

```sh
cd /workspace/firmware-study
bash scripts/setup-rust.sh
. ./scripts/env.sh
make verify
```

`make setup`도 같은 설치 스크립트를 실행합니다. 설치 스크립트를 실행한 뒤 현재 터미널에서 `. ./scripts/env.sh`로 활성화하세요. 새 터미널에서도 활성화가 필요합니다. 이 명령은 POSIX `sh`와 Bash에서 사용할 수 있습니다.

설정의 기준은 `rust-toolchain.toml`입니다. Rust **1.99.1**, `rustfmt`, `clippy`, STM32용 **`thumbv7em-none-eabihf`** 타깃을 설치합니다. `Cargo.lock`과 정확한 버전의 직접 의존성을 함께 관리합니다. 루트에서 기본 빌드 타깃을 ARM으로 지정하지 않으므로 PC용 테스트와 보드용 빌드를 구분할 수 있습니다.

Rust 도구는 저장소 바깥의 `/workspace/.rust-tools`에 설치됩니다. 기존 ARM C/C++ 도구와 `test.txt`는 그대로 둡니다. 다른 설치 경로가 필요하면 설치와 활성화 양쪽에서 같은 값을 사용하세요.

```sh
export TASK_RUST_TOOLS_ROOT=/workspace/my-rust-tools
bash scripts/setup-rust.sh
. ./scripts/env.sh
```

설치 스크립트는 다시 실행할 수 있습니다. 고정된 rustup 1.28.2 설치 파일을 SHA-256으로 검증하고, 이후에는 필요한 컴파일러·컴포넌트·타깃을 맞춥니다. 기존 rustup을 매번 업데이트하지 않습니다. 세션의 프록시 및 CA 환경변수를 유지하며 TLS 검증을 사용합니다. 설치와 최초 의존성 다운로드에는 네트워크 접근이 필요합니다.

## 코드와 검증 경계

```text
crates/app-logic/    no_std 기능 로직과 PC에서 실행하는 단위 테스트
firmware/           HAL, GPIO, 클록, 시작점, STM32 메모리 배치
.cargo/config.toml  ARM 빌드 alias 및 링커 설정
rust-toolchain.toml 고정 Rust 버전·컴포넌트·타깃
scripts/            설치, 활성화, 검증 스크립트
AGENTS.md           Codex 작업 규칙
```

`app-logic`은 HAL과 레지스터를 참조하지 않으며 `unsafe`를 금지합니다. 현재 시간 값을 입력받아 LED 상태를 계산하므로, PC 테스트에서 시간 경계와 `u32` 시간 오버플로를 실제 대기 없이 검사합니다. `firmware`는 이 상태를 받아 실제 PA5 핀을 제어합니다. 펌웨어는 `no_std`/`no_main`으로 동작합니다.

직접 작성한 코드에는 컴파일러 경고를 오류로 적용합니다. Clippy의 `all`·`pedantic` 검사와 `unwrap`·`expect` 제한도 적용합니다. HAL 등 외부 의존성은 내부적으로 하드웨어 접근에 필요한 `unsafe`를 사용할 수 있습니다.

| 명령 | 수행 작업 |
| --- | --- |
| `make verify` | 포맷 검사 → PC 단위 테스트 → PC/ARM Clippy → ARM debug·release 빌드 → ELF 구조 검사 |
| `make firmware` 또는 `cargo firmware` | STM32용 release 펌웨어 빌드 |
| `make test` | PC 단위 테스트 |
| `make fmt` | Rust 코드 포맷 적용 |

Make 없이 검증 스크립트를 직접 실행할 수도 있습니다.

```sh
. ./scripts/env.sh
bash scripts/verify.sh
```

최종 실행 파일은 **`target/thumbv7em-none-eabihf/release/firmware`**입니다. 확장자가 없어도 ELF 형식이며 STM32CubeProgrammer에서 선택할 수 있습니다. 메모리 배치는 기본 부트 주소 `0x08000000`, Flash 512 KiB, RAM 128 KiB입니다. 별도 부트로더 오프셋은 적용하지 않습니다.

## Windows에서 보드에 업로드하기

클라우드에서 빌드한 ELF 파일을 Windows로 가져오면 Rust를 Windows에 설치하지 않고도 업로드할 수 있습니다.

1. [STM32CubeProgrammer](https://www.st.com/en/development-tools/stm32cubeprog.html)를 설치합니다. 필요한 ST-LINK 드라이버도 설치합니다.
2. NUCLEO-F411RE의 ST-LINK USB 포트를 Windows PC에 연결합니다.
3. CubeProgrammer에서 `ST-LINK`로 연결하고 위 ELF 파일을 선택합니다. 파일 선택 필터가 있으면 전체 파일을 표시합니다.
4. 다운로드·검증을 수행하고 리셋 또는 실행합니다. 기존 보드 펌웨어를 덮어씁니다.
5. LD2가 약 500ms마다 상태를 바꾸는지 확인합니다.

클라우드는 Windows의 USB 보드에 자동 연결되지 않습니다. 이 프로젝트에서 자동 검증하는 범위는 컴파일, PC 테스트 및 ELF 검사입니다. **실제 보드 업로드와 동작 확인은 아직 수행하지 않았습니다.**

## Windows에서도 직접 빌드하려면

[rustup](https://rustup.rs/)으로 Windows용 Rust를 설치합니다. 설치 시 안내되는 Visual Studio C++ Build Tools도 설치하면 PC 단위 테스트용 MSVC 링커를 사용할 수 있습니다. PowerShell에서 다음을 실행합니다.

```powershell
git clone https://github.com/red-crypto/firmware-study.git
cd firmware-study
rustup toolchain install 1.99.1 --profile minimal --component rustfmt --component clippy --target thumbv7em-none-eabihf
cargo fmt --all -- --check
cargo test --locked -p app-logic
cargo clippy --locked -p app-logic --all-targets -- -D warnings
cargo clippy --locked -p firmware --target thumbv7em-none-eabihf --release -- -D warnings
cargo build --locked -p firmware --target thumbv7em-none-eabihf --release
```

`cargo firmware`도 마지막 빌드와 같습니다. Linux용 `scripts/env.sh`는 Windows에서 사용하지 않습니다. ELF 구조 검사까지 포함한 전체 검증은 클라우드의 `make verify` 또는 GitHub CI 결과로 확인하세요.

## Rust가 보장하는 것과 실제 보드에서 확인할 것

Rust 컴파일러는 타입, 소유권, 참조 수명 등으로 많은 메모리 오류를 빌드 전에 찾아냅니다. 이 프로젝트의 검사와 테스트는 그 위에 동작 조건을 추가합니다. 하지만 핀 배선, 전압, 센서 응답, 인터럽트 타이밍, 실제 클록 오차까지 컴파일러가 확인하지는 않습니다. 기능을 추가할 때는 테스트로 고정할 로직과 실제 보드에서 확인할 항목을 함께 정하세요.
