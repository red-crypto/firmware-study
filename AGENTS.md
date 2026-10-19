# Project working directory

- The active STM32F411 Rust firmware project is `f411_blinky/` in this repository.
- Make firmware changes in that copy. The original project at `C:\Users\user\stm32_prac\rust_stm411re_261001_2\f411_blinky` is a reference; keep it unchanged unless the user requests otherwise.
- Run Cargo commands with `f411_blinky/` as the working directory so its `.cargo/config.toml` is loaded. Validate builds with `cargo build --locked`.
- Use the Git repository at `STM32_TOY_PROJECT/` for version control. Do not initialize a nested repository in `f411_blinky/`.
- Open `f411_blinky/` as the VS Code workspace when using its existing debug configuration.

## Agentic HIL

- Read `C:\Users\user\.codex\skills\agentic-hil\SKILL.md` for Agentic HIL setup and hardware operations. Route covered hardware operations through its MCP tools.
- Use this repository root as the HIL workspace. The configured single debugger is `dut`, for `f411_blinky` / `STM32F411RETx`, with the `stlink` backend and the installed STM32CubeProgrammer CLI.
- The authoritative configuration is outside the repository at `C:\Users\user\.agentic-hil\projects\STM32_TOY_PROJECT-a74d0f43a5\config.yaml`. Change it through the Agentic HIL configuration tools; do not edit it with file tools.
- The STM32F411 board and its ST-Link VCP were bound through `project_config_adopt_hardware` and verified through MCP. The UART entry is `dut_uart` at 115200 baud; the external configuration pins its USB serial and VID/PID. On a later hardware change, use adoption and description reload, then `probe_target`, to confirm the intended board before flashing.
- From the repository root, run `./scripts/Build-HilFirmware.ps1` (optional `-Offline` or `-Release`) to build and prepare an ELF image accepted by HIL. The default image is `f411_blinky/target/thumbv7em-none-eabihf/debug/f411_blinky.elf`.
- Run `hil/hello-world.yaml` through `test_reactor_run` with that explicit `test_config_path`. It flashes the Debug ELF, opens UART, resets into run mode and asserts the one-time `Hello World` boot line. `hil/smoke.yaml` remains a deployment-only plan.
- `hil/hello-world-negative.yaml` is deliberately expected to fail with `comparator_unmet`. After running it, run the normal plan again to leave the target running. Both verdicts were verified on the real board; `hil/evidence/validation.json` records the runs.
- The firmware toggles PA5 once per second; the current HIL plans do not measure physical LED behavior.
- The user chose to retain the generated default permissions. The subsequently adopted UART entry is read-only, which is sufficient for these tests. Raw debugger commands and mass erase remain disabled. Interactive debug sessions additionally require a compatible GDB and ST-LINK GDB server.
- `agentic-hil.config.example.yaml` is a portable bootstrap profile for a new host. It does not replace the current external authoritative configuration. See `README.md` for the build and HIL workflow.
