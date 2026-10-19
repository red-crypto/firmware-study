# Project working directory

- The active STM32F411 Rust firmware project is `f411_blinky/` in this repository.
- Make firmware changes in that copy. The original project at `C:\Users\user\stm32_prac\rust_stm411re_261001_2\f411_blinky` is a reference; keep it unchanged unless the user requests otherwise.
- Run Cargo commands with `f411_blinky/` as the working directory so its `.cargo/config.toml` is loaded. Validate builds with `cargo build --locked`.
- Use the Git repository at `STM32_TOY_PROJECT/` for version control. Do not initialize a nested repository in `f411_blinky/`.
- Open `f411_blinky/` as the VS Code workspace when using its existing debug configuration.
