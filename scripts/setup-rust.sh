#!/usr/bin/env bash
set -euo pipefail

task_repo_root=$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
# shellcheck source=env.sh
. "$task_repo_root/scripts/env.sh"

if [[ $(uname -s) != Linux || $(uname -m) != x86_64 ]]; then
    printf '%s\n' 'This setup script supports Linux x86_64. See README.md for Windows.' >&2
    exit 1
fi

for task_command in python3 curl sha256sum; do
    if ! command -v "$task_command" >/dev/null 2>&1; then
        printf 'Required command is missing: %s\n' "$task_command" >&2
        exit 1
    fi
done

# Parse TOML rather than duplicating the pinned compiler version in this script.
# Python 3.11+ supplies tomllib without an additional package installation.
task_toolchain_settings=$(python3 - "$task_repo_root/rust-toolchain.toml" <<'PY'
import re
import sys
import tomllib

with open(sys.argv[1], "rb") as manifest:
    toolchain = tomllib.load(manifest)["toolchain"]
channel = toolchain["channel"]
if not isinstance(channel, str) or not re.fullmatch(r"\d+\.\d+\.\d+", channel):
    raise SystemExit("rust-toolchain.toml must pin an exact Rust version, such as 1.99.1")
profile = toolchain.get("profile", "minimal")
if profile not in ("minimal", "default", "complete"):
    raise SystemExit("Unsupported Rust toolchain profile")
print(channel)
print(profile)
for key, label in (("components", "component"), ("targets", "target")):
    values = toolchain.get(key, [])
    if not isinstance(values, list):
        raise SystemExit(f"{key} must be a TOML array")
    for value in values:
        if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", value):
            raise SystemExit(f"Invalid {label} name")
        print(f"{label} {value}")
PY
)
mapfile -t task_settings <<< "$task_toolchain_settings"
task_channel=${task_settings[0]}
task_profile=${task_settings[1]}
task_install_args=()
for task_setting in "${task_settings[@]:2}"; do
    task_install_args+=("--${task_setting%% *}" "${task_setting#* }")
done

if [[ ! -x "$CARGO_HOME/bin/rustup" ]]; then
    # Fixed rustup bootstrap release and checksum for x86_64-unknown-linux-gnu.
    # curl inherits the session's proxy and CA configuration; TLS checks stay on.
    task_rustup_version=1.28.2
    task_rustup_sha256=20a06e644b0d9bd2fbdbfd52d42540bdde820ea7df86e92e533c073da0cdd43c
    mkdir -p "$TASK_RUST_TOOLS_ROOT"
    task_download_dir=$(mktemp -d "$TASK_RUST_TOOLS_ROOT/.rustup-download.XXXXXX")
    trap 'rm -rf -- "$task_download_dir"' EXIT
    task_installer=$task_download_dir/rustup-init
    curl --fail --location --proto '=https' --proto-redir '=https' --tlsv1.2 \
        --retry 3 --retry-delay 1 \
        "https://static.rust-lang.org/rustup/archive/$task_rustup_version/x86_64-unknown-linux-gnu/rustup-init" \
        --output "$task_installer"
    printf '%s  %s\n' "$task_rustup_sha256" "$task_installer" | sha256sum --check
    chmod +x "$task_installer"
    "$task_installer" -y --no-modify-path --default-toolchain none --profile minimal
fi

# Re-running setup adds missing components/targets without upgrading the pinned
# compiler or self-updating rustup. Existing proxy/CA environment remains intact.
"$CARGO_HOME/bin/rustup" toolchain install "$task_channel" \
    --profile "$task_profile" --no-self-update "${task_install_args[@]}"

printf '\nRust %s is ready. Activate it in your current shell:\n' "$task_channel"
printf '  . ./scripts/env.sh\n'
printf 'Then run:\n  make verify\n'
