# POSIX sh: activate with `. ./scripts/env.sh` from the repository root.
# Keep Rust separate from the existing ARM C/C++ toolchain.
TASK_RUST_TOOLS_ROOT=${TASK_RUST_TOOLS_ROOT:-/workspace/.rust-tools}
CARGO_HOME=$TASK_RUST_TOOLS_ROOT/cargo
RUSTUP_HOME=$TASK_RUST_TOOLS_ROOT/rustup

case ":${PATH-}:" in
    *":$CARGO_HOME/bin:"*) ;;
    *) PATH="$CARGO_HOME/bin${PATH:+:$PATH}" ;;
esac

export TASK_RUST_TOOLS_ROOT CARGO_HOME RUSTUP_HOME PATH
