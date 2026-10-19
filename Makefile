.PHONY: setup verify firmware fmt test clean

setup:
	bash scripts/setup-rust.sh

verify:
	. ./scripts/env.sh && bash scripts/verify.sh

firmware:
	. ./scripts/env.sh && cargo firmware

fmt:
	. ./scripts/env.sh && cargo fmt --all

test:
	. ./scripts/env.sh && cargo test --locked --package app-logic --all-targets

clean:
	. ./scripts/env.sh && cargo clean
