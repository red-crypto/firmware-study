#!/usr/bin/env bash
set -euo pipefail

task_repo_root=$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
cd "$task_repo_root"
# shellcheck source=env.sh
. ./scripts/env.sh

printf '%s\n' 'Checking Rust formatting'
cargo fmt --all -- --check

printf '%s\n' 'Running hardware-independent host tests'
cargo test --locked --package app-logic --all-targets

printf '%s\n' 'Checking host logic with Clippy'
cargo clippy --locked --package app-logic --all-targets --no-deps -- -D warnings

printf '%s\n' 'Checking Cortex-M4F firmware with Clippy'
cargo clippy --locked --package firmware --target thumbv7em-none-eabihf --no-deps -- -D warnings

printf '%s\n' 'Linking debug and release firmware'
cargo build --locked --package firmware --target thumbv7em-none-eabihf
cargo firmware

printf '%s\n' 'Checking linked STM32F411RE images'
python3 scripts/check-elf.py target/thumbv7em-none-eabihf/debug/firmware
python3 scripts/check-elf.py target/thumbv7em-none-eabihf/release/firmware

printf '%s\n' 'PASS: format, host tests, Clippy, ARM links and ELF checks. Physical board execution is not tested.'
