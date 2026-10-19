# STM32 Rust development

- Board: NUCLEO-F411RE / STM32F411RET6; target `thumbv7em-none-eabihf`.
- Run `make verify` after changes. Do not weaken checks to make them pass.
- Keep `crates/app-logic` free of HAL, register access, allocation and unsafe code.
- Keep hardware access in `firmware`; preserve the reviewed memory map and pins.
- Use the pinned toolchain and `Cargo.lock`; change dependencies deliberately.
- Keep reviewed tests and public interfaces fixed during implementation-only tasks.
- Report compilation, host tests and physical board execution separately.
- Do not claim flashing or board behavior was verified without the board.
